"""Скачивание и конвертация Qwen2.5-1.5B-Instruct в CTranslate2 формат."""

import logging
import shutil
import sys
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)

REPO_ID = "Qwen/Qwen2.5-1.5B-Instruct"
MODEL_NAME = "qwen2.5-1.5b-ct2"
QUANTIZATION = "float16"

TOKENIZER_FILES = [
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
]

# Определяем путь к models/ относительно APP_DIR
try:
    from core.config_manager import APP_DIR
    MODELS_DIR = APP_DIR / "models"
except ImportError:
    # Fallback для standalone-запуска
    SCRIPT_DIR = Path(__file__).parent
    MODELS_DIR = SCRIPT_DIR.parent / "models"


def convert(output_dir: Path | None = None, tqdm_class=None, progress_callback=None):
    """Конвертировать модель: скачать из HF + CTranslate2 Python API.

    Args:
        output_dir: путь для сохранения модели
        tqdm_class: подменный tqdm для перехвата прогресса скачивания
        progress_callback: callable(phase: str) — уведомление о смене фазы
    """
    if output_dir is None:
        output_dir = MODELS_DIR / MODEL_NAME

    output_dir.parent.mkdir(parents=True, exist_ok=True)

    log.info("Конвертация %s -> %s (квантизация: %s)", REPO_ID, output_dir, QUANTIZATION)

    # Фаза 1: Скачивание модели во временную папку (даёт побайтовый прогресс)
    if progress_callback:
        progress_callback("Скачивание модели...")

    from huggingface_hub import snapshot_download

    with tempfile.TemporaryDirectory(prefix="vd_llm_") as tmp_dir:
        download_kwargs = {
            "repo_id": REPO_ID,
            "local_dir": tmp_dir,
        }
        if tqdm_class is not None:
            download_kwargs["tqdm_class"] = tqdm_class

        log.info("Скачивание модели из HuggingFace...")
        snapshot_download(**download_kwargs)
        tmp_path = Path(tmp_dir)
        log.info("Модель скачана: %s", tmp_path)

        # Фаза 2: Конвертация через Python API (работает в frozen-app)
        if progress_callback:
            progress_callback("Конвертация модели...")

        from ctranslate2.converters.transformers import TransformersConverter

        converter = TransformersConverter(
            str(tmp_path),
            low_cpu_mem_usage=True,
        )
        log.info("Запуск конвертации через CTranslate2 Python API...")
        converter.convert(
            str(output_dir),
            quantization=QUANTIZATION,
            force=True,
        )

        # Шаг 3: Копировать tokenizer-файлы
        log.info("Копирование tokenizer-файлов...")
        for fname in TOKENIZER_FILES:
            src = tmp_path / fname
            dst = output_dir / fname
            if src.exists() and not dst.exists():
                shutil.copy2(src, dst)
                log.info("  %s -> OK", fname)
            elif dst.exists():
                log.info("  %s -> уже есть", fname)
            else:
                log.warning("  %s -> не найден", fname)

    # Проверка (после выхода из with — tmp_dir уже удалён)
    if (output_dir / "model.bin").exists():
        log.info("Модель готова: %s", output_dir)
    else:
        raise RuntimeError(f"model.bin не создан в {output_dir}")


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Конвертация LLM для Voice Dictation")
    parser.add_argument("--output", type=Path, default=None,
                        help=f"Путь для сохранения (по умолчанию: models/{MODEL_NAME})")
    args = parser.parse_args()
    convert(args.output)
