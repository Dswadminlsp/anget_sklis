#!/usr/bin/env python3
"""
微信/QQ 自动化助手 - 跨平台版
支持: Windows (pywinauto) + macOS (pyautogui + osascript)

Windows QQ 语音发送说明：
1. 需要 QQ 客户端在 Windows 上运行
2. 可以通过 pyautogui 自动化粘贴音频文件并发送
3. 注意：Windows QQ 可能不支持直接粘贴 .silk 文件作为语音
   如果不行，可以：
   - 把 .silk 转为 .wav 或 .mp3
   - 或者使用 QQ 的语音消息功能（如果有 API）
"""

import platform
import os
import time
import subprocess
import sys
import json
import logging
import threading

# 根据平台选择自动化方案
IS_WINDOWS = platform.system() == "Windows"
IS_MAC = platform.system() == "Darwin"

if IS_WINDOWS:
    try:
        import pyautogui
        import pyperclip
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.5
        print("✅ Windows 模式: pywinauto/pyautogui")
    except ImportError:
        print("⚠️ pyautogui 未安装，Windows 自动化可能不可用")
        pyautogui = None
        pyperclip = None
elif IS_MAC:
    try:
        import pyautogui
        import pyperclip
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.5
        print("✅ macOS 模式: pyautogui + osascript")
    except ImportError:
        print("⚠️ pyautogui 未安装，macOS 自动化可能不可用")
        pyautogui = None
        pyperclip = None
else:
    print("⚠️ Linux 模式: 仅支持 TTS 服务，不支持自动化")
    pyautogui = None
    pyperclip = None

from flask import Flask, request, jsonify

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)


def copy_to_clipboard(text):
    """跨平台复制到剪贴板"""
    try:
        if IS_WINDOWS:
            # Windows: 使用 pyperclip
            if pyperclip:
                pyperclip.copy(text)
        elif IS_MAC:
            # macOS: 使用 pbcopy
            subprocess.run(['pbcopy'], input=text.encode(), check=True)
        else:
            # Linux: 尝试 xclip
            subprocess.run(['xclip', '-selection', 'c'], input=text.encode(), check=True)
        time.sleep(0.1)
    except Exception as e:
        logger.warning(f"复制到剪贴板失败: {e}")


def activate_window(app_name: str) -> bool:
    """跨平台激活窗口"""
    try:
        if IS_WINDOWS:
            import win32gui
            import win32con
            # 尝试找到窗口
            hwnd = win32gui.FindWindow(None, app_name)
            if hwnd:
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                win32gui.SetForegroundWindow(hwnd)
                time.sleep(1)
                return True
            # 尝试按名称模糊匹配
            def callback(hwnd, extra):
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd)
                    if app_name.lower() in title.lower():
                        extra.append(hwnd)
                return True
            windows = []
            win32gui.EnumWindows(callback, windows)
            if windows:
                win32gui.ShowWindow(windows[0], win32con.SW_RESTORE)
                win32gui.SetForegroundWindow(windows[0])
                time.sleep(1)
                return True
        elif IS_MAC:
            subprocess.run(['osascript', '-e', f'tell application "{app_name}" to activate'], check=True)
            time.sleep(2)
            return True
        return False
    except Exception as e:
        logger.warning(f"激活窗口失败: {e}")
        return False


def key_modifier():
    """返回 Ctrl/Cmd 修饰键"""
    return 'ctrl' if IS_WINDOWS else 'command'


def wechat_send(contact: str, message: str) -> dict:
    """微信发送消息"""
    if not pyautogui:
        return {"status": "error", "message": f"平台不支持: {platform.system()}"}
    
    try:
        activate_window("微信")
        
        # 打开搜索
        pyautogui.hotkey(key_modifier(), 'f')
        time.sleep(0.5)
        
        # 清除之前的搜索内容
        pyautogui.hotkey(key_modifier(), 'a')
        pyautogui.press('backspace')
        time.sleep(0.3)
        
        # 复制搜索内容并粘贴
        copy_to_clipboard(contact)
        time.sleep(0.2)
        pyautogui.hotkey(key_modifier(), 'v')
        time.sleep(2)
        
        # 等待搜索结果
        time.sleep(1)
        
        # 智能选择
        for attempt in range(5):
            if attempt > 0:
                pyautogui.press('down')
                time.sleep(0.3)
            
            pyautogui.press('enter')
            time.sleep(1.5)
            
            # 输入消息测试
            copy_to_clipboard("test")
            time.sleep(0.2)
            pyautogui.hotkey(key_modifier(), 'v')
            time.sleep(0.5)
            
            pyautogui.hotkey(key_modifier(), 'a')
            pyautogui.press('backspace')
            time.sleep(0.2)
            
            # 输入真正消息
            copy_to_clipboard(message)
            time.sleep(0.2)
            pyautogui.hotkey(key_modifier(), 'v')
            time.sleep(0.3)
            
            pyautogui.press('enter')
            time.sleep(0.5)
            
            return {"status": "ok", "message": f"已发送给 {contact}"}
        
        return {"status": "error", "message": "未能找到联系人"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def qq_send(contact: str, message: str) -> dict:
    """QQ发送消息"""
    if not pyautogui:
        return {"status": "error", "message": f"平台不支持: {platform.system()}"}
    
    try:
        activate_window("QQ")
        
        # 打开搜索 Cmd+F / Ctrl+F
        pyautogui.hotkey(key_modifier(), 'f')
        time.sleep(0.5)
        
        # 清除之前的搜索内容
        pyautogui.hotkey(key_modifier(), 'a')
        pyautogui.press('backspace')
        time.sleep(0.3)
        
        # 复制搜索内容并粘贴
        copy_to_clipboard(contact)
        time.sleep(0.2)
        pyautogui.hotkey(key_modifier(), 'v')
        time.sleep(2)
        
        time.sleep(1)
        
        # 智能选择
        for attempt in range(5):
            if attempt > 0:
                pyautogui.press('down')
                time.sleep(0.3)
            
            pyautogui.press('enter')
            time.sleep(2)
            
            # 点击消息输入框
            pyautogui.click(1500, 900)
            time.sleep(0.5)
            
            # 直接输入消息
            copy_to_clipboard(message)
            time.sleep(0.2)
            pyautogui.hotkey(key_modifier(), 'v')
            time.sleep(0.3)
            
            pyautogui.press('enter')
            time.sleep(0.5)
            
            return {"status": "ok", "message": f"QQ已发送给 {contact}"}
        
        return {"status": "error", "message": "未能找到联系人"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.route('/wechat/send', methods=['POST'])
def wechat_send_api():
    data = request.get_json()
    return jsonify(wechat_send(data.get('contact', ''), data.get('message', '')))


@app.route('/wechat/audio', methods=['POST'])
def wechat_audio_api():
    """
    接收 SILK 或 MP3 音频，通过 pyautogui 粘贴发送
    支持:
      - silk_base64: SILK 格式（优先）
      - audio_path: MP3 文件路径（回退）
    """
    data = request.get_json()
    silk_base64 = data.get('silk_base64')
    audio_path = data.get('audio_path')

    if not silk_base64 and not audio_path:
        return jsonify({"success": False, "error": "缺少 silk_base64 或 audio_path"})

    temp_path = "/tmp/dulong_wechat_audio.silk"

    try:
        aac_path = None
        if silk_base64:
            # SILK: 先写入临时文件，再用 QQ 的方式粘贴发送
            silk_bytes = bytes.fromhex(silk_base64)
            with open(temp_path, 'wb') as f:
                f.write(silk_bytes)
            logger.info(f"微信音频: 写入 SILK {len(silk_bytes)} bytes")

            # macOS QQ/微信: 把 SILK 转为 AAC 再粘贴（需要 ffmpeg）
            # 微信 Mac 版支持直接粘贴 .silk 文件作为语音
            # 先尝试转换为 AAC (m4a) 以提高兼容性
            aac_path = "/tmp/dulong_wechat_audio.m4a"
            result = subprocess.run(
                ['ffmpeg', '-y', '-f', 'silk', '-i', temp_path,
                 '-ar', '24000', '-ac', '1', '-c:a', 'aac', '-b:a', '32k', aac_path],
                capture_output=True, timeout=30
            )
            if result.returncode == 0 and os.path.exists(aac_path):
                send_path = aac_path
                logger.info("微信音频: SILK -> AAC 转换成功")
            else:
                # 转换失败则直接发 SILK
                send_path = temp_path
                logger.warning(f"微信音频: AAC 转换失败，使用原始 SILK")

        else:
            send_path = audio_path
            temp_path = None

        # 通过自动化粘贴发送
        success = paste_and_send_audio("微信", send_path)

        # 清理临时文件
        for p in [temp_path, aac_path]:
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except:
                    pass

        return jsonify({"success": success})

    except Exception as e:
        logger.error(f"微信音频发送异常: {e}")
        return jsonify({"success": False, "error": str(e)})


def paste_and_send_audio(app_name: str, audio_path: str, cleanup_paths: list = None) -> bool:
    """
    通用自动化发送音频：激活窗口 → 聚焦输入框 → 粘贴文件 → 回车发送
    macOS 上微信/QQ 支持直接粘贴音频文件作为语音消息
    cleanup_paths: 发送完成后要清理的临时文件列表
    """
    try:
        if not pyautogui:
            logger.error(f"自动化不可用 ({platform.system()})")
            return False

        activate_window(app_name)
        time.sleep(1.5)

        # macOS: 点击消息输入区域中心
        if IS_MAC:
            pyautogui.click(800, 700)
            time.sleep(0.3)

        # 复制文件路径到剪贴板
        copy_to_clipboard(audio_path)
        time.sleep(0.2)

        # 粘贴（macOS 上 Cmd+V 粘贴文件路径会触发文件发送）
        pyautogui.hotkey(key_modifier(), 'v')
        time.sleep(0.5)

        # 回车确认发送
        pyautogui.press('enter')
        time.sleep(0.5)

        logger.info(f"{app_name} 音频发送完成")
        return True

    except Exception as e:
        logger.error(f"自动化发送音频失败: {e}")
        return False


@app.route('/qq/send', methods=['POST'])
def qq_send_api():
    data = request.get_json()
    return jsonify(qq_send(data.get('contact', ''), data.get('message', '')))


@app.route('/status')
def status():
    return jsonify({
        "status": "running",
        "platform": platform.system(),
        "automation": "available" if pyautogui else "unavailable"
    })


if __name__ == '__main__':
    print(f"🚀 微信/QQ智能助手启动 ({platform.system()})")
    app.run(host='0.0.0.0', port=8766, debug=False)
