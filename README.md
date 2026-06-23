# PotPlayer Real-time Translation Plugin

将 PotPlayer 播放的音频实时转录并翻译为字幕的完整方案。

## 架构

```
PotPlayer 音频 → [DSP 插件 C++] → UDP :12345 → [Python 服务端]
                                                      │
                                          ┌───────────┴───────────┐
                                          │  Silero VAD (语音检测) │
                                          │  faster-whisper (转写) │
                                          │  翻译引擎 (可选)       │
                                          └───────────┬───────────┘
                                                      │
                                          HTTP :5000/subtitle
                                                      │
                                          [PyQt6 透明悬浮窗]
```

**三个组件**：

| 组件 | 技术 | 职责 |
|------|------|------|
| `dsp_plugin/` | C++ Winamp DSP | 捕获 PCM 音频，通过 UDP 发送到本地 |
| `backend/server.py` | Python + faster-whisper + Flask | 语音识别 + 翻译 + HTTP API |
| `backend/overlay.py` | Python + PyQt6 | 透明悬浮窗显示翻译字幕 |

## 功能特性

- **本地语音识别**：faster-whisper (CUDA 加速)，延迟低、离线可用
- **可切换翻译后端**：
  - `ollama` — 本地 Ollama 小模型（完全离线，推荐 qwen2.5:1.5b）
  - `api` — 任何 OpenAI 兼容 API（OpenAI / DeepSeek / Groq / OpenRouter 等）
  - `none` — 不翻译，直接输出原文转写
- **VAD 语音检测**：Silero VAD 过滤静音和噪音，避免乱码字幕
- **字幕生命周期**：停止说话后自动淡出，不再永久挂屏
- **播放状态同步**：暂停/跳转时自动清空旧缓冲
- **热更新配置**：通过 HTTP API 实时修改翻译设置，无需重启
- **模型可切换**：支持 tiny / small / medium / large-v3，或自定义 HuggingFace 模型

## 快速开始

### 1. 安装 DSP 插件

需要 CMake 和 Visual Studio (C++ 桌面开发)。

```bash
cd dsp_plugin
mkdir build && cd build
cmake ..
cmake --build . --config Release
```

将 `build/Release/dsp_whisper.dll` 复制到 PotPlayer 的 `Plugins\Audio\` 目录。

然后在 PotPlayer 中：F5 → 声音 → 声音处理 → Winamp DSP 插件 → 勾选启用 → 选择 "Whisper Interceptor Plugin"。

或者运行 `install_plugin.bat` 自动完成编译和安装。

### 2. 安装 Python 依赖

需要 Python 3.10+ 和 NVIDIA GPU + CUDA。

```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

*如果 torch 无法使用 GPU，请前往 PyTorch 官网安装 CUDA 版本的 PyTorch。*

### 3. 配置

编辑 `backend/config.yaml`（有注释说明每个选项）或设置环境变量：

```bash
# API 模式（推荐用于翻译）
set TRANSLATION_BACKEND=api
set TRANSLATION_API_KEY=your-api-key
set TRANSLATION_TARGET_LANG=zh

# Ollama 本地模式
set TRANSLATION_BACKEND=ollama

# 模型切换
set WHISPER_MODEL=medium
```

环境变量优先级高于 config.yaml。

### 4. 运行

```bash
# 方式一：一键启动
start.bat

# 方式二：分别启动
cd backend
python server.py      # 等待控制台显示 "Model loaded" 和 "Ready"
python overlay.py     # 新开一个终端
```

打开 PotPlayer 播放任意视频即可看到实时翻译字幕。

## API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/subtitle` | GET | 获取当前字幕 `{"text": "..."}` |
| `/health` | GET | 健康状态检查 |
| `/config` | GET | 查看当前配置（API key 已脱敏） |
| `/config` | PUT | 热更新翻译和字幕设置 |

### 热更新示例

```bash
curl -X PUT http://127.0.0.1:5000/config \
  -H "Content-Type: application/json" \
  -d '{"translator": {"backend": "ollama", "target_lang": "en"}}'
```

## 翻译提供商配置

### API 模式（OpenAI 兼容）

所有支持 `/v1/chat/completions` 格式的提供商均可使用：

| 提供商 | base_url | 推荐模型 |
|--------|----------|----------|
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` |
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |
| Groq | `https://api.groq.com/openai/v1` | `llama-3.1-8b-instant` |
| OpenRouter | `https://openrouter.ai/api/v1` | 多种可选 |
| SiliconFlow | `https://api.siliconflow.cn/v1` | `Qwen/Qwen2.5-7B-Instruct` |

设置环境变量 `TRANSLATION_API_KEY`，然后在 `config.yaml` 中修改 `api_base_url` 和 `api_model`。

### Ollama 模式（本地）

```bash
# 安装 Ollama 并拉取模型
ollama pull qwen2.5:1.5b    # 轻量 (~1GB)，适合翻译
ollama pull qwen2.5:7b      # 更大，翻译质量更好

# 启动 Ollama
ollama serve
```

然后在 `config.yaml` 中设置 `translator.backend: ollama`。

## Whisper 模型选择

| 模型 | VRAM | 速度 | 精度 | 适用场景 |
|------|------|------|------|----------|
| `tiny` | ~1 GB | 最快 | 低 | 低配 GPU，英文优先 |
| `small` | ~2 GB | 快 | 中 | **推荐默认**，平衡之选 |
| `medium` | ~5 GB | 中 | 高 | 多语言混合，追求准确 |
| `large-v3` | ~10 GB | 慢 | 最高 | 专业场景 |

可设置自定义 HuggingFace 路径，例如非英语优化的 whisper 变体。

## 目录结构

```
├── dsp_plugin/           C++ Winamp DSP 插件
│   ├── dsp.h             Winamp DSP API 头文件
│   ├── main.cpp          插件实现（UDP 发送）
│   └── CMakeLists.txt    构建配置
├── backend/              Python 翻译后端
│   ├── config.py         配置管理
│   ├── config.yaml       配置文件（用户可编辑）
│   ├── server.py         主服务（UDP 接收 + VAD + Whisper + 翻译 + API）
│   ├── vad.py            Silero VAD 语音检测封装
│   ├── translator.py     翻译管道（Ollama / OpenAI API / Noop）
│   ├── subtitle_manager.py  字幕生命周期管理
│   ├── overlay.py        透明字幕悬浮窗
│   └── requirements.txt  Python 依赖
├── start.bat             一键启动脚本
├── install_plugin.bat    DSP 插件编译安装脚本
└── README.md
```
