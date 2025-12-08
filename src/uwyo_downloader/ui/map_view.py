import json
from typing import List

from PySide6.QtCore import QUrl, Signal
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QVBoxLayout, QWidget

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
    const map = L.map('map', {{ zoomControl: true }}).setView(center, 3);
    L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
      maxZoom: 10,
      minZoom: 2,
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
