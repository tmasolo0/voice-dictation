"""LLMManager — коррекция текста через Qwen2.5 (CTranslate2 Generator)."""

import logging
import threading

from core.config_manager import APP_DIR

log = logging.getLogger(__name__)

MODELS_DIR = APP_DIR / "models"

SYSTEM_PROMPT = (
    "Исправь пунктуацию, капитализацию и очевидные ошибки распознавания речи в тексте. "
    "Верни ТОЛЬКО исправленный текст. Не добавляй пояснений. Не меняй смысл и слова."
)


class LLMManager:
    """Загрузка и использование LLM для постобработки текста."""

    def __init__(self, config):
        self._config = config
        self._generator = None
        self._tokenizer = None
        self._lock = threading.Lock()

    @property
    def is_ready(self) -> bool:
        return self._generator is not None and self._tokenizer is not None

    @property
    def model_dir(self):
        model_name = self._config.get('llm', 'model', default='qwen2.5-1.5b-ct2')
        return MODELS_DIR / model_name

    def model_exists(self) -> bool:
        return (self.model_dir / "model.bin").exists()

    def load_model(self):
        """Загрузка Generator + tokenizer."""
        with self._lock:
            if self._generator is not None:
                return

            model_path = self.model_dir
            if not (model_path / "model.bin").exists():
                log.warning("LLM model not found: %s", model_path)
                return

            device = self._config.get('llm', 'device', default='cuda')
            compute_type = self._config.get('llm', 'compute_type', default='int8_float16')

            try:
                import ctranslate2
                from transformers import AutoTokenizer

                log.info("Loading LLM: %s (device=%s, compute=%s)", model_path, device, compute_type)

                self._generator = ctranslate2.Generator(
                    str(model_path),
                    device=device,
                    compute_type=compute_type,
                )

                self._tokenizer = AutoTokenizer.from_pretrained(
                    str(model_path),
                    trust_remote_code=False,
                )

                log.info("LLM loaded successfully")
            except Exception as e:
                log.exception("Failed to load LLM: %s", e)
                self._generator = None
                self._tokenizer = None

    def unload_model(self):
        """Выгрузка модели, освобождение VRAM."""
        with self._lock:
            if self._generator is None:
                return
            log.info("Unloading LLM")
            del self._generator
            del self._tokenizer
            self._generator = None
            self._tokenizer = None

            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except ImportError:
                pass

    def correct(self, text: str) -> str:
        """Коррекция текста через LLM. При ошибке — возвращает исходный text."""
        if not self.is_ready or not text.strip():
            return text

        try:
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ]

            prompt_text = self._tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )

            prompt_tokens = self._tokenizer.convert_ids_to_tokens(
                self._tokenizer.encode(prompt_text)
            )

            results = self._generator.generate_tokens(
                prompt_tokens,
                max_length=512,
                sampling_temperature=0.1,
                repetition_penalty=1.1,
                end_token=self._tokenizer.eos_token_id,
            )

            output_ids = []
            for token_result in results:
                if token_result.token_id == self._tokenizer.eos_token_id:
                    break
                output_ids.append(token_result.token_id)

            corrected = self._tokenizer.decode(output_ids, skip_special_tokens=True).strip()

            if not corrected:
                return text

            return corrected

        except Exception as e:
            log.warning("LLM correction failed: %s", e)
            return text
