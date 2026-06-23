"""
PotPlayer Real-time Translation Server.

Modular pipeline:
  UDP audio → VAD → faster-whisper → Translator → SubtitleManager → HTTP API

Architecture:
  - udp_receiver() thread: receives PCM audio from DSP plugin, handles control frames
  - process_loop() thread: VAD → Whisper transcription → translation → subtitle storage
  - Flask HTTP server: serves /subtitle, /health, /config endpoints
"""

import logging
import socket
import struct
import threading
import time
from typing import Optional

import numpy as np
import scipy.signal
from flask import Flask, jsonify, request

from config import load_config, Config, DEFAULT_CONFIG_PATH
from vad import get_speech_timestamps, has_speech
from translator import create_translator, BaseTranslator
from subtitle_manager import SubtitleManager

# ── Logging ──────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("server")

# ── Flask App ────────────────────────────────────────────────────────────

app = Flask(__name__)

# ── Global State ─────────────────────────────────────────────────────────

# Audio buffer (mono float32, 16kHz)
audio_buffer = np.array([], dtype=np.float32)
buffer_lock = threading.Lock()

# Last time we received UDP data (for timeout-based reset)
last_udp_time = time.time()
udp_time_lock = threading.Lock()

# Config, loaded after import
config: Optional[Config] = None

# Translator instance
translator: Optional[BaseTranslator] = None

# Subtitle manager
subtitle_mgr: Optional[SubtitleManager] = None

# Whisper model (loaded on startup)
whisper_model = None

# Flag to signal threads to stop
shutdown_flag = threading.Event()


# ── UDP Receiver ─────────────────────────────────────────────────────────

# Control frame: header with nch = -1 signals "playback reset"
CONTROL_RESET_NCH = -1


def udp_receiver():
    """Thread: receive PCM audio over UDP from the DSP plugin."""
    global audio_buffer, last_udp_time

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(1.0)  # 1s timeout so we can check shutdown_flag

    udp_ip = config.server.udp_ip
    udp_port = config.server.udp_port

    try:
        sock.bind((udp_ip, udp_port))
        logger.info(f"UDP receiver listening on {udp_ip}:{udp_port}")
    except OSError as e:
        logger.error(f"Failed to bind UDP port {udp_port}: {e}")
        logger.error("Is another server instance running?")
        return

    buffer_size = 65536

    while not shutdown_flag.is_set():
        try:
            data, addr = sock.recvfrom(buffer_size)
        except socket.timeout:
            continue
        except OSError:
            if shutdown_flag.is_set():
                break
            continue

        if len(data) < 12:
            continue

        # Parse header: srate (int32), nch (int32), bps (int32)
        header = struct.unpack("iii", data[:12])
        srate, nch, bps = header

        # ── Control frame detection ──
        if nch == CONTROL_RESET_NCH:
            logger.info("Received reset control frame (playback state change).")
            with buffer_lock:
                audio_buffer = np.array([], dtype=np.float32)
            if subtitle_mgr:
                subtitle_mgr.reset()
            continue

        pcm_data = data[12:]

        # ── Audio data processing ──
        if bps == 16 and len(pcm_data) > 0:
            samples = np.frombuffer(pcm_data, dtype=np.int16).astype(np.float32) / 32768.0

            # Convert to mono if stereo
            if nch == 2:
                samples = samples.reshape(-1, 2).mean(axis=1)

            # Resample to 16kHz
            target_rate = config.audio.target_sample_rate
            if srate != target_rate and len(samples) > 0:
                num_samples = max(1, int(len(samples) * target_rate / srate))
                samples = scipy.signal.resample(samples, num_samples)

            with buffer_lock:
                audio_buffer = np.concatenate((audio_buffer, samples))

            with udp_time_lock:
                last_udp_time = time.time()

    sock.close()
    logger.info("UDP receiver stopped.")


# ── Audio Processing Loop ────────────────────────────────────────────────

def process_loop():
    """Thread: process audio buffer through VAD → Whisper → Translator pipeline."""
    global audio_buffer

    # Wait a moment for the Whisper model to load before starting
    time.sleep(0.5)

    logger.info("Audio processing loop started.")

    while not shutdown_flag.is_set():
        # ── Check for UDP timeout (fallback reset) ──
        with udp_time_lock:
            if time.time() - last_udp_time > config.audio.udp_timeout_seconds:
                with buffer_lock:
                    if len(audio_buffer) > 0:
                        logger.debug("UDP timeout: resetting audio buffer.")
                        audio_buffer = np.array([], dtype=np.float32)
                if subtitle_mgr:
                    subtitle_mgr.reset()

        # ── Extract chunk from buffer ──
        chunk = None
        min_samples = int(config.audio.min_chunk_duration * config.audio.target_sample_rate)
        max_samples = int(config.audio.max_chunk_duration * config.audio.target_sample_rate)
        overlap_samples = int(config.audio.overlap_duration * config.audio.target_sample_rate)

        with buffer_lock:
            if len(audio_buffer) >= min_samples:
                chunk_len = min(len(audio_buffer), max_samples)
                chunk = audio_buffer[:chunk_len].copy()
                # Keep overlap for next iteration
                keep_start = max(0, chunk_len - overlap_samples)
                audio_buffer = audio_buffer[keep_start:]

        if chunk is None or len(chunk) == 0:
            time.sleep(0.1)
            continue

        # ── VAD: check for speech ──
        vad_cfg = config.vad
        if not has_speech(
            chunk,
            sample_rate=config.audio.target_sample_rate,
            threshold=vad_cfg.threshold,
            min_speech_duration_ms=vad_cfg.min_speech_duration_ms,
        ):
            # No speech detected — if nothing new has been said recently, clear subtitle
            if subtitle_mgr:
                current = subtitle_mgr.get_current()
                if current is None:
                    # subtitle already cleared, nothing to do
                    pass
            continue

        # ── Extract speech segments ──
        speech_segments = get_speech_timestamps(
            chunk,
            sample_rate=config.audio.target_sample_rate,
            threshold=vad_cfg.threshold,
            min_speech_duration_ms=vad_cfg.min_speech_duration_ms,
            min_silence_duration_ms=vad_cfg.min_silence_duration_ms,
        )

        if not speech_segments:
            continue

        # Concatenate all speech segments for Whisper
        speech_parts = []
        for start_ms, end_ms in speech_segments:
            start_idx = int(start_ms / 1000 * config.audio.target_sample_rate)
            end_idx = int(end_ms / 1000 * config.audio.target_sample_rate)
            start_idx = max(0, start_idx)
            end_idx = min(len(chunk), end_idx)
            if end_idx > start_idx:
                speech_parts.append(chunk[start_idx:end_idx])

        if not speech_parts:
            continue

        speech_audio = np.concatenate(speech_parts)

        # ── Whisper Transcription ──
        try:
            # Build transcribe kwargs from config
            transcribe_kwargs = {
                "beam_size": config.whisper.beam_size,
                "task": "transcribe",
            }
            # Language hint: None = auto-detect, or set like "en", "ja", "zh"
            if config.whisper.language:
                transcribe_kwargs["language"] = config.whisper.language

            segments, info = whisper_model.transcribe(speech_audio, **transcribe_kwargs)
            transcription = " ".join([seg.text for seg in segments]).strip()

            if not transcription:
                continue

            src_lang = info.language
            logger.info(f"Transcribed [{src_lang}]: {transcription[:80]}")

        except Exception as e:
            logger.error(f"Whisper transcription failed: {e}", exc_info=True)
            continue

        # ── Translation ──
        target_lang = config.translator.target_lang
        translated = None

        if config.translator.backend == "none" or src_lang == target_lang:
            # Directly use transcription
            translated = transcription
        else:
            try:
                translated = translator.translate(transcription, source_lang=src_lang, target_lang=target_lang)
            except Exception as e:
                logger.error(f"Translation failed: {e}", exc_info=True)
                translated = None

        if translated:
            logger.info(f"Translated [{target_lang}]: {translated[:80]}")
            if subtitle_mgr:
                subtitle_mgr.update(translated)
        elif config.translator.backend != "none" and src_lang != target_lang:
            # Translation failed — fallback to original transcription
            logger.warning("Translation failed, falling back to original transcription.")
            if subtitle_mgr:
                subtitle_mgr.update(transcription)


# ── Flask Routes ─────────────────────────────────────────────────────────

@app.route("/subtitle", methods=["GET"])
def get_subtitle():
    """Get the current subtitle. Returns {"text": "..."} or {"text": ""}."""
    text = ""
    if subtitle_mgr:
        current = subtitle_mgr.get_current()
        if current:
            text = current
    return jsonify({"text": text})


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    with buffer_lock:
        buffer_len = len(audio_buffer)
    with udp_time_lock:
        seconds_since_last_udp = time.time() - last_udp_time

    return jsonify({
        "status": "ok",
        "whisper_model": config.whisper.model_size,
        "translation_backend": config.translator.backend,
        "target_lang": config.translator.target_lang,
        "audio_buffer_samples": buffer_len,
        "seconds_since_last_udp": round(seconds_since_last_udp, 1),
        "subtitle_active": subtitle_mgr.get_current() is not None if subtitle_mgr else False,
    })


@app.route("/config", methods=["GET", "PUT"])
def config_endpoint():
    """
    GET:  view current configuration (with API key redacted).
    PUT:  hot-reload configuration. Only updates translation settings and subtitle settings.
          Whisper model changes require a restart.
    """
    global translator, config

    if request.method == "GET":
        return jsonify(config.to_dict())

    elif request.method == "PUT":
        if not request.is_json:
            return jsonify({"error": "Request must be JSON"}), 400

        new_data = request.get_json()

        # Update translator settings
        if "translator" in new_data:
            t = new_data["translator"]
            if "backend" in t:
                config.translator.backend = t["backend"]
            if "target_lang" in t:
                config.translator.target_lang = t["target_lang"]
            if "ollama_base_url" in t:
                config.translator.ollama_base_url = t["ollama_base_url"]
            if "ollama_model" in t:
                config.translator.ollama_model = t["ollama_model"]
            if "api_base_url" in t:
                config.translator.api_base_url = t["api_base_url"]
            if "api_key" in t:
                config.translator.api_key = t["api_key"]
            if "api_model" in t:
                config.translator.api_model = t["api_model"]

            # Re-create translator with new settings
            translator = create_translator(config)
            logger.info(f"Translator reconfigured: backend={config.translator.backend}")

        # Update subtitle settings
        if "subtitle" in new_data:
            s = new_data["subtitle"]
            if "max_idle_seconds" in s:
                config.subtitle.max_idle_seconds = float(s["max_idle_seconds"])
                subtitle_mgr.max_idle_seconds = config.subtitle.max_idle_seconds

        return jsonify({"status": "ok", "message": "Configuration updated."})


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    global config, translator, subtitle_mgr, whisper_model

    # Load configuration
    config = load_config()
    logger.info(f"Configuration loaded from {DEFAULT_CONFIG_PATH}")
    logger.info(f"  Whisper model: {config.whisper.model_size} on {config.whisper.device}")
    logger.info(f"  Translation: backend={config.translator.backend}, target={config.translator.target_lang}")
    logger.info(f"  VAD: threshold={config.vad.threshold}")
    logger.info(f"  Subtitle: max_idle={config.subtitle.max_idle_seconds}s")

    # ── Load Whisper Model ──
    logger.info(f"Loading Whisper model '{config.whisper.model_size}' on {config.whisper.device}...")
    logger.info("This may take a while on first run (downloading model files)...")

    from faster_whisper import WhisperModel
    whisper_model = WhisperModel(
        config.whisper.model_size,
        device=config.whisper.device,
        compute_type=config.whisper.compute_type,
    )
    logger.info("Whisper model loaded successfully.")

    # ── Initialize Translator ──
    translator = create_translator(config)

    # ── Initialize Subtitle Manager ──
    subtitle_mgr = SubtitleManager(max_idle_seconds=config.subtitle.max_idle_seconds)

    # ── Start Threads ──
    threading.Thread(target=udp_receiver, daemon=True, name="udp-receiver").start()
    threading.Thread(target=process_loop, daemon=True, name="audio-processor").start()

    # ── Start Flask ──
    logger.info(f"Starting subtitle API server on http://{config.server.http_ip}:{config.server.http_port}")
    logger.info("Ready. Open PotPlayer to begin real-time translation.")
    print()  # blank line for readability

    try:
        app.run(
            host=config.server.http_ip,
            port=config.server.http_port,
            threaded=True,
            debug=False,
            use_reloader=False,
        )
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        shutdown_flag.set()


if __name__ == "__main__":
    main()
