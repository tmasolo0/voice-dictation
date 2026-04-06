"""Recognizer — распознавание речи через Qwen3-ASR."""

import gc
import logging
import re
import time
import threading
from concurrent.futures import ThreadPoolExecutor

log = logging.getLogger(__name__)

_HALLUCINATION_RE = [
    re.compile(r'(.{8,}?)\1{2,}'),  # одна и та же фраза 3+ раз подряд
    re.compile(r'^\s*[.…♪♫«»\-\s]+\s*$'),  # только пунктуация/символы
]

# Одиночные слова-галлюцинации (весь текст = одно слово из этого набора)
_HALLUCINATION_WORDS = {
    "you", "i", "so", "uh", "um", "hmm", "huh", "ah", "oh",
    "bye", "goodbye", "hey", "the", "a", "is", "it", "and",
    "да", "нет", "ну", "а", "и", "о", "э",
}

# Фразы-галлюцинации (проверяются в коротких текстах <40 символов)
_HALLUCINATION_PHRASES = [
    "silence", "no speech", "inaudible",
    "[music]", "(music)", "[applause]", "[laughter]",
    "субтитры сделал", "субтитры выполнены",
    "подписывайтесь на канал", "спасибо за просмотр",
    "продолжение следует",
]

# Максимум терминов в system prompt
# Qwen3-ASR int4: длинный prompt (~200+ tokens) мешает распознаванию.
# 20 терминов ≈ 40-60 токенов — безопасный лимит.
MAX_SYSTEM_PROMPT_TERMS = 20


class Recognizer:
    """Транскрипция аудио через Qwen3-ASR."""

    def __init__(self, event_bus, model_manager, config, llm_manager=None):
        self._bus = event_bus
        self._models = model_manager
        self._config = config
        self._llm = llm_manager
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._busy = False
        self._busy_lock = threading.Lock()
        self._transcription_count = 0
        self._vram_cleanup_interval = config.get('recognition', 'vram_cleanup_interval', default=10)

        self._replacements = self._config.get_replacements()
        self._bus.audio_ready.connect(self._on_audio_ready)

    def _on_audio_ready(self, audio_data):
        """Получены аудиоданные — запустить транскрипцию если не занят."""
        log.info("audio_ready: len=%d", len(audio_data))
        with self._busy_lock:
            if self._busy:
                log.warning("Транскрипция уже выполняется — пропускаем")
                self._bus.error_occurred.emit("Recognizer", "Транскрипция занята")
                return
            self._busy = True
        try:
            self._executor.submit(self._transcribe, audio_data)
        except RuntimeError as e:
            log.error("executor.submit failed: %s", e)
            with self._busy_lock:
                self._busy = False
            self._bus.error_occurred.emit("Recognizer", str(e))

    def _build_system_prompt(self, terms: list[str]) -> str | None:
        """Построить system prompt с терминологией для ASR.

        Args:
            terms: список терминов из словарей

        Returns:
            System prompt строка или None если терминов нет.
        """
        # Пользовательский system prompt из настроек
        user_prompt = self._config.get('recognition', 'system_prompt', default='') or ''

        # Термины из словарей (ограничиваем количество)
        if terms:
            limited = terms[:MAX_SYSTEM_PROMPT_TERMS]
            terms_str = ", ".join(limited)
            terms_prompt = f"Термины: {terms_str}"
        else:
            terms_prompt = ""

        parts = [p for p in [user_prompt.strip(), terms_prompt] if p]
        return "\n".join(parts) if parts else None

    def _transcribe(self, audio_data):
        """Транскрипция аудио (фоновый поток)."""
        try:
            model = self._models.get_model()
            if model is None:
                self._bus.error_occurred.emit("Recognizer", "Модель не загружена")
                return

            start = time.time()

            llm_active = (self._llm and self._llm.is_ready
                          and self._config.get('llm', 'enabled', default=False))

            # Термины для system prompt
            use_hotwords = self._config.get('recognition', 'use_hotwords', default=True)
            terms = self._config.get_terms_list() if use_hotwords else []

            # Термины для LLM (если LLM активна)
            llm_terms = terms if llm_active else []

            # System prompt для ASR
            system_prompt = self._build_system_prompt(terms)

            language = self._config.get('recognition', 'language', default=None)
            if not language or language == 'auto':
                language = None

            log.info("transcribe: lang=%s model=%s system_prompt=%s",
                     language, self._models.model_name,
                     f"'{system_prompt[:50]}...'" if system_prompt and len(system_prompt) > 50
                     else repr(system_prompt))

            # Qwen3-ASR: единый вызов transcribe
            result = model.transcribe(
                audio_data,
                language=language,
                system_prompt=system_prompt,
            )

            text = result.text.strip()

            if text and self._is_hallucination(text):
                log.warning("hallucination filtered: '%s'", text[:100])
                text = ""

            # LLM-коррекция (если включена и модель загружена)
            if text and llm_active:
                try:
                    corrected = self._llm.correct(text, terms=llm_terms or None)
                    log.info("llm_correction: '%s' -> '%s'", text[:60], corrected[:60])
                    text = corrected
                except Exception as e:
                    log.warning("llm_correction fallback: %s", e)

            text = self._apply_replacements(text)
            elapsed = time.time() - start

            metadata = {
                'language': result.language,
                'language_probability': result.language_probability,
                'elapsed': elapsed,
            }

            log.info("[%.1fс] lang=%s text='%s'", elapsed, metadata['language'], text[:100] if text else '')

            self._bus.text_recognized.emit(text, metadata)

            # Периодическая очистка VRAM
            self._transcription_count += 1
            if self._transcription_count % self._vram_cleanup_interval == 0:
                self._cleanup_vram()

        except Exception as e:
            log.exception("Ошибка распознавания: %s", e)
            self._bus.error_occurred.emit("Recognizer", str(e))
        finally:
            with self._busy_lock:
                self._busy = False

    def _apply_replacements(self, text):
        """Пост-обработка: замена часто неверно распознанных терминов."""
        if not self._replacements:
            return text
        for wrong, correct in self._replacements.items():
            pattern = r'\b' + re.escape(wrong) + r'\b'
            text = re.sub(pattern, correct, text, flags=re.IGNORECASE)
        return text

    def _is_hallucination(self, text):
        """Детекция типичных шаблонов галлюцинаций."""
        stripped = text.strip()
        if len(stripped) < 3:
            return True
        lower = stripped.lower()
        # Одиночное слово-галлюцинация
        if lower in _HALLUCINATION_WORDS:
            return True
        # Короткий текст — проверяем фразы-галлюцинации
        if len(stripped) < 40:
            for phrase in _HALLUCINATION_PHRASES:
                if phrase in lower:
                    return True
        # Regex-паттерны (повторы, мусор)
        for pattern in _HALLUCINATION_RE:
            if pattern.search(stripped):
                return True
        return False

    def reload_replacements(self):
        """Перезагрузка словаря замен из файла."""
        self._replacements = self._config.get_replacements()

    def _cleanup_vram(self):
        """Периодическая очистка VRAM для предотвращения утечек."""
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                log.debug("VRAM cleanup после %d транскрипций", self._transcription_count)
        except ImportError:
            pass

    def shutdown(self):
        """Завершить executor, подождать максимум 5 секунд."""
        self._executor.shutdown(wait=True, cancel_futures=True)
