import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from .di import get_container
from .ui.main_window import MainWindow


def _prepare_env() -> None:
    """
    Небольшая стабилизация Qt на macOS: отключаем GPU рендер и
    шарим GL-контексты между окнами.
    """
    os.environ.setdefault(
        "QTWEBENGINE_CHROMIUM_FLAGS",
        "--disable-gpu --disable-software-rasterizer",
    )
    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)


def main() -> None:
    _prepare_env()
    container = get_container()
    container.ensure_ready()
    app = QApplication(sys.argv)
    window = MainWindow(container)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
