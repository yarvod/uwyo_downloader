from typing import List

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsScene, QGraphicsView

from ..models import StationInfo


class StationMapView(QGraphicsView):
    def __init__(self) -> None:
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(
            self.renderHints()
            | QPainter.Antialiasing
            | QPainter.TextAntialiasing
        )
        self._stations: List[StationInfo] = []
        self.setMinimumHeight(320)
        self.setStyleSheet(
            "QGraphicsView { border: 1px solid #1f2937; background: transparent; }"
        )
        self.draw_scene()

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self.draw_scene()

    def set_stations(self, stations: List[StationInfo]) -> None:
        self._stations = [s for s in stations if s.has_coords]
        self.draw_scene()

    def draw_scene(self) -> None:
        scene = self.scene()
        scene.clear()
        rect = self.viewport().rect()
        width = max(rect.width() - 2, 200)
        height = max(rect.height() - 2, 200)
        scene.setSceneRect(0, 0, width, height)

        bg = QLinearGradient(0, 0, width, height)
        bg.setColorAt(0.0, QColor("#0f172a"))
        bg.setColorAt(1.0, QColor("#111827"))
        scene.addRect(0, 0, width, height, pen=Qt.NoPen, brush=bg)

        grid_pen = QPen(QColor("#1f2937"))
        grid_pen.setWidth(1)
        for lon in range(-180, 181, 60):
            x = self.lon_to_x(lon, width)
            scene.addLine(x, 0, x, height, pen=grid_pen)
        for lat in range(-90, 91, 30):
            y = self.lat_to_y(lat, height)
            scene.addLine(0, y, width, y, pen=grid_pen)

        point_pen = QPen(QColor("#22d3ee"))
        point_pen.setWidth(1)
        for station in self._stations:
            x = self.lon_to_x(station.lon or 0.0, width)
            y = self.lat_to_y(station.lat or 0.0, height)
            item = QGraphicsEllipseItem(x - 3, y - 3, 6, 6)
            item.setBrush(QColor("#22d3ee"))
            item.setPen(point_pen)
            item.setToolTip(f"{station.stationid}\n{station.name}")
            scene.addItem(item)

    @staticmethod
    def lon_to_x(lon: float, width: float) -> float:
        return (lon + 180.0) / 360.0 * width

    @staticmethod
    def lat_to_y(lat: float, height: float) -> float:
        return (90.0 - lat) / 180.0 * height
