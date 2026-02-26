"""Генерация icon.ico из исходного изображения."""

import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("Pillow не установлен. Установите: pip install Pillow")
    sys.exit(1)


def generate_icon(source: Path, output: Path):
    """Создаёт .ico с размерами 16, 32, 48, 256 из исходного изображения."""
    img = Image.open(source)

    # Обрезка до квадрата по центру
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    img = img.crop((left, top, left + side, top + side))

    sizes = [(16, 16), (32, 32), (48, 48), (256, 256)]
    icons = []
    for size in sizes:
        resized = img.resize(size, Image.LANCZOS)
        icons.append(resized)

    output.parent.mkdir(parents=True, exist_ok=True)
    icons[0].save(
        str(output),
        format='ICO',
        sizes=sizes,
        append_images=icons[1:],
    )
    print(f"Иконка создана: {output} ({', '.join(f'{s[0]}px' for s in sizes)})")


if __name__ == "__main__":
    root = Path(__file__).parent.parent
    source = root / "Ava.jpg"
    output = root / "assets" / "icon.ico"

    if not source.exists():
        print(f"Исходное изображение не найдено: {source}")
        sys.exit(1)

    generate_icon(source, output)
