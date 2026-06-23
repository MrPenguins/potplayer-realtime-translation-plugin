"""
Configuration management for PotPlayer Realtime Translation Plugin.

Priority: environment variables > config.yaml > code defaults.
API keys should always be set via environment variables, not in config.yaml.
"""

import os
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

CONFIG_DIR = Path(__file__).parent
DEFAULT_CONFIG_PATH = CONFIG_DIR / "config.yaml"


@dataclass
class WhisperConfig:
    """faster-whisper model settings."""
    model_size: str = "small"          # tiny, small, medium, large-v3, or custom HF path
    device: str = "cuda"               # cuda or cpu
    compute_type: str = "float16"      # float16, int8_float16, int8
    beam_size: int = 5
    language: Optional[str] = None     # source language: None=auto-detect, "en", "ja", "zh", etc.
    # Custom model: set model_size to a HF repo path like "guillaumeklay/faster-whisper-small-vi"
    # and it will be used directly.


@dataclass
class TranslatorConfig:
    """Translation backend settings."""
    # Backend: "ollama" (local), "api" (OpenAI-compatible cloud), "none" (no translation)
    backend: str = "api"

    # Target language for translation
    target_lang: str = "zh"            # zh, en, ja, etc.

    # Used when source == target (no translation needed)
    # Set to "none" backend to skip all translation

    # Ollama settings (when backend = "ollama")
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:1.5b"

    # API settings (when backend = "api", OpenAI-compatible)
    api_base_url: str = "https://api.openai.com/v1"
    api_key: str = ""                  # USE ENV VAR: TRANSLATION_API_KEY
    api_model: str = "gpt-4o-mini"


@dataclass
class VADConfig:
    """Silero VAD settings."""
    # Speech probability threshold (0.0-1.0). Higher = stricter.
    threshold: float = 0.5

    # Minimum speech duration in ms. Segments shorter than this are treated as noise.
    min_speech_duration_ms: int = 250

    # Minimum silence duration in ms. Silence shorter than this won't split a sentence.
    min_silence_duration_ms: int = 500

    # Audio sample rate expected by Silero VAD (fixed at 16000)
    sample_rate: int = 16000


@dataclass
class SubtitleConfig:
    """Subtitle display settings."""
    # How many seconds without new subtitle before the overlay clears
    max_idle_seconds: float = 3.0

    # Fade-out animation duration in ms (for the overlay)
    fade_out_ms: int = 500

    # Font settings
    font_size: int = 28
    font_family: str = "Microsoft YaHei, Arial"

    # Window position offset from bottom (pixels)
    bottom_offset: int = 150

    # Window dimensions
    window_width: int = 800
    window_height: int = 100


@dataclass
class AudioConfig:
    """Audio processing settings."""
    # Chunk duration to accumulate before processing (seconds)
    min_chunk_duration: float = 1.0

    # Maximum chunk duration sent to Whisper (seconds)
    max_chunk_duration: float = 5.0

    # Overlap between consecutive chunks to avoid cutting words (seconds)
    overlap_duration: float = 0.5

    # Target sample rate for Whisper
    target_sample_rate: int = 16000

    # Timeout in seconds: if no UDP data arrives in this window, reset all buffers
    # This acts as a fallback for playback state detection
    udp_timeout_seconds: float = 3.0


@dataclass
class ServerConfig:
    """Server network settings."""
    udp_ip: str = "127.0.0.1"
    udp_port: int = 12345
    http_ip: str = "127.0.0.1"
    http_port: int = 5000


@dataclass
class Config:
    """Top-level configuration aggregating all sub-configs."""
    whisper: WhisperConfig = field(default_factory=WhisperConfig)
    translator: TranslatorConfig = field(default_factory=TranslatorConfig)
    vad: VADConfig = field(default_factory=VADConfig)
    subtitle: SubtitleConfig = field(default_factory=SubtitleConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    server: ServerConfig = field(default_factory=ServerConfig)

    # ---

    @classmethod
    def from_yaml(cls, path: Path = DEFAULT_CONFIG_PATH) -> "Config":
        """Load config from a YAML file, with env var overrides applied after."""
        config = cls()

        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}

            if "whisper" in data:
                for k, v in data["whisper"].items():
                    if hasattr(config.whisper, k):
                        setattr(config.whisper, k, v)
            if "translator" in data:
                for k, v in data["translator"].items():
                    if hasattr(config.translator, k):
                        setattr(config.translator, k, v)
            if "vad" in data:
                for k, v in data["vad"].items():
                    if hasattr(config.vad, k):
                        setattr(config.vad, k, v)
            if "subtitle" in data:
                for k, v in data["subtitle"].items():
                    if hasattr(config.subtitle, k):
                        setattr(config.subtitle, k, v)
            if "audio" in data:
                for k, v in data["audio"].items():
                    if hasattr(config.audio, k):
                        setattr(config.audio, k, v)
            if "server" in data:
                for k, v in data["server"].items():
                    if hasattr(config.server, k):
                        setattr(config.server, k, v)

        # Apply environment variable overrides
        config._apply_env_overrides()
        return config

    def _apply_env_overrides(self):
        """Override config values from environment variables (highest priority)."""
        # Translator
        if os.getenv("TRANSLATION_BACKEND"):
            self.translator.backend = os.getenv("TRANSLATION_BACKEND")
        if os.getenv("TRANSLATION_TARGET_LANG"):
            self.translator.target_lang = os.getenv("TRANSLATION_TARGET_LANG")
        if os.getenv("TRANSLATION_API_KEY"):
            self.translator.api_key = os.getenv("TRANSLATION_API_KEY")
        if os.getenv("TRANSLATION_API_BASE_URL"):
            self.translator.api_base_url = os.getenv("TRANSLATION_API_BASE_URL")
        if os.getenv("TRANSLATION_API_MODEL"):
            self.translator.api_model = os.getenv("TRANSLATION_API_MODEL")
        if os.getenv("OLLAMA_BASE_URL"):
            self.translator.ollama_base_url = os.getenv("OLLAMA_BASE_URL")
        if os.getenv("OLLAMA_MODEL"):
            self.translator.ollama_model = os.getenv("OLLAMA_MODEL")

        # Whisper
        if os.getenv("WHISPER_MODEL"):
            self.whisper.model_size = os.getenv("WHISPER_MODEL")
        if os.getenv("WHISPER_DEVICE"):
            self.whisper.device = os.getenv("WHISPER_DEVICE")
        if os.getenv("WHISPER_LANGUAGE"):
            self.whisper.language = os.getenv("WHISPER_LANGUAGE")

        # Server
        if os.getenv("UDP_PORT"):
            self.server.udp_port = int(os.getenv("UDP_PORT"))
        if os.getenv("HTTP_PORT"):
            self.server.http_port = int(os.getenv("HTTP_PORT"))

        # Subtitle
        if os.getenv("SUBTITLE_MAX_IDLE"):
            self.subtitle.max_idle_seconds = float(os.getenv("SUBTITLE_MAX_IDLE"))
        if os.getenv("SUBTITLE_FONT_SIZE"):
            self.subtitle.font_size = int(os.getenv("SUBTITLE_FONT_SIZE"))

    def to_dict(self) -> dict:
        """Serialize to dict (useful for /config API endpoint, with api_key redacted)."""
        return {
            "whisper": {
                "model_size": self.whisper.model_size,
                "device": self.whisper.device,
                "compute_type": self.whisper.compute_type,
                "language": self.whisper.language,
            },
            "translator": {
                "backend": self.translator.backend,
                "target_lang": self.translator.target_lang,
                "ollama_base_url": self.translator.ollama_base_url,
                "ollama_model": self.translator.ollama_model,
                "api_base_url": self.translator.api_base_url,
                "api_model": self.translator.api_model,
                "api_key": "***" if self.translator.api_key else "(not set)",
            },
            "vad": {
                "threshold": self.vad.threshold,
                "min_speech_duration_ms": self.vad.min_speech_duration_ms,
                "min_silence_duration_ms": self.vad.min_silence_duration_ms,
            },
            "subtitle": {
                "max_idle_seconds": self.subtitle.max_idle_seconds,
                "font_size": self.subtitle.font_size,
            },
            "audio": {
                "min_chunk_duration": self.audio.min_chunk_duration,
                "max_chunk_duration": self.audio.max_chunk_duration,
                "overlap_duration": self.audio.overlap_duration,
            },
            "server": {
                "udp_port": self.server.udp_port,
                "http_port": self.server.http_port,
            },
        }


# Convenience: load the default config on import
def load_config(path: Optional[Path] = None) -> Config:
    """Load configuration from path or default location."""
    return Config.from_yaml(path or DEFAULT_CONFIG_PATH)
