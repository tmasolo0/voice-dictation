"""LLMManager — коррекция текста через Qwen2.5 (CTranslate2 Generator)."""

import logging
import os
import sys
import threading

from core.config_manager import APP_DIR

log = logging.getLogger(__name__)

MODELS_DIR = APP_DIR / "models"

def _ensure_cuda_libs():
    """Добавить пути к CUDA DLL (nvidia pip packages) если нужно."""
    for pkg_name in ("nvidia.cublas", "nvidia.cudnn"):
        try:
            pkg = __import__(pkg_name, fromlist=[""])
            # namespace packages have __path__ but __file__ is None
            pkg_dirs = list(getattr(pkg, "__path__", []))
            if not pkg_dirs:
                continue
            bin_dir = os.path.join(pkg_dirs[0], "bin")
            if not os.path.isdir(bin_dir):
                continue
            if bin_dir not in os.environ.get("PATH", ""):
                os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
                if sys.platform == "win32":
                    os.add_dll_directory(bin_dir)
                log.debug("Added CUDA DLL path: %s", bin_dir)
        except ImportError:
            pass


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
            compute_type = self._config.get('llm', 'compute_type', default='float32')

            try:
                _ensure_cuda_libs()
                import ctranslate2
                from transformers import AutoTokenizer

                # Попытка загрузки с fallback по compute_type
                fallback_types = [compute_type, "float32"]
                # Убираем дубликаты, сохраняя порядок
                seen = set()
                unique_types = []
                for ct in fallback_types:
                    if ct not in seen:
                        seen.add(ct)
                        unique_types.append(ct)

                tokenizer = AutoTokenizer.from_pretrained(
                    str(model_path),
                    trust_remote_code=False,
                )

                generator = None
                used_type = None
                for ct in unique_types:
                    try:
                        log.info("Loading LLM: %s (device=%s, compute=%s)", model_path, device, ct)
                        gen = ctranslate2.Generator(
                            str(model_path),
                            device=device,
                            compute_type=ct,
                        )
                    except ValueError as ve:
                        log.warning("compute_type %s not supported: %s", ct, ve)
                        continue

                    # Валидация: генерируем тестовые токены, проверяем что не все id=0
                    if not self._validate_generator(gen, tokenizer):
                        log.warning("compute_type %s produces garbage output, skipping", ct)
                        del gen
                        continue

                    generator = gen
                    used_type = ct
                    break

                if generator is None:
                    log.error("Failed to load LLM: no working compute_type found")
                    return

                self._generator = generator
                self._tokenizer = tokenizer

                log.info("LLM loaded successfully (compute_type=%s)", used_type)
            except Exception as e:
                log.exception("Failed to load LLM: %s", e)
                self._generator = None
                self._tokenizer = None

    @staticmethod
    def _validate_generator(generator, tokenizer) -> bool:
        """Проверка что генератор выдаёт осмысленный результат на chat template промпте."""
        try:
            # Используем полный chat template — как при реальной коррекции
            messages = [
                {"role": "system", "content": "Fix punctuation. Return ONLY corrected text."},
                {"role": "user", "content": "hello world how are you"},
            ]
            prompt = tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True,
            )
            test_tokens = tokenizer.convert_ids_to_tokens(
                tokenizer.encode(prompt)
            )
            results = generator.generate_batch(
                [test_tokens],
                max_length=20,
                sampling_temperature=0.1,
                repetition_penalty=1.1,
                end_token=[tokenizer.eos_token_id],
                include_prompt_in_result=False,
            )
            output_tokens = results[0].sequences[0]
            if not output_tokens:
                return False
            output_ids = tokenizer.convert_tokens_to_ids(output_tokens)
            if all(i == 0 for i in output_ids):
                return False
            return True
        except Exception as e:
            log.warning("LLM validation failed: %s", e)
            return False

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

    def correct(self, text: str, terms: list[str] | None = None) -> str:
        """Коррекция текста через LLM. При ошибке — возвращает исходный text."""
        if not self.is_ready or not text.strip():
            return text

        try:
            system_prompt = SYSTEM_PROMPT
            if terms:
                limited = terms[:150]
                system_prompt += (
                    "\nСловарь терминов (используй правильное написание): "
                    + ", ".join(limited) + "."
                )

            messages = [
                {"role": "system", "content": system_prompt},
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

            results = self._generator.generate_batch(
                [prompt_tokens],
                max_length=512,
                sampling_temperature=0.1,
                repetition_penalty=1.1,
                end_token=[self._tokenizer.eos_token_id],
                include_prompt_in_result=False,
            )

            output_tokens = results[0].sequences[0]
            output_ids = self._tokenizer.convert_tokens_to_ids(output_tokens)

            # Защита: если все id=0 — модель выдаёт мусор
            if output_ids and all(i == 0 for i in output_ids):
                log.warning("LLM output is all zeros, returning original text")
                return text

            corrected = self._tokenizer.decode(output_ids, skip_special_tokens=True).strip()

            if not corrected:
                return text

            return corrected

        except Exception as e:
            log.warning("LLM correction failed: %s", e)
            return text
