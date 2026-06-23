"""
Translation pipeline with pluggable backends.

Supports three modes:
  - "none"  → NoopTranslator (pass-through, no translation)
  - "ollama"→ OllamaTranslator (local, via Ollama's OpenAI-compatible endpoint)
  - "api"   → OpenAICompatTranslator (cloud, any OpenAI-compatible provider)
"""

import logging
from abc import ABC, abstractmethod
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# ── System Prompts (tuned for subtitle translation) ──────────────────────

SYSTEM_PROMPT_ZH = (
    "你是一个专业字幕翻译。将输入的文本翻译成简体中文。"
    "规则：\n"
    "- 只输出翻译结果，不要添加任何解释、注释或额外内容\n"
    "- 保持口语化、自然的表达，像日常对话一样\n"
    "- 保持原文的语气和情感（惊讶、疑问、愤怒等）\n"
    "- 不要添加敬语或过度礼貌的表达\n"
    "- 如果原文有歧义，选择最符合上下文的理解\n"
    "- 人名、地名保留原文，不翻译"
)

SYSTEM_PROMPT_EN = (
    "You are a professional subtitle translator. Translate the input text into natural, "
    "fluent English.\n"
    "Rules:\n"
    "- Output ONLY the translation, no explanations, notes, or extra content\n"
    "- Use natural, conversational English as spoken in everyday life\n"
    "- Preserve the original tone and emotion (surprise, question, anger, etc.)\n"
    "- Match the register: casual speech stays casual, formal stays formal\n"
    "- If the original is ambiguous, choose the most contextually appropriate reading\n"
    "- Keep proper names (people, places) in their original form"
)


def get_system_prompt(target_lang: str) -> str:
    """Return the appropriate system prompt for the target language."""
    if target_lang == "zh":
        return SYSTEM_PROMPT_ZH
    else:
        # Default to English prompt for all other target languages
        return SYSTEM_PROMPT_EN


# ── Abstract Base ────────────────────────────────────────────────────────

class BaseTranslator(ABC):
    """Abstract translation interface."""

    @abstractmethod
    def translate(self, text: str, source_lang: str, target_lang: str) -> Optional[str]:
        """
        Translate text from source_lang to target_lang.

        Returns translated text, or None on failure.
        """
        ...


# ── No-op Translator ─────────────────────────────────────────────────────

class NoopTranslator(BaseTranslator):
    """
    Pass-through translator: returns text unchanged.

    Used when translation backend is "none", or when source_lang == target_lang.
    """

    def translate(self, text: str, source_lang: str, target_lang: str) -> Optional[str]:
        return text


# ── Ollama Translator (local) ────────────────────────────────────────────

class OllamaTranslator(BaseTranslator):
    """
    Translation via local Ollama instance.

    Ollama's /v1/chat/completions endpoint is OpenAI-compatible.
    """

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "qwen2.5:1.5b"):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._chat_url = f"{self.base_url}/v1/chat/completions"
        logger.info(f"Ollama translator initialized: model={model}, url={self._chat_url}")

    def translate(self, text: str, source_lang: str, target_lang: str) -> Optional[str]:
        if not text or not text.strip():
            return text

        system_prompt = get_system_prompt(target_lang)
        user_message = f"Translate to {target_lang}:\n{text}"

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "temperature": 0.1,
            "max_tokens": 256,
        }

        try:
            resp = requests.post(self._chat_url, json=payload, timeout=15)
            if resp.status_code == 200:
                result = resp.json()
                translation = result["choices"][0]["message"]["content"].strip()
                return translation
            else:
                logger.warning(f"Ollama translation failed: HTTP {resp.status_code} — {resp.text[:200]}")
                return None
        except requests.exceptions.ConnectionError:
            logger.warning("Ollama is not running. Start it with: ollama serve")
            return None
        except Exception as e:
            logger.warning(f"Ollama translation error: {e}")
            return None


# ── OpenAI-Compatible API Translator (cloud) ─────────────────────────────

class OpenAICompatTranslator(BaseTranslator):
    """
    Translation via any OpenAI-compatible chat completions API.

    Works with: OpenAI, DeepSeek, Groq, OpenRouter, together.ai, SiliconFlow, etc.
    Just configure base_url, api_key, and model.
    """

    def __init__(
        self,
        base_url: str = "https://api.openai.com/v1",
        api_key: str = "",
        model: str = "gpt-4o-mini",
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self._chat_url = f"{self.base_url}/chat/completions"
        logger.info(f"API translator initialized: model={model}, url={self._chat_url}")

    def translate(self, text: str, source_lang: str, target_lang: str) -> Optional[str]:
        if not text or not text.strip():
            return text

        if not self.api_key:
            logger.warning("No API key configured. Set TRANSLATION_API_KEY env var.")
            return None

        system_prompt = get_system_prompt(target_lang)
        user_message = f"Translate to {target_lang}:\n{text}"

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "temperature": 0.1,
            "max_tokens": 256,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            resp = requests.post(self._chat_url, json=payload, headers=headers, timeout=15)
            if resp.status_code == 200:
                result = resp.json()
                translation = result["choices"][0]["message"]["content"].strip()
                return translation
            else:
                logger.warning(f"API translation failed: HTTP {resp.status_code} — {resp.text[:200]}")
                return None
        except requests.exceptions.Timeout:
            logger.warning("API translation timeout (>15s). Check network or use a faster model.")
            return None
        except Exception as e:
            logger.warning(f"API translation error: {e}")
            return None


# ── Factory ──────────────────────────────────────────────────────────────

def create_translator(config) -> BaseTranslator:
    """
    Create a translator instance based on configuration.

    Args:
        config: Config object from config.py.

    Returns:
        A BaseTranslator instance.
    """
    backend = config.translator.backend

    if backend == "none":
        logger.info("Translation disabled (backend=none). Outputting transcription as-is.")
        return NoopTranslator()

    elif backend == "ollama":
        return OllamaTranslator(
            base_url=config.translator.ollama_base_url,
            model=config.translator.ollama_model,
        )

    elif backend == "api":
        api_key = config.translator.api_key
        if not api_key:
            logger.warning(
                "API backend selected but no API key found. "
                "Set TRANSLATION_API_KEY env var or api_key in config.yaml."
            )
        return OpenAICompatTranslator(
            base_url=config.translator.api_base_url,
            api_key=api_key,
            model=config.translator.api_model,
        )

    else:
        logger.warning(f"Unknown translation backend '{backend}'. Falling back to noop.")
        return NoopTranslator()
