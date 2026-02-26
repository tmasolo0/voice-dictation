"""AudioCapture — захват аудио с микрофона."""

import threading
import numpy as np
import sounddevice as sd


SAMPLE_RATE = 16000
BLOCK_SIZE_SEC = 0.1


class AudioCapture:
    """Захват аудио через sounddevice, управляемый сигналами EventBus."""

    def __init__(self, event_bus, config):
        self._bus = event_bus
        self._config = config
        self._stream = None
        self._audio_data = []
        self._recording_event = threading.Event()
        self._lock = threading.Lock()

        self._bus.recording_start.connect(self._on_start)
        self._bus.recording_stop.connect(self._on_stop)

    def open_stream(self):
        """Открыть аудиопоток."""
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype='float32',
            callback=self._audio_callback,
            blocksize=int(SAMPLE_RATE * BLOCK_SIZE_SEC),
        )
        self._stream.start()

    def close_stream(self):
        """Закрыть аудиопоток."""
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def _audio_callback(self, indata, frames, time_info, status):
        """Callback sounddevice — вызывается из аудиопотока."""
        if self._recording_event.is_set():
            with self._lock:
                self._audio_data.append(indata.copy())

    def _on_start(self, hwnd):
        """Начало записи."""
        with self._lock:
            self._audio_data = []
        self._recording_event.set()

    def _on_stop(self):
        """Конец записи — собрать данные, обрезать тишину, нормализовать."""
        self._recording_event.clear()
        with self._lock:
            data = list(self._audio_data)
            self._audio_data = []

        if data:
            audio_np = np.concatenate(data, axis=0).flatten()
            gain = self._config.get('recognition', 'audio_gain', default=1.0)
            if gain != 1.0:
                audio_np = audio_np * gain
            audio_np = self._trim_silence(audio_np)
            if len(audio_np) < SAMPLE_RATE * 0.1:
                return
            audio_np = self._normalize(audio_np)
            self._bus.audio_ready.emit(audio_np)

    def _trim_silence(self, audio, threshold=0.01, margin_samples=1600):
        """Обрезать тишину в начале и конце аудио."""
        amplitude = np.abs(audio)
        above = np.where(amplitude > threshold)[0]
        if len(above) == 0:
            return audio[:0]
        start = max(0, above[0] - margin_samples)
        end = min(len(audio), above[-1] + margin_samples)
        return audio[start:end]

    def _normalize(self, audio, target_peak=0.8):
        """Нормализовать громкость до target_peak."""
        peak = np.max(np.abs(audio))
        if peak < 0.001:
            return audio
        return audio * (target_peak / peak)
