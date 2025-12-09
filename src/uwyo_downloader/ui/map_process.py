import argparse
import json
import signal
import sys
import threading
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication, QMainWindow

from .map_view import StationMapView


class _StdinBridge(QObject):
    """
    Читает JSON сообщения из stdin в фоне и прокидывает в GUI поток.
    """

    message = Signal(dict)
    eof = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def _run(self) -> None:
        for raw in sys.stdin.buffer:
            line = raw.decode("utf-8", errors="ignore").strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            self.message.emit(payload)
        self.eof.emit()


class MapWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Карта станций")
        self.view = StationMapView()
        self.setCentralWidget(self.view)
        self.view.stationClicked.connect(self._handle_station_click)

    def load_html(self, html: str) -> None:
        self.view.set_html(html)
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):  # noqa: N802
        """
        Закрытие окна — корректно завершаем приложение, чтобы не было crash-диалога macOS.
        """
        QApplication.quit()
        event.accept()

    @staticmethod
    def _handle_station_click(station_id: str) -> None:
        try:
            payload = json.dumps({"type": "station", "id": station_id})
            sys.stdout.write(payload + "\n")
            sys.stdout.flush()
        except Exception:  # noqa: BLE001
            pass


def _handle_message(window: MapWindow, app: QApplication, message: dict) -> None:
    kind = message.get("type")
    if kind == "load":
        path = message.get("path")
        if path:
            try:
                html = Path(path).read_text(encoding="utf-8")
            except OSError:
                return
            window.load_html(html)
    elif kind == "show":
        window.showNormal()
        window.raise_()
        window.activateWindow()
    elif kind == "quit":
        app.quit()


def run_map_process(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Отдельный процесс для карты станций")
    parser.add_argument("--html", help="Путь к HTML с картой", default=None)
    args = parser.parse_args(argv or sys.argv[1:])

    app = QApplication(sys.argv)
    signal.signal(signal.SIGTERM, lambda *_: app.quit())
    window = MapWindow()

    if args.html:
        try:
            initial_html = Path(args.html).read_text(encoding="utf-8")
        except OSError:
            initial_html = None
        if initial_html is not None:
            window.load_html(initial_html)

    bridge = _StdinBridge()
    bridge.message.connect(lambda payload: _handle_message(window, app, payload))
    bridge.eof.connect(app.quit)
    bridge.start()

    window.show()
    exit_code = app.exec()
    sys.exit(exit_code if exit_code is not None else 0)


if __name__ == "__main__":
    run_map_process()
