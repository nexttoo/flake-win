"""Сборка иконки Windows (.ico) из векторной снежинки приложения."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PIL import Image
from PySide6.QtWidgets import QApplication

from flakewin.app import make_snowflake_image

SIZES = (16, 24, 32, 48, 64, 128, 256)


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841
    out_dir = os.path.dirname(os.path.abspath(__file__))
    frames = []
    for size in SIZES:
        image = make_snowflake_image(size)
        path = os.path.join(out_dir, f"_icon_{size}.png")
        image.save(path, "PNG")
        frames.append(Image.open(path).convert("RGBA"))

    ico_path = os.path.join(out_dir, "flake.ico")
    frames[-1].save(ico_path, format="ICO",
                    sizes=[(s, s) for s in SIZES])
    for size in SIZES:
        try:
            os.remove(os.path.join(out_dir, f"_icon_{size}.png"))
        except OSError:
            pass
    print("icon:", ico_path, os.path.getsize(ico_path), "bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
