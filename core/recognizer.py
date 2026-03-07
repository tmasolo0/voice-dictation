"""Recognizer — распознавание речи через Whisper."""

import gc
import logging
import re
import sys
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
    "thanks for watching", "thank you for watching",
    "thanks for listening", "thank you for listening",
    "please subscribe", "like and subscribe",
    "see you next time", "the end",
    "silence", "no speech", "inaudible",
    "[music]", "(music)", "[applause]", "[laughter]",
    "субтитры сделал", "субтитры выполнены",
    "подписывайтесь на канал", "спасибо за просмотр",
    "продолжение следует",
]


class Recognizer:
    """Транскрипция аудио через faster-whisper."""

    def __init__(self, event_bus, model_manager, config):
        self._bus = event_bus
        self._models = model_manager
        self._config = config
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

    def _transcribe(self, audio_data):
        """Транскрипция аудио (фоновый поток)."""
        try:
            model = self._models.get_model()
            if model is None:
                self._bus.error_occurred.emit("Recognizer", "Модель не загружена")
                return

            start = time.time()
            beam_size = self._config.get('recognition', 'beam_size', default=5)
            temperature = self._config.get('recognition', 'temperature', default=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0])
            use_hotwords = self._config.get('recognition', 'use_hotwords', default=True)
            hotwords = self._config.get_hotwords() if use_hotwords else ""

            language = self._config.get('recognition', 'language', default=None)
            if not language or language == 'auto':
                language = None
            initial_prompt = self._config.get('recognition', 'initial_prompt', default='') or None

            log.info("transcribe_params: lang=%s temperature=%s beam=%d model=%s frozen=%s",
                     language, temperature, beam_size,
                     self._models.model_name, getattr(sys, 'frozen', False))

            vad_params = {
                'threshold': self._config.get('vad', 'threshold', default=0.5),
                'min_speech_duration_ms': self._config.get('vad', 'min_speech_ms', default=250),
                'min_silence_duration_ms': self._config.get('vad', 'min_silence_ms', default=500),
            }

            segments, info = model.transcribe(
                audio_data,
                language=language,
                vad_filter=True,
                vad_parameters=vad_params,
                initial_prompt=initial_prompt,
                hotwords=hotwords or None,
                condition_on_previous_text=self._config.get('recognition', 'condition_on_previous_text', default=False),
                beam_size=beam_size,
                temperature=temperature,
                compression_ratio_threshold=self._config.get('recognition', 'compression_ratio_threshold', default=2.4),
                log_prob_threshold=self._config.get('recognition', 'log_prob_threshold', default=-1.0),
                no_speech_threshold=self._config.get('recognition', 'no_speech_threshold', default=0.6),
                repetition_penalty=self._config.get('recognition', 'repetition_penalty', default=1.2),
                no_repeat_ngram_size=self._config.get('recognition', 'no_repeat_ngram_size', default=3),
                suppress_tokens=self._config.get('recognition', 'suppress_tokens', default=[-1]),
                hallucination_silence_threshold=self._config.get('recognition', 'hallucination_silence_threshold', default=2.0),
            )

            # Фильтрация сегментов по качеству (защита от галлюцинаций)
            no_speech_thr = self._config.get('recognition', 'no_speech_threshold', default=0.6)
            logprob_thr = self._config.get('recognition', 'log_prob_threshold', default=-1.0)
            compress_thr = self._config.get('recognition', 'compression_ratio_threshold', default=2.4)

            filtered_texts = []
            for s in segments:
                if s.no_speech_prob > no_speech_thr:
                    log.debug("skip segment no_speech=%.2f logprob=%.2f: '%s'",
                              s.no_speech_prob, s.avg_logprob, s.text[:60])
                    continue
                if s.avg_logprob < logprob_thr:
                    log.debug("skip segment logprob=%.2f: '%s'", s.avg_logprob, s.text[:60])
                    continue
                if s.compression_ratio > compress_thr:
                    log.debug("skip segment compress=%.1f: '%s'", s.compression_ratio, s.text[:60])
                    continue
                filtered_texts.append(s.text)

            text = "".join(filtered_texts).strip()

            if text and self._is_hallucination(text):
                log.warning("hallucination filtered: '%s'", text[:100])
                text = ""

            text = self._apply_replacements(text)
            elapsed = time.time() - start

            metadata = {
                'language': info.language,
                'language_probability': info.language_probability,
                'elapsed': elapsed,
            }

            # Очистка ссылок на результаты transcribe
            del segments, info

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
        """Детекция типичных шаблонов галлюцинаций Whisper."""
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
