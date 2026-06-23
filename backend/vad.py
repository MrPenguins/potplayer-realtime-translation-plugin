"""
Voice Activity Detection wrapper using Silero VAD.

Filters silence and noise from audio before feeding it to Whisper,
preventing hallucinated transcriptions on background noise.
"""

import logging
from typing import List, Tuple

import numpy as np
import torch

logger = logging.getLogger(__name__)

# Lazy-loaded global model (singleton, GPU if available)
_vad_model = None


def _get_device() -> str:
    """Resolve torch device. Silero VAD also runs well on CPU if no GPU."""
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def _load_model():
    """Load Silero VAD model (singleton, lazy)."""
    global _vad_model
    if _vad_model is not None:
        return _vad_model

    try:
        from silero_vad import load_silero_vad
        _vad_model = load_silero_vad()
        logger.info("Silero VAD model loaded successfully.")
    except ImportError:
        raise ImportError(
            "silero-vad is not installed. Run: pip install silero-vad"
        )
    return _vad_model


def get_speech_timestamps(
    audio: np.ndarray,
    sample_rate: int = 16000,
    threshold: float = 0.5,
    min_speech_duration_ms: int = 250,
    min_silence_duration_ms: int = 500,
) -> List[Tuple[float, float]]:
    """
    Detect speech segments in an audio array.

    Args:
        audio: float32 numpy array of audio samples.
        sample_rate: sample rate of the audio (must be 16000 for Silero VAD).
        threshold: speech probability threshold (0.0–1.0).
        min_speech_duration_ms: shorter speech chunks are treated as noise.
        min_silence_duration_ms: shorter silences don't split a sentence.

    Returns:
        List of (start_ms, end_ms) tuples for each detected speech segment.
        Returns empty list if no speech detected.
    """
    if len(audio) == 0:
        return []

    model = _load_model()
    device = _get_device()

    # Convert numpy array to torch tensor
    if isinstance(audio, np.ndarray):
        audio_tensor = torch.from_numpy(audio.copy()).float()
    else:
        audio_tensor = torch.tensor(audio, dtype=torch.float32)

    # Ensure 1D
    if audio_tensor.ndim > 1:
        audio_tensor = audio_tensor.squeeze()

    if len(audio_tensor) == 0:
        return []

    # Get speech timestamps
    # silero-vad's get_speech_timestamps returns list of {'start': samples, 'end': samples}
    try:
        from silero_vad import get_speech_timestamps as silero_get_ts

        speech_ts = silero_get_ts(
            audio_tensor,
            model,
            threshold=threshold,
            sampling_rate=sample_rate,
            min_speech_duration_ms=min_speech_duration_ms,
            min_silence_duration_ms=min_silence_duration_ms,
        )
    except Exception as e:
        logger.warning(f"VAD processing failed: {e}. Returning full audio as speech.")
        return [(0.0, len(audio) / sample_rate * 1000)]

    # Convert to (ms, ms) format
    segments = []
    for ts in speech_ts:
        start_ms = ts["start"] / sample_rate * 1000
        end_ms = ts["end"] / sample_rate * 1000
        segments.append((start_ms, end_ms))

    return segments


def extract_speech(
    audio: np.ndarray,
    sample_rate: int = 16000,
    threshold: float = 0.5,
    min_speech_duration_ms: int = 250,
    min_silence_duration_ms: int = 500,
) -> np.ndarray:
    """
    Extract only speech portions from audio by concatenating all VAD-detected segments.

    Args:
        audio: float32 numpy array of audio samples.
        sample_rate: must be 16000 (Silero VAD requirement).
        threshold: speech probability threshold.
        min_speech_duration_ms: shorter chunks are noise.
        min_silence_duration_ms: shorter silences don't split.

    Returns:
        Float32 numpy array containing only speech audio.
        Returns empty array if no speech detected.
    """
    segments = get_speech_timestamps(
        audio,
        sample_rate=sample_rate,
        threshold=threshold,
        min_speech_duration_ms=min_speech_duration_ms,
        min_silence_duration_ms=min_silence_duration_ms,
    )

    if not segments:
        return np.array([], dtype=np.float32)

    # Concatenate all speech segments
    parts = []
    for start_ms, end_ms in segments:
        start_idx = int(start_ms / 1000 * sample_rate)
        end_idx = int(end_ms / 1000 * sample_rate)
        start_idx = max(0, start_idx)
        end_idx = min(len(audio), end_idx)
        if end_idx > start_idx:
            parts.append(audio[start_idx:end_idx])

    if not parts:
        return np.array([], dtype=np.float32)

    return np.concatenate(parts)


def has_speech(
    audio: np.ndarray,
    sample_rate: int = 16000,
    threshold: float = 0.5,
    min_speech_duration_ms: int = 250,
) -> bool:
    """
    Quick check: does this audio contain any speech?

    Useful for skipping processing entirely on silent chunks.
    """
    segments = get_speech_timestamps(
        audio,
        sample_rate=sample_rate,
        threshold=threshold,
        min_speech_duration_ms=min_speech_duration_ms,
        min_silence_duration_ms=100,  # short, we just want a yes/no
    )
    return len(segments) > 0
