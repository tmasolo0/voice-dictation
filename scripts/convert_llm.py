"""Скачивание и конвертация Qwen2.5-1.5B-Instruct в CTranslate2 формат."""

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ID = "Qwen/Qwen2.5-1.5B-Instruct"
MODEL_NAME = "qwen2.5-1.5b-ct2"
QUANTIZATION = "int8_float16"

TOKENIZER_FILES = [
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
]

# Определяем путь к models/ относительно скрипта (../models/)
SCRIPT_DIR = Path(__file__).parent
MODELS_DIR = SCRIPT_DIR.parent / "models"


def get_hf_cache_dir(repo_id: str) -> Path | None:
    """Найти папку модели в кэше HuggingFace."""
    try:
        from huggingface_hub import snapshot_download
        # snapshot_download возвращает путь к кэшу
        cache_path = snapshot_download(repo_id, local_dir=None)
        return Path(cache_path)
    except Exception:
        return None


def convert(output_dir: Path | None = None):
    """Конвертировать модель: скачать из HF + ct2-transformers-converter."""
    if output_dir is None:
        output_dir = MODELS_DIR / MODEL_NAME

    output_dir.parent.mkdir(parents=True, exist_ok=True)

    print(f"Конвертация {REPO_ID} -> {output_dir}")
    print(f"Квантизация: {QUANTIZATION}")

    # Шаг 1: Конвертация через ct2-transformers-converter
    cmd = [
        sys.executable, "-m", "ctranslate2.converters.transformers",
        "--model", REPO_ID,
        "--output_dir", str(output_dir),
        "--quantization", QUANTIZATION,
        "--low_cpu_mem_usage",
        "--force",
    ]
    print(f"Запуск: {' '.join(cmd)}")
    result = subprocess.run(cmd, check=True)

    # Шаг 2: Копировать tokenizer-файлы из кэша HF
    print("Копирование tokenizer-файлов...")
    hf_cache = get_hf_cache_dir(REPO_ID)
    if hf_cache and hf_cache.exists():
        for fname in TOKENIZER_FILES:
            src = hf_cache / fname
            dst = output_dir / fname
            if src.exists() and not dst.exists():
                shutil.copy2(src, dst)
                print(f"  {fname} -> OK")
            elif dst.exists():
                print(f"  {fname} -> уже есть")
            else:
                print(f"  {fname} -> не найден в кэше")
    else:
        print("WARN: кэш HF не найден, tokenizer-файлы нужно скопировать вручную")

    # Проверка
    if (output_dir / "model.bin").exists():
        print(f"\nМодель готова: {output_dir}")
    else:
        print(f"\nОШИБКА: model.bin не создан в {output_dir}")
        sys.exit(1)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Конвертация LLM для Voice Dictation")
    parser.add_argument("--output", type=Path, default=None,
                        help=f"Путь для сохранения (по умолчанию: models/{MODEL_NAME})")
    args = parser.parse_args()
    convert(args.output)
