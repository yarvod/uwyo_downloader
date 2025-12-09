import json
import os
import sys
import tempfile
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QProcess, QUrl, Signal
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QVBoxLayout, QWidget

from ..models import StationInfo


class StationWebPage(QWebEnginePage):
    stationClicked = Signal(str)

    def acceptNavigationRequest(self, url, navtype, isMainFrame):  # noqa: N802
        if url.scheme().lower() == "station":
            station_id = url.host() or url.path().lstrip("/")
            self.stationClicked.emit(station_id)
            return False
        return super().acceptNavigationRequest(url, navtype, isMainFrame)


class StationMapView(QWidget):
    stationClicked = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.webview = QWebEngineView()
        self.page = StationWebPage(self.webview)
        self.page.stationClicked.connect(self.stationClicked)
        self.webview.setPage(self.page)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.webview)
        self.setMinimumHeight(320)

        settings = self.webview.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.ErrorPageEnabled, True)

        self.set_stations([])

    @staticmethod
    def build_html(stations: List[StationInfo]) -> str:
        """
        Сборка HTML для Leaflet карты с маркерами станций.
        """
        center = StationMapView._center_for(stations)
        station_data = [
            {
                "id": s.stationid,
                "name": s.name,
                "lat": s.lat,
                "lon": s.lon,
            }
            for s in stations
            if s.lat is not None and s.lon is not None
        ]
        stations_js = json.dumps(station_data, ensure_ascii=False)
        center_js = json.dumps(center)

        return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <link
    rel="stylesheet"
    href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
  />
  <style>
    html, body, #map {{ height: 100%; margin: 0; padding: 0; background: #0f172a; }}
    .leaflet-container {{ background: #0f172a; }}
  </style>
</head>
<body>
  <div id="map"></div>
  <script
    src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js">
  </script>
  <script>
    const center = {center_js};
    const stations = {stations_js};
    const map = L.map('map', {{
      zoomControl: true,
      worldCopyJump: false,
      maxBounds: [[-85, -180], [85, 180]],
      maxBoundsViscosity: 1.0
    }}).setView(center, 3);
    L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
      maxZoom: 10,
      minZoom: 2,
      noWrap: true,
      attribution: '&copy; OpenStreetMap contributors'
    }}).addTo(map);

    stations.forEach(s => {{
      const m = L.marker([s.lat, s.lon], {{ title: s.id }});
      m.bindTooltip(`${{s.id}} — ${{s.name}}`, {{permanent: false, direction: 'top'}});
      m.on('click', () => {{
        window.location.href = `station://${{encodeURIComponent(s.id)}}`;
      }});
      m.addTo(map);
    }});
  </script>
</body>
</html>"""

    @staticmethod
    def _center_for(stations: List[StationInfo]) -> list[float]:
        coords = [(s.lat, s.lon) for s in stations if s.lat is not None and s.lon is not None]
        if not coords:
            return [0.0, 0.0]
        avg_lat = sum(lat for lat, _ in coords) / len(coords)
        avg_lon = sum(lon for _, lon in coords) / len(coords)
        return [avg_lat, avg_lon]

    def set_stations(self, stations: List[StationInfo]) -> None:
        """
        Рендерим новую HTML-карту с маркерами станций (Leaflet).
        """
        html = self.build_html(stations)
        self.set_html(html)

    def set_html(self, html: str) -> None:
        self.webview.setHtml(html, baseUrl=QUrl("https://leaflet.local/"))


class StationMapProcessHost(QWidget):
    """
    Обертка, которая выводит карту в отдельном процессе через QProcess.
    UI в главном окне остаётся живым даже при тяжёлой карте/рендере.
    """

    stationClicked = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.process: Optional[QProcess] = None
        self._stdout_buffer: str = ""
        self._latest_html: Optional[str] = None
        self._current_temp: Optional[Path] = None

        self.status_label = QLabel("Карта откроется в отдельном окне после загрузки списка станций.")
        self.status_label.setWordWrap(True)
        self.open_btn = QPushButton("Открыть карту")
        self.open_btn.clicked.connect(self._on_open_clicked)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.status_label)
        layout.addWidget(self.open_btn)
        layout.addStretch()
        self.setMinimumHeight(320)

        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._stop_process)

    def set_stations(self, stations: List[StationInfo]) -> None:
        html = StationMapView.build_html(stations)
        self.set_html(html)

    def set_html(self, html: str) -> None:
        self._latest_html = html
        temp_path = self._write_temp_file(html)
        if self._is_running():
            self._send_message({"type": "load", "path": temp_path})
            self.status_label.setText("Карта обновлена в отдельном окне.")
        else:
            self._start_process(initial_path=temp_path)

    def _is_running(self) -> bool:
        return self.process is not None and self.process.state() != QProcess.ProcessState.NotRunning

    def _write_temp_file(self, html: str) -> str:
        if self._current_temp and self._current_temp.exists():
            try:
                self._current_temp.unlink()
            except OSError:
                pass
        fd, path = tempfile.mkstemp(prefix="uwyo-map-", suffix=".html")
        with os.fdopen(fd, "w", encoding="utf-8") as fp:
            fp.write(html)
        self._current_temp = Path(path)
        return path

    def _on_open_clicked(self) -> None:
        if self._is_running():
            self._send_message({"type": "show"})
            return
        if self._latest_html:
            self._start_process(initial_path=self._write_temp_file(self._latest_html))
        else:
            empty_html = StationMapView.build_html([])
            self._start_process(initial_path=self._write_temp_file(empty_html))

    def _start_process(self, initial_path: Optional[str] = None) -> None:
        if self._is_running():
            return
        program, args, workdir = self._build_command(initial_path)
        process = QProcess(self)
        if workdir:
            process.setWorkingDirectory(workdir)
        process.readyReadStandardOutput.connect(self._read_stdout)
        process.errorOccurred.connect(self._on_error)
        process.finished.connect(self._on_finished)
        process.started.connect(
            lambda: self.status_label.setText("Запущен отдельный процесс карты.")
        )
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.start(program, args)
        self.process = process
        self.status_label.setText("Запускаем отдельный процесс карты...")

    def _build_command(self, initial_path: Optional[str]) -> tuple[str, List[str], Optional[str]]:
        program = sys.executable
        args: List[str]
        workdir: Optional[str] = None
        root_main = self._find_root_main()

        if getattr(sys, "frozen", False):
            args = ["--map-process"]
        elif root_main and root_main.exists():
            args = [str(root_main), "--map-process"]
            workdir = str(root_main.parent)
        else:
            args = ["-m", "uwyo_downloader", "--map-process"]

        if initial_path:
            args.extend(["--html", initial_path])
        return program, args, workdir

    @staticmethod
    def _find_root_main() -> Optional[Path]:
        try:
            return Path(__file__).resolve().parents[3] / "main.py"
        except IndexError:
            return None

    def _send_message(self, payload: dict) -> None:
        if not self._is_running() or self.process is None:
            return
        try:
            data = (json.dumps(payload) + "\n").encode("utf-8")
            self.process.write(data)
        except Exception:  # noqa: BLE001
            pass

    def _read_stdout(self) -> None:
        if self.process is None:
            return
        data = bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="ignore")
        if not data:
            return
        self._stdout_buffer += data
        while "\n" in self._stdout_buffer:
            line, self._stdout_buffer = self._stdout_buffer.split("\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if payload.get("type") == "station":
                station_id = str(payload.get("id", "")).strip()
                if station_id:
                    self.stationClicked.emit(station_id)

    def _on_error(self, _code) -> None:
        self.status_label.setText("Ошибка процесса карты. Попробуйте открыть снова.")

    def _on_finished(self, *_) -> None:
        self.status_label.setText("Процесс карты завершен.")
        self.process = None

    def _stop_process(self) -> None:
        process = self.process
        self.process = None
        if not process:
            return
        try:
            self._send_message({"type": "quit"})
        except Exception:  # noqa: BLE001
            pass
        process.closeWriteChannel()
        # Ждем нормального выхода, чтобы macOS не показывала crash-диалог
        if process.waitForFinished(5000):
            return
        process.terminate()
        if process.waitForFinished(3000):
            return
        # Не дергаем kill, чтобы не провоцировать "unexpectedly quit" диалог.
