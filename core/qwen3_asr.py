"""Qwen3-ASR ONNX Backend — распознавание речи через ONNX Runtime."""

import logging
from pathlib import Path

import numpy as np

from core.asr_backend import ASRBackend, ASRResult
from core.vad import SileroVAD

log = logging.getLogger(__name__)

# --- Mel spectrogram параметры (идентичны Whisper / Qwen3-ASR) ---
SAMPLE_RATE = 16000
N_FFT = 400
HOP_LENGTH = 160
N_MELS = 128
FMIN = 0
FMAX = 8000

# --- Специальные токены ---
ENDOFTEXT_ID = 151643
IM_START_ID = 151644
IM_END_ID = 151645
AUDIO_START_ID = 151669
AUDIO_END_ID = 151670
AUDIO_PAD_ID = 151676
ASR_TEXT_ID = 151704
NEWLINE_ID = 198

EOS_TOKEN_IDS = {ENDOFTEXT_ID, IM_END_ID}

# Токен IDs для строковых литералов
TOKEN_SYSTEM = 9125     # "system"
TOKEN_USER = 882        # "user"
TOKEN_ASSISTANT = 77091  # "assistant"

# --- Encoder output length ---
CONV_WINDOW = 100  # n_window * 2
TOKENS_PER_WINDOW = 13

MAX_NEW_TOKENS = 1024


def _conv_out_len(t: int) -> int:
    return (t + 1) // 2


def get_audio_token_count(mel_frames: int) -> int:
    """Число audio-токенов из числа mel-фреймов."""
    leave = mel_frames % CONV_WINDOW
    t = _conv_out_len(leave)
    t = _conv_out_len(t)
    t = _conv_out_len(t)
    return t + (mel_frames // CONV_WINDOW) * TOKENS_PER_WINDOW


def compute_mel_filters() -> np.ndarray:
    """Mel-фильтры для спектрограммы (128 bins)."""
    import librosa
    return librosa.filters.mel(
        sr=SAMPLE_RATE, n_fft=N_FFT, n_mels=N_MELS,
        fmin=FMIN, fmax=FMAX, norm="slaney", htk=False,
    ).astype(np.float32)


def compute_mel_spectrogram(audio: np.ndarray, mel_filters: np.ndarray) -> np.ndarray:
    """Log-mel спектрограмма для Qwen3-ASR.

    Args:
        audio: float32 моно @ 16kHz
        mel_filters: [N_MELS, N_FFT//2 + 1]

    Returns:
        [N_MELS, T] float32 — log-mel спектрограмма
    """
    import librosa

    stft = librosa.stft(
        audio, n_fft=N_FFT, hop_length=HOP_LENGTH,
        window="hann", center=True, pad_mode="reflect",
    )
    magnitudes = np.abs(stft) ** 2
    mel_spec = mel_filters @ magnitudes
    log_spec = np.log10(np.maximum(mel_spec, 1e-10))
    log_spec = np.maximum(log_spec, log_spec.max() - 8.0)
    log_spec = (log_spec + 4.0) / 4.0
    return log_spec.astype(np.float32)


def build_prompt_ids(
    num_audio_tokens: int,
    system_prompt: str | None = None,
    tokenizer=None,
) -> list[int]:
    """Построить prompt token IDs для Qwen3-ASR.

    Формат: <|im_start|>system\n{system_prompt}<|im_end|>\n
            <|im_start|>user\n<|audio_start|><|audio_pad|>*N<|audio_end|><|im_end|>\n
            <|im_start|>assistant\n
    """
    ids = [IM_START_ID, TOKEN_SYSTEM, NEWLINE_ID]

    # System prompt (термины, инструкции)
    if system_prompt and tokenizer:
        prompt_ids = tokenizer.encode(system_prompt).ids
        ids.extend(prompt_ids)

    ids.extend([IM_END_ID, NEWLINE_ID])

    # User turn с аудио
    ids.extend([IM_START_ID, TOKEN_USER, NEWLINE_ID, AUDIO_START_ID])
    ids.extend([AUDIO_PAD_ID] * num_audio_tokens)
    ids.extend([AUDIO_END_ID, IM_END_ID, NEWLINE_ID])

    # Assistant turn (генерация)
    ids.extend([IM_START_ID, TOKEN_ASSISTANT, NEWLINE_ID])

    return ids


class Qwen3ASRBackend(ASRBackend):
    """Qwen3-ASR через ONNX Runtime с KV-cache авторегрессией."""

    def __init__(self):
        self._encoder = None
        self._decoder_init = None
        self._decoder_step = None
        self._embed_tokens = None
        self._tokenizer = None
        self._mel_filters = None
        self._vad = None
        self._hidden_size = 0
        self._vocab_size = 151936
        self._device = "cpu"

    @property
    def is_loaded(self) -> bool:
        return self._encoder is not None and self._decoder_init is not None

    def load(self, model_path: str, device: str = "cuda") -> None:
        """Загрузить ONNX-модель Qwen3-ASR.

        Поддерживает два варианта layout:
        - Единый encoder.onnx + decoder_init.onnx + decoder_step.onnx (andrewleech)
        - Split encoder_conv.onnx + encoder_transformer.onnx + decoder_init.int8.onnx (Daumee)
        """
        import onnxruntime as ort
        from tokenizers import Tokenizer

        self._device = device
        model_dir = Path(model_path)

        # Определяем providers для ONNX Runtime
        providers = self._get_providers(device)
        log.info("ONNX providers: %s", providers)

        # Загрузка encoder
        self._encoder = self._load_encoder(model_dir, providers, ort)

        # Загрузка decoder
        self._decoder_init, self._decoder_step = self._load_decoders(
            model_dir, providers, ort,
        )

        # Определяем hidden_size из config.json
        self._load_config(model_dir)

        # Embedding matrix (нужна для decoder_step авторегрессии)
        embed_path = model_dir / "embed_tokens.bin"
        if embed_path.exists():
            raw = np.fromfile(str(embed_path), dtype=self._embed_dtype)
            self._embed_tokens = raw.reshape(self._vocab_size, self._hidden_size)
            log.info("Embeddings: [%d, %d] dtype=%s", self._vocab_size, self._hidden_size,
                     self._embed_dtype)
        else:
            log.warning("embed_tokens.bin не найден — decoder_step будет недоступен")
            self._embed_tokens = None

        # Tokenizer
        tokenizer_path = model_dir / "tokenizer.json"
        if tokenizer_path.exists():
            self._tokenizer = Tokenizer.from_file(str(tokenizer_path))
        else:
            log.warning("tokenizer.json не найден, system prompt будет игнорироваться")

        # Mel filters (вычисляются один раз)
        self._mel_filters = compute_mel_filters()

        # VAD (Silero)
        self._load_vad(model_dir)

        log.info("Qwen3-ASR загружена: %s (device=%s, hidden=%d)",
                 model_dir.name, device, self._hidden_size)

    def _get_providers(self, device: str) -> list[str]:
        """Список ONNX Runtime providers по приоритету."""
        if device == "cuda":
            return ["CUDAExecutionProvider", "CPUExecutionProvider"]
        return ["CPUExecutionProvider"]

    def _load_encoder(self, model_dir: Path, providers: list[str], ort) -> object:
        """Загрузить encoder (приоритет int4 → fp32 → split)."""
        # Приоритет: int4 квантизация (меньше VRAM, быстрее)
        for name in ("encoder.int4.onnx", "encoder.onnx"):
            path = model_dir / name
            if path.exists():
                log.info("Загрузка %s...", name)
                return ort.InferenceSession(str(path), providers=providers)

        # Split вариант (Daumee)
        if (model_dir / "encoder_conv.onnx").exists():
            log.info("Загрузка split encoder (conv + transformer)...")
            return _SplitEncoder(
                ort.InferenceSession(
                    str(model_dir / "encoder_conv.onnx"), providers=providers,
                ),
                ort.InferenceSession(
                    str(model_dir / "encoder_transformer.onnx"), providers=providers,
                ),
            )

        raise FileNotFoundError(f"encoder ONNX не найден в {model_dir}")

    def _load_decoders(self, model_dir: Path, providers: list[str], ort):
        """Загрузить decoder_init и decoder_step."""
        # Приоритет: int4 → int8 → fp32
        init_candidates = ["decoder_init.int4.onnx", "decoder_init.int8.onnx", "decoder_init.onnx"]
        step_candidates = ["decoder_step.int4.onnx", "decoder_step.int8.onnx", "decoder_step.onnx"]

        decoder_init = None
        for name in init_candidates:
            path = model_dir / name
            if path.exists():
                log.info("Загрузка %s...", name)
                decoder_init = ort.InferenceSession(str(path), providers=providers)
                break

        decoder_step = None
        for name in step_candidates:
            path = model_dir / name
            if path.exists():
                log.info("Загрузка %s...", name)
                decoder_step = ort.InferenceSession(str(path), providers=providers)
                break

        if decoder_init is None:
            raise FileNotFoundError(f"decoder_init ONNX не найден в {model_dir}")
        if decoder_step is None:
            raise FileNotFoundError(f"decoder_step ONNX не найден в {model_dir}")

        return decoder_init, decoder_step

    def _load_config(self, model_dir: Path) -> None:
        """Прочитать config.json для определения размерностей."""
        import json
        config_path = model_dir / "config.json"
        self._embed_dtype = np.float32  # default

        if config_path.exists():
            with open(config_path, encoding="utf-8") as f:
                cfg = json.load(f)
            # andrewleech формат: decoder.hidden_size
            decoder_cfg = cfg.get("decoder", {})
            text_cfg = cfg.get("text_config", {})
            self._hidden_size = (
                decoder_cfg.get("hidden_size")
                or text_cfg.get("hidden_size")
                or cfg.get("hidden_size", 2048)
            )
            self._vocab_size = (
                decoder_cfg.get("vocab_size")
                or text_cfg.get("vocab_size")
                or cfg.get("vocab_size", 151936)
            )
            # embed_tokens может быть float16
            dtype_str = cfg.get("embed_tokens_dtype", "float32")
            self._embed_dtype = np.float16 if "16" in dtype_str else np.float32
            log.info("Config: hidden=%d, vocab=%d, embed_dtype=%s",
                     self._hidden_size, self._vocab_size, dtype_str)
        else:
            self._hidden_size = 2048
            log.warning("config.json не найден, hidden_size=%d (default)", self._hidden_size)

    def _load_vad(self, model_dir: Path) -> None:
        """Загрузить Silero VAD (из assets/ или model_dir)."""
        # Ищем VAD в нескольких местах
        candidates = [
            model_dir / "silero_vad.onnx",
            model_dir.parent.parent / "assets" / "silero_vad.onnx",
            Path(__file__).parent.parent / "assets" / "silero_vad.onnx",
        ]

        # Также ищем в faster_whisper assets (если ещё установлен)
        try:
            import faster_whisper
            fw_dir = Path(faster_whisper.__file__).parent / "assets"
            candidates.append(fw_dir / "silero_vad_v6.onnx")
        except ImportError:
            pass

        for vad_path in candidates:
            if vad_path.exists():
                self._vad = SileroVAD(model_path=vad_path)
                log.info("Silero VAD загружена: %s", vad_path)
                return

        log.warning("Silero VAD не найдена, VAD отключён")

    def transcribe(
        self,
        audio: np.ndarray,
        language: str | None = None,
        system_prompt: str | None = None,
    ) -> ASRResult:
        """Распознать аудио через Qwen3-ASR.

        Args:
            audio: float32 моно @ 16kHz
            language: код языка (пока не используется — модель определяет сама)
            system_prompt: системный промпт (термины, инструкции)

        Returns:
            ASRResult с текстом и метаданными
        """
        if not self.is_loaded:
            raise RuntimeError("Модель не загружена")

        import time
        start = time.time()

        # 1. VAD — обрезать тишину
        if self._vad and self._vad.is_loaded:
            audio = self._vad.extract_speech(audio)

        if len(audio) < SAMPLE_RATE * 0.1:  # < 100ms
            return ASRResult(text="", language="", elapsed=time.time() - start)

        # 2. Mel spectrogram
        mel = compute_mel_spectrogram(audio, self._mel_filters)
        mel_input = mel[np.newaxis, :, :]  # [1, 128, T]
        log.debug("mel shape: %s, audio len: %d samples", mel_input.shape, len(audio))

        # 3. Encode audio
        audio_features = self._encode(mel_input)  # [1, N, hidden_size]
        num_audio_tokens = audio_features.shape[1]
        log.debug("audio_features shape: %s, num_tokens: %d", audio_features.shape, num_audio_tokens)

        # 4. Build prompt token IDs
        prompt_ids = build_prompt_ids(
            num_audio_tokens,
            system_prompt=system_prompt,
            tokenizer=self._tokenizer,
        )

        # 5. Найти audio_offset (позиция первого AUDIO_PAD в prompt)
        ids_array = np.array(prompt_ids, dtype=np.int64)
        audio_positions = np.where(ids_array == AUDIO_PAD_ID)[0]
        audio_offset = np.array([int(audio_positions[0])], dtype=np.int64) if len(audio_positions) > 0 else np.array([0], dtype=np.int64)

        log.debug("prompt_ids len: %d, audio_pad count: %d, audio_offset: %d",
                  len(prompt_ids), len(audio_positions), audio_offset[0])

        # 6. Prefill (decoder_init) — принимает input_ids + audio_features
        seq_len = len(prompt_ids)
        input_ids = ids_array.reshape(1, -1)
        position_ids = np.arange(seq_len, dtype=np.int64).reshape(1, -1)

        outputs = self._decoder_init.run(None, {
            "input_ids": input_ids,
            "position_ids": position_ids,
            "audio_features": audio_features,
            "audio_offset": audio_offset,
        })
        logits = outputs[0]
        present_keys = outputs[1]
        present_values = outputs[2]

        # 7. Autoregressive decode (decoder_step использует input_embeds)
        next_token = int(np.argmax(logits[0, -1, :]))
        generated = [next_token]
        log.debug("first token: %d", next_token)
        cur_pos = seq_len

        for _ in range(MAX_NEW_TOKENS - 1):
            if next_token in EOS_TOKEN_IDS:
                break

            # decoder_step требует input_embeds из embed_tokens
            if self._embed_tokens is None:
                log.error("embed_tokens.bin не загружен — авторегрессия невозможна")
                break

            token_embed = self._embed_tokens[next_token][np.newaxis, np.newaxis, :].astype(np.float32)
            pos = np.array([[cur_pos]], dtype=np.int64)

            outputs = self._decoder_step.run(None, {
                "input_embeds": token_embed,
                "position_ids": pos,
                "past_keys": present_keys,
                "past_values": present_values,
            })
            logits = outputs[0]
            present_keys = outputs[1]
            present_values = outputs[2]

            next_token = int(np.argmax(logits[0, -1, :]))
            generated.append(next_token)
            cur_pos += 1

        # 8. Decode tokens → text
        log.debug("generated token_ids (%d): %s", len(generated), generated[:20])
        raw_text = self._tokenizer.decode(generated) if self._tokenizer else ""
        log.debug("raw_text: '%s'", raw_text[:200])
        text, detected_lang = self._parse_output(raw_text)

        elapsed = time.time() - start
        log.info("[%.1fс] lang=%s tokens=%d text='%s'",
                 elapsed, detected_lang, len(generated), text[:100] if text else "")

        return ASRResult(
            text=text,
            language=detected_lang or (language or ""),
            language_probability=1.0 if detected_lang else 0.0,
            elapsed=elapsed,
            metadata={"raw_tokens": len(generated), "audio_tokens": num_audio_tokens},
        )

    def _encode(self, mel: np.ndarray) -> np.ndarray:
        """Прогнать mel через encoder → audio features.

        Args:
            mel: [1, 128, T]

        Returns:
            [1, N, hidden_size] — audio features
        """
        if isinstance(self._encoder, _SplitEncoder):
            return self._encoder.run(mel)
        else:
            outputs = self._encoder.run(None, {"mel": mel})
            return outputs[0]

    def _embed_and_fuse(
        self,
        token_ids: list[int],
        audio_features: np.ndarray,
    ) -> np.ndarray:
        """Заменить audio_pad токены на реальные audio features.

        Args:
            token_ids: список token IDs
            audio_features: [N, hidden_size] — выход encoder

        Returns:
            [1, seq_len, hidden_size] — input embeddings с audio features
        """
        ids_array = np.array(token_ids, dtype=np.int64)
        embeds = self._embed_tokens[ids_array]  # [seq_len, hidden_size]

        # Заменяем AUDIO_PAD позиции на audio features
        audio_positions = np.where(ids_array == AUDIO_PAD_ID)[0]
        n_features = min(len(audio_positions), audio_features.shape[0])
        embeds[audio_positions[:n_features]] = audio_features[:n_features]

        return embeds[np.newaxis, :, :].astype(np.float32)

    @staticmethod
    def _parse_output(raw_text: str) -> tuple[str, str]:
        """Парсинг вывода модели: 'language ru<asr_text>Текст' → ('Текст', 'ru').

        Returns:
            (text, language)
        """
        text = raw_text.strip()
        language = ""

        # Убираем EOS-токены
        for marker in ["<|im_end|>", "<|endoftext|>"]:
            text = text.replace(marker, "")

        # Парсим язык и текст
        if "language " in text and "<asr_text>" in text:
            parts = text.split("<asr_text>", 1)
            lang_part = parts[0].strip()
            if lang_part.startswith("language "):
                language = lang_part[len("language "):].strip()
            text = parts[1].strip() if len(parts) > 1 else ""
        elif "<asr_text>" in text:
            text = text.split("<asr_text>", 1)[1].strip()

        return text, language

    def unload(self) -> None:
        """Выгрузить модель."""
        self._encoder = None
        self._decoder_init = None
        self._decoder_step = None
        self._embed_tokens = None
        self._tokenizer = None
        self._mel_filters = None
        if self._vad:
            self._vad = None
        self._hidden_size = 0
        log.info("Qwen3-ASR выгружена")


class _SplitEncoder:
    """Обёртка для split-варианта encoder (conv + transformer)."""

    def __init__(self, conv_session, transformer_session):
        self._conv = conv_session
        self._transformer = transformer_session

    def run(self, mel: np.ndarray) -> np.ndarray:
        """Прогнать mel через conv → transformer.

        Args:
            mel: [1, 128, T]

        Returns:
            [1, N, hidden_size]
        """
        # Conv: принимает чанки [N, 1, 128, chunk_len]
        # Для простоты пропускаем весь mel как один чанк
        mel_4d = mel[:, np.newaxis, :, :]  # [1, 1, 128, T]

        conv_out = self._conv.run(None, {"padded_mel_chunks": mel_4d})[0]
        # conv_out: [total_tokens, d_model]

        # Transformer
        total_tokens = conv_out.shape[0]
        # Простая causal mask
        attn_mask = np.zeros((1, 1, total_tokens, total_tokens), dtype=np.float32)
        attn_mask[:, :, :, :] = np.triu(
            np.full((total_tokens, total_tokens), -1e9), k=1,
        )

        encoder_out = self._transformer.run(None, {
            "hidden_states": conv_out,
            "attention_mask": attn_mask,
        })[0]

        return encoder_out[np.newaxis, :, :]  # [1, N, hidden_size]
