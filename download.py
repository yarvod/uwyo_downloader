from pathlib import Path
import sys


def main() -> None:
    """
    Тонкий вход: пробрасываем путь src и запускаем GUI.
    """
    root = Path(__file__).resolve().parent
    src_path = root / "src"
    if src_path.exists():
        sys.path.insert(0, str(src_path))
    from uwyo_downloader.__main__ import main as app_main

    app_main()


if __name__ == "__main__":
    main()
