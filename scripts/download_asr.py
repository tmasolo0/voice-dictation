"""Скачивание ONNX-модели Qwen3-ASR из HuggingFace."""

import logging
import shutil
from pathlib import Path

log = logging.getLogger(__name__)

# Модели с готовыми ONNX-весами
MODELS = {
    "qwen3-asr-1.7b": {
        "repo_id": "andrewleech/Qwen3-ASR-1.7B-ONNX",
        "size_gb": 2.7,
        "description": "Quality (1.7B) — лучшее качество",
    },
    "qwen3-asr-0.6b": {
        "repo_id": "andrewleech/Qwen3-ASR-0.6B-ONNX",
        "size_gb": 1.3,
        "description": "Fast (0.6B) — быстрый, компактный",
    },
}

ALLOW_PATTERNS = [
    "*.int4.onnx",
    "*.int4.data",
    "embed_tokens.bin",
    "config.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "added_tokens.json",
    "preprocessor_config.json",
    "vocab.json",
]

# Определяем путь к models/
try:
    from core.config_manager import APP_DIR
    MODELS_DIR = APP_DIR / "models"
except ImportError:
    SCRIPT_DIR = Path(__file__).parent
    MODELS_DIR = SCRIPT_DIR.parent / "models"


def download(
    model_name: str = "qwen3-asr-1.7b",
    output_dir: Path | None = None,
    tqdm_class=None,
    progress_callback=None,
):
    """Скачать ONNX-модель Qwen3-ASR.

    Args:
        model_name: ключ из MODELS
        output_dir: путь для сохранения модели
        tqdm_class: подменный tqdm для перехвата прогресса
        progress_callback: callable(phase: str) — уведомление о смене фазы
    """
    if model_name not in MODELS:
        raise ValueError(f"Неизвестная модель: {model_name}. Доступные: {list(MODELS)}")

    model_info = MODELS[model_name]
    repo_id = model_info["repo_id"]

    if output_dir is None:
        output_dir = MODELS_DIR / model_name

    output_dir.mkdir(parents=True, exist_ok=True)

    log.info("Скачивание %s -> %s (~%.1f GB)", repo_id, output_dir, model_info["size_gb"])

    if progress_callback:
        progress_callback("Скачивание модели...")

    from huggingface_hub import snapshot_download

    download_kwargs = {
        "repo_id": repo_id,
        "local_dir": str(output_dir),
        "allow_patterns": ALLOW_PATTERNS,
    }
    if tqdm_class is not None:
        download_kwargs["tqdm_class"] = tqdm_class

    snapshot_download(**download_kwargs)

    # Верификация: проверяем наличие ключевых файлов
    has_encoder = any(
        (output_dir / name).exists()
        for name in ("encoder.int4.onnx", "encoder.onnx", "encoder_conv.onnx")
    )
    has_decoder = any(
        (output_dir / name).exists()
        for name in ("decoder_init.int4.onnx", "decoder_init.int8.onnx", "decoder_init.onnx")
    )

    if has_encoder and has_decoder:
        log.info("Модель %s готова: %s", model_name, output_dir)
    else:
        files = [f.name for f in output_dir.iterdir()]
        raise RuntimeError(
            f"Не найдены ONNX-файлы модели в {output_dir}. Файлы: {files}"
        )

    if progress_callback:
        progress_callback("Готово")


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Скачивание Qwen3-ASR ONNX")
    parser.add_argument(
        "--model", default="qwen3-asr-1.7b",
        choices=list(MODELS),
        help="Модель для скачивания",
    )
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    download(args.model, args.output)
