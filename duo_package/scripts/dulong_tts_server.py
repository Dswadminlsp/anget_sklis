#!/usr/bin/env python3
"""
独龙 TTS 服务 - 使用 pygame 播放 + 飞书/QQ/微信音频
支持格式: MP3 (飞书) + SILK (QQ/微信)
"""

from flask import Flask, request, jsonify, send_file
import requests
import pygame
import io
import os
from datetime import datetime, timedelta
import time
import json
import logging
import threading
import subprocess

# 尝试导入 pysilk（用于 SILK 编码）
try:
    import pysilk
    SILK_AVAILABLE = True
except ImportError:
    SILK_AVAILABLE = False
    logger.warning("pysilk 未安装，QQ 语音将不可用")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# TTS 配置
VOICE = "zh-CN-XiaoxiaoNeural"
SPEED = 1.0
PITCH = "0"
STYLE = "general"

# 飞书配置（可通过环境变量覆盖）
# 完整从 OpenClaw 配置自动获取，无需手动填写

def _auto_get_feishu_config() -> dict:
    """从 OpenClaw 配置自动获取飞书相关配置"""
    import json
    cfg = {}
    # 1. 从 openclaw.json 读取 appId 和 appSecret
    openclaw_cfg_path = os.path.expanduser("~/.openclaw/openclaw.json")
    try:
        with open(openclaw_cfg_path) as f:
            d = json.load(f)
        feishu_cfg = d.get("channels", {}).get("feishu", {})
        cfg["FEISHU_APP_ID"] = feishu_cfg.get("appId", "")
        cfg["FEISHU_APP_SECRET"] = feishu_cfg.get("appSecret", "")
    except Exception:
        pass
    # 2. 从 feishu-default-allowFrom.json 读取已配对用户 open_id
    allowFrom_path = os.path.expanduser("~/.openclaw/credentials/feishu-default-allowFrom.json")
    try:
        with open(allowFrom_path) as f:
            data = json.load(f)
        if data.get("allowFrom") and len(data["allowFrom"]) > 0:
            cfg["FEISHU_USER_ID"] = data["allowFrom"][0]
    except Exception:
        pass
    return cfg

_auto_cfg = _auto_get_feishu_config()

FEISHU_APP_ID = os.environ.get("FEISHU_APP_ID") or _auto_cfg.get("FEISHU_APP_ID") or ""
FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET") or _auto_cfg.get("FEISHU_APP_SECRET") or ""
FEISHU_USER_ID = os.environ.get("FEISHU_USER_ID") or _auto_cfg.get("FEISHU_USER_ID") or ""

# 微信配置（通过 Windows 接口）
WECHAT_API = "http://localhost:8766"

# QQ配置（通过 Windows 接口）
QQ_API = "http://localhost:8766"

# 自动发送开关（环境变量控制）
# 设置为 "false" 可关闭自动发送飞书/QQ/微信
AUTO_SEND_TTS = os.environ.get("AUTO_SEND_TTS", "true").lower() != "false"

SERVER_IP = "localhost"
SERVER_PORT = 8765

AUDIO_DIR = os.path.expanduser("~/.openclaw/workspace/tts_audio")
os.makedirs(AUDIO_DIR, exist_ok=True)

# 初始化 pygame
pygame.mixer.init()

# 当前播放状态
is_playing = False


def get_feishu_token():
    try:
        url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
        data = {"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET}
        response = requests.post(url, json=data, timeout=10)
        result = response.json()
        if result.get("code") == 0:
            return result.get("tenant_access_token")
    except Exception as e:
        logger.error(f"获取飞书 token 失败: {e}")
    return None


def generate_speech(text: str) -> bytes:
    """生成语音"""
    url = "https://tts.wangwangit.com/v1/audio/speech"
    headers = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
    data = {"input": text, "voice": VOICE, "speed": SPEED, "pitch": PITCH, "style": STYLE}
    
    try:
        response = requests.post(url, json=data, headers=headers, timeout=60)
        if response.status_code == 200 and len(response.content) > 0:
            logger.info(f"TTS 生成成功: {len(response.content)} bytes")
            return response.content
        else:
            logger.error(f"TTS 返回异常: status={response.status_code}, size={len(response.content)}")
    except Exception as e:
        logger.error(f"TTS 生成失败: {e}")
    return None


def mp3_to_silk(mp3_data: bytes) -> bytes:
    """将 MP3 转换为 SILK 格式（用于 QQ 语音）"""
    if not SILK_AVAILABLE:
        raise RuntimeError("pysilk 未安装")
    
    # Step 1: FFmpeg 将 MP3 转为 24kHz PCM
    pcm_buf = io.BytesIO()
    result = subprocess.run(
        ['ffmpeg', '-y', '-i', 'pipe:0',
         '-ar', '24000', '-ac', '1', '-f', 's16le', '-acodec', 'pcm_s16le', 'pipe:1'],
        input=mp3_data, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=30
    )
    
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg 转 PCM 失败: {result.returncode}")
    
    pcm_data = result.stdout
    
    # Step 2: pysilk 编码为 SILK (tencent=True 适配 QQ)
    input_stream = io.BytesIO(pcm_data)
    output_stream = io.BytesIO()
    pysilk.encode(input_stream, output_stream, sample_rate=24000, bit_rate=40000)
    
    silk_data = output_stream.getvalue()
    logger.info(f"SILK 编码成功: {len(silk_data)} bytes (from {len(mp3_data)} bytes MP3)")
    return silk_data


def play_audio(audio_data: bytes):
    """播放音频"""
    global is_playing
    
    if pygame.mixer.music.get_busy():
        pygame.mixer.music.stop()
    
    try:
        is_playing = True
        audio_file = io.BytesIO(audio_data)
        pygame.mixer.music.load(audio_file)
        pygame.mixer.music.play()
        logger.info("开始播放")
        
        while pygame.mixer.music.get_busy():
            time.sleep(0.1)
        
        logger.info("播放完成")
    except Exception as e:
        logger.error(f"播放错误: {e}")
    finally:
        is_playing = False


def upload_audio_to_feishu(file_path: str) -> str:
    """上传音频到飞书（转换为 opus 格式）"""
    token = get_feishu_token()
    if not token:
        logger.error("无法获取飞书 token")
        return None
    
    try:
        opus_path = file_path.replace('.mp3', '.opus')
        result = subprocess.run(
            ['ffmpeg', '-y', '-i', file_path, '-c:a', 'libopus', opus_path],
            capture_output=True, timeout=30
        )
        
        if result.returncode != 0:
            logger.error(f"FFmpeg opus 转换失败: {result.stderr.decode()[:200]}")
            return None
        
        url = "https://open.feishu.cn/open-apis/im/v1/files"
        headers = {"Authorization": f"Bearer {token}"}
        
        with open(opus_path, 'rb') as f:
            files = {'file': ('audio.opus', f, 'audio/opus')}
            data = {'file_type': 'opus', 'file_name': 'audio.opus'}
            response = requests.post(url, headers=headers, files=files, data=data, timeout=60)
        
        result = response.json()
        if result.get("code") == 0:
            try:
                os.remove(opus_path)
            except:
                pass
            return result.get("data", {}).get("file_key")
        else:
            logger.error(f"飞书上传统失败: {result}")
    except Exception as e:
        logger.error(f"上传失败: {e}")
    
    return None


def send_feishu_audio(file_key: str) -> bool:
    """发送飞书音频消息"""
    token = get_feishu_token()
    if not token:
        logger.error("发送飞书音频失败: 无 token")
        return False
    
    try:
        url = "https://open.feishu.cn/open-apis/im/v1/messages"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        
        response = requests.post(
            url, headers=headers,
            params={'receive_id_type': 'open_id'},
            json={
                'receive_id': FEISHU_USER_ID,
                'msg_type': 'audio',
                'content': json.dumps({"file_key": file_key})
            },
            timeout=10
        )
        
        result = response.json()
        if result.get("code") == 0:
            logger.info(f"飞书音频发送成功: {result.get('data', {}).get('message_id')}")
            return True
        else:
            logger.error(f"飞书音频发送失败: {result}")
    except Exception as e:
        logger.error(f"发送飞书音频异常: {e}")
    
    return False


def send_wechat_audio(silk_data: bytes) -> bool:
    """通过微信接口发送音频（SILK 格式）"""
    try:
        response = requests.post(
            f"{WECHAT_API}/wechat/audio",
            json={"silk_base64": silk_data.hex()},
            timeout=15
        )
        return response.json().get("success", False)
    except Exception as e:
        logger.error(f"微信发送失败: {e}")
        return False


def send_wechat_audio_mp3(audio_path: str) -> bool:
    """通过微信接口发送音频（MP3 回退）"""
    try:
        response = requests.post(
            f"{WECHAT_API}/wechat/audio",
            json={"audio_path": audio_path},
            timeout=15
        )
        return response.json().get("success", False)
    except Exception as e:
        logger.error(f"微信发送失败(MP3): {e}")
        return False


def send_qq_audio(silk_data: bytes) -> bool:
    """通过 QQ 接口发送音频（SILK 格式）"""
    try:
        response = requests.post(
            f"{QQ_API}/qq/audio",
            json={"silk_base64": silk_data.hex()},
            timeout=15
        )
        return response.json().get("success", False)
    except Exception as e:
        logger.error(f"QQ 发送失败: {e}")
        return False


def cleanup_old_files():
    try:
        now = datetime.now()
        for filename in os.listdir(AUDIO_DIR):
            file_path = os.path.join(AUDIO_DIR, filename)
            if os.path.isfile(file_path):
                mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
                if now - mtime > timedelta(days=1):
                    os.remove(file_path)
    except:
        pass

cleanup_old_files()


# ============ OpenAI TTS 兼容接口 ============
@app.route('/v1/audio/speech', methods=['POST'])
@app.route('/audio/speech', methods=['POST'])
def openai_tts():
    """
    OpenAI 兼容的 TTS 接口（QClaw 调用）
    POST /audio/speech 或 /v1/audio/speech
    Body: {"model": "tts-1", "input": "text", "voice": "alloy", "response_format": "pcm"}
    Returns: 原始二进制音频数据（不是 JSON！）

    支持 target 参数: {"target": "wechat"} → 转为 SILK 语音条直接发送
    """
    data = request.get_json()
    text = data.get('input', '')
    model = data.get('model', 'tts-1')
    voice = data.get('voice', 'alloy')
    response_format = data.get('response_format', 'mp3')  # pcm 或 mp3
    target = data.get('target', 'default')  # wechat / qq / default

    # 详细日志：打印收到的原始数据
    logger.warning(f"[TTS DEBUG] raw_input={repr(text[:200])}")

    if not text:
        return 'text is empty', 400

    # 过滤 TTS 指令标签（如 [[tts]], [[tts openclaw]], [[/tts]] 等）
    import re
    text = re.sub(r'\[\[tts[^\]]*\]\]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[\[\/tts[^\]]*\]\]', '', text, flags=re.IGNORECASE)
    text = text.strip()

    # 过滤 URL 和 token（防止 API token、URL 等被朗读出来）
    # 过滤常见 URL 模式
    text = re.sub(r'https?://[^\s<>\[\]]+', ' ', text)
    # 过滤 token 模式（Bearer token、api-key 等）
    text = re.sub(r'Bearer\s+[a-zA-Z0-9_-]+', ' ', text)
    text = re.sub(r'api[_-]?key["\s:]+[a-zA-Z0-9_-]+', ' ', text, flags=re.IGNORECASE)
    text = re.sub(r'token["\s:]+[a-zA-Z0-9_-]+', ' ', text, flags=re.IGNORECASE)
    # 过滤文件路径中的敏感部分
    text = re.sub(r'MEDIA:[^\s]+', '', text)

    # 过滤系统提示词模式（防止 AI 把系统指令读出来）
    # 过滤"具体包括"开头的系统功能列表
    text = re.sub(r'具体包括[：:\s]*\n[^\n]+', ' ', text)
    # 过滤常见的系统指令关键词
    system_keywords = [
        r'读取文件', r'写入文件', r'编辑文件', r'执行命令',
        r'Shell\s+(ls|cat|git|python|cd|rm|mkdir)',
        r'工作目录', r'\.qclaw', r'\.openclaw',
        r'有什么具体任务', r'需要我帮你',
        r'文件操作能力', r'文本文件内容',
        r'创建新文件', r'覆盖已有文件',
        r'精确的部分修改', r'命令行操作',
    ]
    for keyword in system_keywords:
        text = re.sub(keyword, ' ', text, flags=re.IGNORECASE)

    # 过滤多余空格
    text = re.sub(r'\s+', ' ', text).strip()

    # 过滤 emoji（U+1F000-U+1FFFF 覆盖所有 emoji，不影响中文）
    text = re.sub(r'[\U0001F000-\U0001FFFF]', '', text)

    logger.warning(f"[TTS DEBUG] filtered_input={repr(text[:200])}")

    # 检测是否为系统提示词（在原始文本中检测）
    raw_system_patterns = [
        r'读取文件|写入文件|编辑文件|执行命令',
        r'Shell\s+(ls|cat|git|python|cd|rm|mkdir)',
        r'shell\s+(ls|cat|git|python|cd|rm|mkdir)',
        r'有什么具体任务|需要我帮你处理',
        r'你的系统有[一显]定的文件操作能力',
        r'\.qclaw/workspace|\.openclaw/workspace',
    ]
    raw_text = request.get_json().get('input', '')
    system_match_count = sum(1 for p in raw_system_patterns if re.search(p, raw_text, re.I))
    if system_match_count >= 1:
        logger.warning(f"[TTS] 疑似系统提示词，拒绝生成: {repr(raw_text[:100])}")
        return '疑似系统提示词，拒绝生成', 400


    if not text or len(text.strip()) < 2:
        logger.warning(f"[OpenAI TTS] text too short after filtering: '{text}'")
        return 'text too short after filtering', 400

    logger.info(f"[OpenAI TTS] voice={voice}, model={model}, format={response_format}, target={target}, text={text[:30]}...")

    # 生成语音
    audio_data = generate_speech(text)
    if not audio_data or len(audio_data) == 0:
        logger.error("[OpenAI TTS] TTS 生成失败")
        return 'TTS generation failed', 500

    # 保存记录
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"dulong_{timestamp}.mp3"
    file_path = os.path.join(AUDIO_DIR, filename)
    with open(file_path, 'wb') as f:
        f.write(audio_data)

    # 播放（后台）
    play_audio(audio_data)

    # 自动发送到飞书（OpenClaw TTS 模式，可通过 AUTO_SEND_TTS=false 关闭）
    if AUTO_SEND_TTS:
        try:
            file_key = upload_audio_to_feishu(file_path)
            if file_key:
                feishu_sent = send_feishu_audio(file_key)
                logger.info(f"[OpenAI TTS] 飞书音频发送: {'成功' if feishu_sent else '失败'}")
                # 清理文件
                try:
                    os.remove(file_path)
                except:
                    pass
        except Exception as e:
            logger.error(f"[OpenAI TTS] 飞书发送失败: {e}")

    logger.info(f"[OpenAI TTS] 生成成功: {len(audio_data)} bytes")

    # ========== 微信/QQ 语音条模式 ==========
    # 如果指定了 target=wechat 或 target=qq，直接发送语音条，不走 QClaw 的附件方式
    if target in ('wechat', 'qq') and SILK_AVAILABLE:
        try:
            silk_data = mp3_to_silk(audio_data)
            if target == 'wechat':
                sent = send_wechat_audio(silk_data)
                logger.info(f"[TTS] 微信语音条发送: {'成功' if sent else '失败'}")
            else:  # qq
                sent = send_qq_audio(silk_data)
                logger.info(f"[TTS] QQ 语音条发送: {'成功' if sent else '失败'}")
            # 清理 MP3
            try:
                os.remove(file_path)
            except:
                pass
            # 返回最小有效 MP3（QClaw 会播放这个，但实际语音已通过接口发出）
            # 1字节的静音 MP3 不会产生明显声音
            return send_file(
                io.BytesIO(b'\xff\xfb\x90\x00'),
                mimetype='audio/mpeg',
                as_attachment=False,
                download_name='speech.mp3'
            )
        except Exception as e:
            logger.error(f"[TTS] {target} 语音条发送失败: {e}")
            # 失败了就正常返回 MP3

    # 正常模式：返回 MP3 bytes
    return send_file(
        io.BytesIO(audio_data),
        mimetype='audio/mpeg',
        as_attachment=False,
        download_name='speech.mp3'
    )


@app.route('/speak', methods=['POST'])
def speak_endpoint():
    """
    统一播报接口
    生成语音 -> 播放 -> 发送到飞书
    """
    data = request.get_json()
    text = data.get('text', '')
    targets = data.get('targets', ['feishu'])  # 发送目标: feishu, wechat, qq
    
    # 过滤 TTS 指令标签
    import re
    text = re.sub(r'\[\[tts[^\]]*\]\]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[\[\/tts[^\]]*\]\]', '', text, flags=re.IGNORECASE)
    text = text.strip()
    
    if not text:
        return jsonify({'status': 'error', 'message': 'text is empty'})
    
    logger.info(f"🎤 播报 [{targets}]: {text[:30]}...")
    
    # 生成语音
    audio_data = generate_speech(text)
    if not audio_data or len(audio_data) == 0:
        logger.error("TTS 生成失败，返回空数据")
        return jsonify({'status': 'error', 'message': 'TTS failed: empty response'})
    
    # 保存 MP3
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"dulong_{timestamp}.mp3"
    file_path = os.path.join(AUDIO_DIR, filename)
    with open(file_path, 'wb') as f:
        f.write(audio_data)
    
    # 播放
    play_audio(audio_data)
    
    # 发送结果
    results = {'feishu_sent': False, 'wechat_sent': False, 'qq_sent': False}
    
    if 'feishu' in targets:
        file_key = upload_audio_to_feishu(file_path)
        if file_key:
            results['feishu_sent'] = send_feishu_audio(file_key)
    
    if 'wechat' in targets and SILK_AVAILABLE:
        try:
            silk_data = mp3_to_silk(audio_data)
            silk_path = file_path.replace('.mp3', '.silk')
            with open(silk_path, 'wb') as f:
                f.write(silk_data)
            results['wechat_sent'] = send_wechat_audio(silk_data)
            try:
                os.remove(silk_path)
            except:
                pass
        except Exception as e:
            logger.error(f"微信 SILK 转换/发送失败: {e}")
            results['wechat_sent'] = False
    elif 'wechat' in targets:
        # SILK 不可用时回退到 MP3
        logger.warning("微信发送：SILK 不可用，回退 MP3")
        results['wechat_sent'] = send_wechat_audio_mp3(file_path)

    if 'qq' in targets and SILK_AVAILABLE:
        try:
            silk_data = mp3_to_silk(audio_data)
            silk_path = file_path.replace('.mp3', '.silk')
            with open(silk_path, 'wb') as f:
                f.write(silk_data)
            results['qq_sent'] = send_qq_audio(silk_data)
            # 清理 SILK 文件
            try:
                os.remove(silk_path)
            except:
                pass
        except Exception as e:
            logger.error(f"QQ SILK 转换/发送失败: {e}")
            results['qq_sent'] = False
    
    # 清理 MP3 文件
    if results['feishu_sent']:
        try:
            os.remove(file_path)
        except:
            pass
    
    return jsonify({
        'status': 'ok',
        'text': text,
        'filename': filename,
        'audio_size': len(audio_data),
        'silk_available': SILK_AVAILABLE,
        'results': results,
        'audio_url': f"http://{SERVER_IP}:{SERVER_PORT}/audio/{filename}"
    })


@app.route('/to_feishu', methods=['POST'])
def to_feishu():
    """只发送到飞书"""
    return speak_endpoint()


@app.route('/to_qq', methods=['POST'])
def to_qq():
    """只发送到 QQ"""
    data = request.get_json()
    data['targets'] = ['qq']
    return speak_endpoint()


@app.route('/to_wechat', methods=['POST'])
def to_wechat():
    """只发送到微信"""
    data = request.get_json()
    data['targets'] = ['wechat']
    return speak_endpoint()


@app.route('/audio/<filename>')
def get_audio(filename):
    file_path = os.path.join(AUDIO_DIR, filename)
    if os.path.exists(file_path):
        return send_file(file_path, mimetype='audio/mpeg')
    return jsonify({'error': 'File not found'}), 404


@app.route('/silk/<filename>')
def get_silk(filename):
    """获取 SILK 格式音频"""
    file_path = os.path.join(AUDIO_DIR, filename.replace('.silk', '.mp3'))
    if not os.path.exists(file_path):
        return jsonify({'error': 'MP3 not found'}), 404
    
    if not SILK_AVAILABLE:
        return jsonify({'error': 'SILK not available'}), 500
    
    try:
        with open(file_path, 'rb') as f:
            mp3_data = f.read()
        silk_data = mp3_to_silk(mp3_data)
        return send_file(
            io.BytesIO(silk_data),
            mimetype='audio/SILK',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/audio_list')
def audio_list():
    files = sorted(os.listdir(AUDIO_DIR), reverse=True)
    return jsonify({'files': files})


@app.route('/health')
def health():
    return jsonify({
        'status': 'running',
        'silk_available': SILK_AVAILABLE,
        'audio_dir': AUDIO_DIR
    })


if __name__ == '__main__':
    print("🎙️ 独龙 TTS 服务已启动（pygame + 飞书/QQ/微信）")
    print(f"   SILK 支持: {'已启用' if SILK_AVAILABLE else '未安装 (QQ语音不可用)'}")
    app.run(host='0.0.0.0', port=SERVER_PORT, debug=False)
