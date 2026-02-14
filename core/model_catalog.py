"""Каталог моделей Whisper — метаданные, проверка наличия, хелперы."""

from pathlib import Path

MODELS_DIR = Path(__file__).parent.parent / "models"

MODEL_CATALOG = {
    "large-v3-turbo": {
        "repo_id": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
        "size_gb": 1.51,
        "description": "Turbo — быстрый, хорошее качество",
        "downloadable": True,
    },
    "large-v3": {
        "repo_id": "Systran/faster-whisper-large-v3",
        "size_gb": 2.88,
        "description": "Quality — лучшее качество, медленнее",
        "downloadable": True,
    },
    "medium": {
        "repo_id": "Systran/faster-whisper-medium",
        "size_gb": 1.43,
        "description": "Medium — для перевода RU→EN",
        "downloadable": True,
    },
    "whisper-podlodka-turbo": {
        "repo_id": "bond005/whisper-podlodka-turbo",
        "size_gb": 3.03,
        "description": "RU Turbo — fine-tuned для русского (требует конвертации)",
        "downloadable": False,
    },
}

ALLOW_PATTERNS = [
    "config.json",
    "preprocessor_config.json",
    "model.bin",
    "tokenizer.json",
    "vocabulary.*",
]


def is_model_downloaded(model_name: str) -> bool:
    """Проверяет наличие скачанной модели по model.bin."""
    return (MODELS_DIR / model_name / "model.bin").exists()


def get_local_models() -> list[str]:
    """Возвращает список имён моделей, у которых есть model.bin в MODELS_DIR."""
    if not MODELS_DIR.exists():
        return []
    return [
        d.name
        for d in MODELS_DIR.iterdir()
        if d.is_dir() and (d / "model.bin").exists()
    ]


MODEL_LABELS = {
    'large-v3-turbo': 'Turbo',
    'large-v3': 'Quality',
    'medium': 'Medium',
    'whisper-podlodka-turbo': 'RU Turbo',
}
