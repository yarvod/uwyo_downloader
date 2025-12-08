from typing import List

import folium
from PySide6.QtCore import QUrl
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QVBoxLayout, QWidget

from ..models import StationInfo


class StationMapView(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.webview = QWebEngineView()
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
    def _center_for(stations: List[StationInfo]) -> list[float]:
        coords = [(s.lat, s.lon) for s in stations if s.lat is not None and s.lon is not None]
        if not coords:
            return [0.0, 0.0]
        avg_lat = sum(lat for lat, _ in coords) / len(coords)
        avg_lon = sum(lon for _, lon in coords) / len(coords)
        return [avg_lat, avg_lon]

    def set_stations(self, stations: List[StationInfo]) -> None:
        """
        Рендерим новую HTML-карту с маркерами станций.
        """
        center = self._center_for(stations)
        fmap = folium.Map(location=center, zoom_start=3, tiles="OpenStreetMap", control_scale=True)

        for station in stations:
            if station.lat is None or station.lon is None:
                continue
            tooltip = f"{station.stationid} — {station.name}"
            folium.Marker(
                [station.lat, station.lon],
                tooltip=tooltip,
            ).add_to(fmap)

        html = fmap.get_root().render()
        # baseUrl https to allow external assets
        self.webview.setHtml(html, baseUrl=QUrl("https://local.map/"))
