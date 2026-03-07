"""AudioDucker — приглушение системного звука при записи."""

import logging
import os

log = logging.getLogger(__name__)


class AudioDucker:
    """Приглушает все аудио-сессии кроме собственного процесса при записи."""

    def __init__(self, event_bus, config):
        self._bus = event_bus
        self._config = config
        self._saved_volumes: dict[int, float] = {}  # pid -> original volume
        self._own_pid = os.getpid()

        self._bus.recording_start.connect(self._on_recording_start)
        self._bus.recording_stop.connect(self._on_recording_stop)

    def _is_enabled(self) -> bool:
        return self._config.get('widget', 'audio_ducking', default=True)

    def _get_duck_level(self) -> float:
        return self._config.get('widget', 'duck_level', default=0.15)

    def _on_recording_start(self, hwnd):
        if not self._is_enabled():
            return
        try:
            from pycaw.pycaw import AudioUtilities

            duck_level = self._get_duck_level()
            self._saved_volumes.clear()

            sessions = AudioUtilities.GetAllSessions()
            for session in sessions:
                if session.Process is None:
                    continue
                if session.Process.pid == self._own_pid:
                    continue
                try:
                    volume = session.SimpleAudioVolume
                    current = volume.GetMasterVolume()
                    self._saved_volumes[session.Process.pid] = current
                    volume.SetMasterVolume(current * duck_level, None)
                except Exception:
                    pass

            if self._saved_volumes:
                log.debug("audio_ducking: приглушено %d сессий (x%.2f)",
                          len(self._saved_volumes), duck_level)
        except Exception as e:
            log.warning("audio_ducking: ошибка при приглушении: %s", e)

    def _on_recording_stop(self):
        if not self._saved_volumes:
            return
        try:
            from pycaw.pycaw import AudioUtilities

            sessions = AudioUtilities.GetAllSessions()
            restored = 0
            for session in sessions:
                if session.Process is None:
                    continue
                pid = session.Process.pid
                if pid in self._saved_volumes:
                    try:
                        volume = session.SimpleAudioVolume
                        volume.SetMasterVolume(self._saved_volumes[pid], None)
                        restored += 1
                    except Exception:
                        pass

            log.debug("audio_ducking: восстановлено %d/%d сессий",
                      restored, len(self._saved_volumes))
        except Exception as e:
            log.warning("audio_ducking: ошибка при восстановлении: %s", e)
        finally:
            self._saved_volumes.clear()
