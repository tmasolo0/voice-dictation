"""Генерация мягких звуковых эффектов start.wav и stop.wav в стиле Aqua Voice."""

import wave
import struct
import math
import os

SAMPLE_RATE = 44100
AMPLITUDE = 0.12  # тихий, деликатный звук


def generate_soft_tone(freq_start, freq_end, duration=0.1, harmonics=True):
    """Мягкий тон с плавным fade и опциональной второй гармоникой."""
    num_samples = int(SAMPLE_RATE * duration)
    samples = []
    for i in range(num_samples):
        t = i / SAMPLE_RATE
        progress = i / num_samples

        # Плавная интерполяция частоты (ease in-out)
        ease = progress * progress * (3 - 2 * progress)
        freq = freq_start + (freq_end - freq_start) * ease

        # Основной тон
        sample = math.sin(2 * math.pi * freq * t)

        # Мягкая вторая гармоника (придаёт "округлость")
        if harmonics:
            sample += 0.15 * math.sin(2 * math.pi * freq * 1.5 * t)

        sample *= AMPLITUDE

        # Envelope: мягкий fade in (30%) + длинный fade out (50%)
        if progress < 0.3:
            env = progress / 0.3
            env = env * env  # quadratic ease-in
        elif progress > 0.5:
            env = (1 - progress) / 0.5
            env = env * env  # quadratic ease-out
        else:
            env = 1.0

        sample *= env
        samples.append(sample)

    return samples


def write_wav(filename, samples):
    """Запись сэмплов в WAV файл."""
    with wave.open(filename, 'w') as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(SAMPLE_RATE)
        for s in samples:
            s = max(-1.0, min(1.0, s))
            f.writeframes(struct.pack('<h', int(s * 32767)))


if __name__ == '__main__':
    out_dir = os.path.join(os.path.dirname(__file__), '..', 'assets', 'sounds')
    os.makedirs(out_dir, exist_ok=True)

    # Start: мягкий восходящий "пинг" (C5 → E5)
    start_samples = generate_soft_tone(523, 659, duration=0.12)
    write_wav(os.path.join(out_dir, 'start.wav'), start_samples)

    # Stop: мягкий нисходящий "понг" (E5 → C5)
    stop_samples = generate_soft_tone(659, 523, duration=0.10)
    write_wav(os.path.join(out_dir, 'stop.wav'), stop_samples)

    print(f"Generated soft start.wav and stop.wav in {out_dir}")
