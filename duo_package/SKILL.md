---
name: duo-tts
description: 独龙 TTS 语音服务 - 文本转语音并发送到飞书/QQ/微信
metadata:
  {
    "openclaw": {
      "os": ["darwin", "linux"],
      "requires": {
        "bins": ["python3", "ffmpeg"]
      }
    }
  }
---

# 独龙工具集 (Duo Package) v1.3.1

> 🎙️ TTS 语音服务 + 飞书/微信/QQ 音频发送插件

## ✨ 新特性（v1.3.1）

- ✅ **移除硬编码凭证** — 不再包含任何私人应用凭证，安全分享
- ✅ **飞书配置全自动** — 自动从 OpenClaw 配置读取 `appId`、`appSecret`、`userId`，开箱即用
- ✅ **微信语音支持 SILK** — 微信语音也转为 SILK 格式，支持原生语音条
- ✅ **环境变量优先级** — 可通过环境变量覆盖，灵活适配不同部署环境
- ✅ **自动发送开关** — 可通过 `AUTO_SEND_TTS=false` 关闭自动发送飞书/QQ/微信

---

## 功能一览

| 功能 | 说明 |
|------|------|
| 🎙️ **TTS 语音合成** | 中文语音，Azure 晓晓音色，OpenAI 兼容接口 |
| 📱 **飞书音频** | 转 OPUS 格式，OpenClaw 配置自动读取 |
| 💬 **QQ 语音** | 转 SILK 格式，原生语音气泡 |
| 📱 **微信语音** | 转 SILK + AAC，原生语音条 |
| 🔧 **OpenAI 兼容** | `/audio/speech` 兼容 QClaw 等客户端 |

---

## 快速开始

### 1. 安装依赖

```bash
pip3 install pygame requests flask pysilk silk-python
```

### 2. 配置飞书（自动读取）

服务启动时自动从本机 OpenClaw 配置读取，无需任何手动操作：

- `FEISHU_APP_ID` — 从 `~/.openclaw/openclaw.json` → `channels.feishu.appId`
- `FEISHU_APP_SECRET` — 从 `~/.openclaw/openclaw.json` → `channels.feishu.appSecret`
- `FEISHU_USER_ID` — 从 `~/.openclaw/credentials/feishu-default-allowFrom.json`

**手动覆盖（如需指定其他飞书应用）**：

```bash
export FEISHU_APP_ID="cli_xxxxxxxx"
export FEISHU_APP_SECRET="xxxxxxxx"
export FEISHU_USER_ID="ou_xxxxxxxx"
```

### 3. 启动服务

```bash
# TTS 服务（端口 8765）
python3 ~/.openclaw/workspace/skills/duo_package/scripts/dulong_tts_server.py

# 关闭自动发送（如不需要自动发飞书/QQ/微信）
AUTO_SEND_TTS=false python3 ~/.openclaw/workspace/skills/duo_package/scripts/dulong_tts_server.py
```

### 4. 配置 OpenClaw / QClaw

在 `~/.openclaw/openclaw.json` 中配置 TTS：

```json
{
  "messages": {
    "tts": {
      "auto": "always",
      "provider": "openai",
      "openai": {
        "baseUrl": "http://localhost:8765",
        "apiKey": "dummy-key-for-local-tts",
        "model": "tts-1"
      }
    }
  }
}
```

---

## 接口说明

### POST /speak

统一播报接口，同时生成语音并发送：

```json
{
  "text": "要播报的文本",
  "targets": ["feishu", "qq", "wechat"]
}
```

### POST /audio/speech（OpenAI 兼容）

```json
{
  "model": "tts-1",
  "input": "要播报的文本",
  "voice": "alloy"
}
```

### POST /wechat/audio

发送微信语音（SILK 格式）：

```json
{
  "silk_base64": "...",
  "audio_path": "/path/to/audio.mp3"
}
```

---

## 配置优先级

```
环境变量 > OpenClaw 自动读取 > 空（无默认值）
```

## 自动发送控制

| 环境变量 | 值 | 效果 |
|---------|-----|------|
| `AUTO_SEND_TTS` | `true`（默认） | 生成后自动发送飞书/QQ/微信 |
| `AUTO_SEND_TTS` | `false` | 只生成语音，不自动发送 |

---

## 依赖

| 依赖 | 说明 |
|------|------|
| pygame | 本机音频播放 |
| requests | HTTP 请求 |
| flask | Web 服务 |
| pysilk | SILK 音频编码 |
| ffmpeg | 音频格式转换 |

---

## 注意事项

1. 飞书音频发送需要有效的飞书应用凭证（自动从 OpenClaw 读取）
2. 微信/QQ 自动化需要 Mac/Linux 系统（使用 pyautogui）
3. TTS 文本中的 `[[tts]]` 等标签会被自动过滤
4. 系统提示词相关内容会被拒绝生成
