import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from .ui.main_window import MainWindow


def _prepare_env() -> None:
    """
    Небольшая стабилизация QtWebEngine на macOS: отключаем GPU рендер,
    шарим GL-контексты между окнами.
    """
    os.environ.setdefault(
        "QTWEBENGINE_CHROMIUM_FLAGS",
        "--disable-gpu --disable-software-rasterizer",
    )
    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)


def main() -> None:
    if "--map-process" in sys.argv:
        idx = sys.argv.index("--map-process")
        sys.argv = [sys.argv[0]] + sys.argv[idx + 1 :]
        _prepare_env()
        from .ui.map_process import run_map_process

        run_map_process(sys.argv[1:])
        return

    _prepare_env()
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
