"""Recognizer — распознавание речи через Whisper."""

import gc
import re
import time
import threading
from concurrent.futures import ThreadPoolExecutor


class Recognizer:
    """Транскрипция аудио через faster-whisper, с поддержкой режима перевода."""

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
        with self._busy_lock:
            if self._busy:
                print("Транскрипция уже выполняется — пропускаем")
                return
            self._busy = True
        self._executor.submit(self._transcribe, audio_data)

    def _transcribe(self, audio_data):
        """Транскрипция аудио (фоновый поток)."""
        try:
            model = self._models.get_model()
            if model is None:
                self._bus.error_occurred.emit("Recognizer", "Модель не загружена")
                return

            start = time.time()
            translate_mode = self._config.get('dictation', 'translate_to_english', default=False)
            beam_size = self._config.get('recognition', 'beam_size', default=5)
            use_hotwords = self._config.get('recognition', 'use_hotwords', default=True)
            hotwords = self._config.get_hotwords() if use_hotwords else ""

            language = self._config.get('recognition', 'language', default=None) or None
            initial_prompt = self._config.get('recognition', 'initial_prompt', default='') or None

            if translate_mode:
                segments, info = model.transcribe(
                    audio_data,
                    language=language,
                    task="translate",
                    vad_filter=True,
                    initial_prompt=initial_prompt,
                    hotwords=hotwords or None,
                    condition_on_previous_text=self._config.get('recognition', 'condition_on_previous_text', default=False),
                    beam_size=beam_size,
                    repetition_penalty=self._config.get('recognition', 'repetition_penalty', default=1.2),
                    no_repeat_ngram_size=self._config.get('recognition', 'no_repeat_ngram_size', default=3),
                    suppress_tokens=self._config.get('recognition', 'suppress_tokens', default=[-1]),
                    hallucination_silence_threshold=self._config.get('recognition', 'hallucination_silence_threshold', default=2.0),
                )
            else:
                segments, info = model.transcribe(
                    audio_data,
                    language=language,
                    vad_filter=True,
                    initial_prompt=initial_prompt,
                    hotwords=hotwords or None,
                    condition_on_previous_text=self._config.get('recognition', 'condition_on_previous_text', default=False),
                    beam_size=beam_size,
                    temperature=self._config.get('recognition', 'temperature', default=0.3),
                    compression_ratio_threshold=self._config.get('recognition', 'compression_ratio_threshold', default=2.4),
                    log_prob_threshold=self._config.get('recognition', 'log_prob_threshold', default=-1.0),
                    no_speech_threshold=self._config.get('recognition', 'no_speech_threshold', default=0.6),
                    repetition_penalty=self._config.get('recognition', 'repetition_penalty', default=1.2),
                    no_repeat_ngram_size=self._config.get('recognition', 'no_repeat_ngram_size', default=3),
                    suppress_tokens=self._config.get('recognition', 'suppress_tokens', default=[-1]),
                    hallucination_silence_threshold=self._config.get('recognition', 'hallucination_silence_threshold', default=2.0),
                )

            text = "".join([s.text for s in segments]).strip()
            text = self._apply_replacements(text)
            elapsed = time.time() - start

            metadata = {
                'language': info.language,
                'language_probability': info.language_probability,
                'elapsed': elapsed,
                'translate_mode': translate_mode,
            }

            # Очистка ссылок на результаты transcribe
            del segments, info

            if text:
                mode_info = f"({metadata['language']})→EN" if translate_mode else f"({metadata['language']})"
                print(f"[{elapsed:.1f}с] {mode_info}: {text}")

            self._bus.text_recognized.emit(text, metadata)

            # Периодическая очистка VRAM
            self._transcription_count += 1
            if self._transcription_count % self._vram_cleanup_interval == 0:
                self._cleanup_vram()

        except Exception as e:
            print(f"Ошибка распознавания: {e}")
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
                print(f"VRAM cleanup после {self._transcription_count} транскрипций")
        except ImportError:
            pass

    def shutdown(self):
        """Завершить executor, подождать максимум 5 секунд."""
        self._executor.shutdown(wait=True, cancel_futures=True)
