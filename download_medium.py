"""Скачивание модели Whisper medium для режима перевода."""

from pathlib import Path
from huggingface_hub import snapshot_download

MODELS_DIR = Path(__file__).parent / "models"
MODEL_NAME = "medium"
REPO_ID = "Systran/faster-whisper-medium"

def main():
    target_dir = MODELS_DIR / MODEL_NAME

    print("=" * 50)
    print(f"Скачивание модели: {REPO_ID}")
    print(f"Папка: {target_dir}")
    print("=" * 50)

    # Создаём папку models если нет
    MODELS_DIR.mkdir(exist_ok=True)

    # Скачиваем модель
    snapshot_download(
        repo_id=REPO_ID,
        local_dir=str(target_dir),
        local_dir_use_symlinks=False,  # Копировать файлы, не симлинки
    )

    print("=" * 50)
    print("Готово!")
    print(f"Модель сохранена в: {target_dir}")
    print("=" * 50)

if __name__ == "__main__":
    main()
