"""Каталог моделей ASR — метаданные, проверка наличия, хелперы."""

from core.config_manager import APP_DIR

MODELS_DIR = APP_DIR / "models"

MODEL_CATALOG = {
    "qwen3-asr-1.7b": {
        "repo_id": "andrewleech/Qwen3-ASR-1.7B-ONNX",
        "size_gb": 2.7,
        "description": "Quality (1.7B) — лучшее качество, 52 языка",
        "downloadable": True,
    },
    "qwen3-asr-0.6b": {
        "repo_id": "andrewleech/Qwen3-ASR-0.6B-ONNX",
        "size_gb": 1.3,
        "description": "Fast (0.6B) — быстрый, компактный",
        "downloadable": True,
    },
}

ALLOW_PATTERNS = [
    "*.int4.onnx",
    "*.int4.data",
    "embed_tokens.bin",
    "*.json",
]


def _has_onnx_model(model_dir) -> bool:
    """Проверяет наличие ONNX-файлов модели."""
    return (
        (model_dir / "encoder.int4.onnx").exists()
        or (model_dir / "encoder.onnx").exists()
        or (model_dir / "encoder_conv.onnx").exists()
    )


def is_model_downloaded(model_name: str) -> bool:
    """Проверяет наличие скачанной модели."""
    return _has_onnx_model(MODELS_DIR / model_name)


def get_local_models() -> list[str]:
    """Возвращает список имён скачанных моделей."""
    if not MODELS_DIR.exists():
        return []
    return [
        d.name
        for d in MODELS_DIR.iterdir()
        if d.is_dir() and _has_onnx_model(d)
    ]


MODEL_LABELS = {
    'qwen3-asr-1.7b': 'Quality (1.7B)',
    'qwen3-asr-0.6b': 'Fast (0.6B)',
}
