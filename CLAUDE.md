# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A real-time audio translation system for PotPlayer (Windows media player). Captures the player's PCM audio output, transcribes/translates it via `faster-whisper`, and displays translated subtitles as a mouse-transparent overlay.

## Architecture

Three decoupled components that communicate locally:

```
PotPlayer → [DSP Plugin] → UDP :12345 → [Python Flask Server] → HTTP :5000/subtitle → [PyQt6 Overlay]
```

1. **`dsp_plugin/`** — C++ Winamp DSP plugin loaded by PotPlayer. In `modify_samples()`, it captures PCM audio and sends each chunk via UDP to `127.0.0.1:12345` with a 12-byte header (`int32 srate, nch, bps`) followed by raw PCM samples.
2. **`backend/server.py`** — Receives UDP audio on port 12345, resamples to 16kHz mono, buffers segments (2–3s chunks with 0.5s overlap), transcribes via `faster-whisper` (CUDA), and serves the latest subtitle text at `GET /subtitle` on port 5000.
3. **`backend/overlay.py`** — PyQt6 window (frameless, always-on-top, mouse-transparent, translucent background) polls `/subtitle` every 500ms and renders the text centered at the bottom of the screen.

## Development Commands

### C++ DSP Plugin (Windows only, requires Visual Studio + CMake)

```bash
cd dsp_plugin && mkdir build && cd build
cmake ..
cmake --build . --config Release
# Output: dsp_plugin/build/Release/dsp_whisper.dll
```

Match the architecture (32-bit vs 64-bit) to your PotPlayer installation.

### Python Backend (Python 3.10+, NVIDIA GPU + CUDA required)

```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python server.py      # wait for "Model loaded"
python overlay.py     # in a separate terminal
```

The `start.bat` script automates venv creation, dependency install (via Tsinghua mirror), and launches both Python processes.

### Plugin Installation

Run `install_plugin.bat` — it attempts to compile the DSP plugin, locates PotPlayer via registry, and copies the DLL. Or manually copy `dsp_whisper.dll` to `PotPlayer\Plugins\Audio\` and enable it under PotPlayer → F5 → Sound → Sound Processing → Winamp DSP.

## Key Technical Details

- **Whisper model**: Defaults to `tiny` for speed; change `WHISPER_MODEL` in `server.py` to `small`, `medium`, or `large-v3` for better quality at the cost of latency.
- **Audio format**: DSP sends 16-bit PCM; server always converts to 16kHz mono float32 before feeding Whisper.
- **UDP packet format**: 12-byte header (`int32 srate, int32 nch, int32 bps`) + raw PCM data. No fragmentation handling — PotPlayer's typical chunk sizes (576–1152 samples) fit within a single UDP datagram.
- **No persistence**: Subtitles live in memory only (`current_subtitle` global). No log file, no database.
- **Windows-only**: The entire stack (Winsock, Winamp DSP API, PyQt6) targets Windows exclusively.
