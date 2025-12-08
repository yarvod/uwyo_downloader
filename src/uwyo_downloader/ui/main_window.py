from datetime import datetime
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QDateTime, QThread, Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QPlainTextEdit,
    QProgressBar,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QDateTimeEdit,
)

from ..config import APP_VERSION, DEFAULT_OUTPUT_DIR
from ..models import StationInfo
from ..utils import build_datetimes
from .map_view import StationMapView
from .workers import DownloadWorker, StationListWorker


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"UWYO Soundings Downloader v{APP_VERSION}")
        self.output_dir = DEFAULT_OUTPUT_DIR
        self.download_thread: Optional[QThread] = None
        self.download_worker: Optional[DownloadWorker] = None
        self.station_thread: Optional[QThread] = None
        self.station_worker: Optional[StationListWorker] = None
        self.stations: List[StationInfo] = []
        self.build_ui()
        self.apply_palette()

    def build_ui(self) -> None:
        main_widget = QWidget()
        main_layout = QHBoxLayout(main_widget)
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(4)
        splitter.addWidget(self.build_download_panel())
        splitter.addWidget(self.build_map_panel())
        splitter.setSizes([420, 620])
        main_layout.addWidget(splitter)
        self.setCentralWidget(main_widget)
        self.resize(1200, 720)

    def build_download_panel(self) -> QWidget:
        box = QGroupBox("Скачать диапазон дат")
        layout = QVBoxLayout(box)

        station_row = QHBoxLayout()
        station_row.addWidget(QLabel("ID станции:"))
        self.station_input = QLineEdit()
        self.station_input.setPlaceholderText("например, 51076")
        station_row.addWidget(self.station_input)
        layout.addLayout(station_row)

        dates_row = QHBoxLayout()
        self.start_dt = QDateTimeEdit(QDateTime.currentDateTime().addDays(-1))
        self.start_dt.setDisplayFormat("yyyy-MM-dd HH:mm")
        self.start_dt.setCalendarPopup(True)
        self.end_dt = QDateTimeEdit(QDateTime.currentDateTime())
        self.end_dt.setDisplayFormat("yyyy-MM-dd HH:mm")
        self.end_dt.setCalendarPopup(True)
        dates_row.addWidget(QLabel("Начало:"))
        dates_row.addWidget(self.start_dt)
        dates_row.addWidget(QLabel("Конец:"))
        dates_row.addWidget(self.end_dt)
        layout.addLayout(dates_row)

        step_row = QHBoxLayout()
        step_row.addWidget(QLabel("Шаг (часы):"))
        self.step_input = QSpinBox()
        self.step_input.setRange(1, 48)
        self.step_input.setValue(12)
        step_row.addWidget(self.step_input)
        layout.addLayout(step_row)

        folder_row = QHBoxLayout()
        self.folder_input = QLineEdit(str(self.output_dir))
        self.folder_input.setPlaceholderText("Папка для сохранения")
        folder_btn = QPushButton("Выбрать...")
        folder_btn.clicked.connect(self.choose_folder)
        folder_row.addWidget(self.folder_input)
        folder_row.addWidget(folder_btn)
        layout.addLayout(folder_row)

        buttons_row = QHBoxLayout()
        self.download_btn = QPushButton("Скачать")
        self.download_btn.clicked.connect(self.start_download)
        self.cancel_btn = QPushButton("Отменить")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.cancel_download)
        buttons_row.addWidget(self.download_btn)
        buttons_row.addWidget(self.cancel_btn)
        layout.addLayout(buttons_row)

        self.progress_label = QLabel("Готово")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_label)
        layout.addWidget(self.progress_bar)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(500)
        self.log.setPlaceholderText("Логи загрузки...")
        layout.addWidget(self.log)
        layout.addStretch()
        return box

    def build_map_panel(self) -> QWidget:
        box = QGroupBox("Карта станций")
        layout = QVBoxLayout(box)

        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("Дата/время:"))
        self.stations_dt = QDateTimeEdit(QDateTime.currentDateTime())
        self.stations_dt.setDisplayFormat("yyyy-MM-dd HH:mm")
        self.stations_dt.setCalendarPopup(True)
        top_row.addWidget(self.stations_dt)
        self.load_stations_btn = QPushButton("Показать станции")
        self.load_stations_btn.clicked.connect(self.load_stations)
        top_row.addWidget(self.load_stations_btn)
        layout.addLayout(top_row)

        self.map_view = StationMapView()
        layout.addWidget(self.map_view)

        self.station_table = QTableWidget()
        self.station_table.setColumnCount(5)
        self.station_table.setHorizontalHeaderLabels(
            ["ID", "Название", "Источник", "Широта", "Долгота"]
        )
        self.station_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.station_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.station_table.horizontalHeader().setStretchLastSection(True)
        self.station_table.itemSelectionChanged.connect(self.fill_station_from_selection)
        layout.addWidget(self.station_table)

        bottom_row = QHBoxLayout()
        self.download_selected_btn = QPushButton("Скачать выбранную")
        self.download_selected_btn.clicked.connect(self.download_selected_station)
        bottom_row.addWidget(self.download_selected_btn)
        self.station_status = QLabel("")
        bottom_row.addWidget(self.station_status)
        layout.addLayout(bottom_row)
        version_row = QHBoxLayout()
        version_row.addStretch()
        self.version_label = QLabel(f"Версия: {APP_VERSION}")
        version_row.addWidget(self.version_label)
        layout.addLayout(version_row)
        return box

    def apply_palette(self) -> None:
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor("#0b1220"))
        palette.setColor(QPalette.ColorRole.Base, QColor("#0f172a"))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#111827"))
        palette.setColor(QPalette.ColorRole.Text, QColor("#e5e7eb"))
        palette.setColor(QPalette.ColorRole.WindowText, QColor("#e5e7eb"))
        palette.setColor(QPalette.ColorRole.Button, QColor("#111827"))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor("#e5e7eb"))
        palette.setColor(QPalette.ColorRole.Highlight, QColor("#22d3ee"))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#0b1220"))
        self.setPalette(palette)
        self.setStyleSheet(
            """
            QGroupBox { border: 1px solid #1f2937; border-radius: 8px; margin-top: 12px; padding: 12px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; color: #9ca3af; }
            QLabel { color: #e5e7eb; }
            QLineEdit, QDateTimeEdit, QPlainTextEdit, QSpinBox, QTableWidget {
                background: #0f172a; border: 1px solid #1f2937; color: #e5e7eb; border-radius: 6px; padding: 6px;
            }
            QPushButton {
                background: #22d3ee; color: #0b1220; border: none; border-radius: 6px; padding: 8px 12px;
                font-weight: 600;
            }
            QPushButton:disabled { background: #1f2937; color: #9ca3af; }
            QProgressBar { background: #0f172a; border: 1px solid #1f2937; border-radius: 6px; text-align: center; }
            QProgressBar::chunk { background: #22d3ee; border-radius: 6px; }
            QTableWidget { gridline-color: #1f2937; }
            """
        )

    def choose_folder(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self, "Выберите папку", str(self.output_dir)
        )
        if selected:
            self.output_dir = Path(selected)
            self.folder_input.setText(selected)

    def start_download(self) -> None:
        if self.download_worker is not None:
            return
        station_id = self.station_input.text().strip()
        if not station_id:
            self.append_log("Укажите ID станции.")
            return
        try:
            datetimes = build_datetimes(
                self.start_dt.dateTime().toPyDateTime(),
                self.end_dt.dateTime().toPyDateTime(),
                self.step_input.value(),
            )
        except Exception as exc:  # noqa: BLE001
            self.append_log(str(exc))
            return

        self.progress_bar.setRange(0, len(datetimes))
        self.progress_bar.setValue(0)
        self.progress_label.setText("Загрузка...")
        self.download_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)

        worker = DownloadWorker(station_id, datetimes, Path(self.folder_input.text()))
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self.on_progress)
        worker.finished.connect(self.on_download_finished)
        worker.log.connect(self.append_log)
        worker.finished.connect(lambda *_: thread.quit())
        worker.finished.connect(lambda *_: worker.deleteLater())
        thread.finished.connect(thread.deleteLater)

        self.download_worker = worker
        self.download_thread = thread
        thread.start()

    def cancel_download(self) -> None:
        if self.download_worker:
            self.download_worker.cancel()
            self.append_log("Останавливаем...")

    def on_progress(self, current: int, total: int, _: str) -> None:
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(current)
        self.progress_label.setText(f"{current}/{total}")

    def on_download_finished(self, success: bool, message: str) -> None:
        self.append_log(message)
        self.progress_label.setText(message)
        self.download_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.download_worker = None
        self.download_thread = None

    def append_log(self, message: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log.appendPlainText(f"[{stamp}] {message}")
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())

    def load_stations(self) -> None:
        if self.station_worker is not None:
            return
        dt = self.stations_dt.dateTime().toPyDateTime()
        self.station_status.setText("Загрузка списка...")
        self.map_view.set_stations([])
        self.station_table.setRowCount(0)

        worker = StationListWorker(dt)
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.loaded.connect(self.on_stations_loaded)
        worker.failed.connect(self.on_stations_failed)
        worker.finished.connect(lambda: thread.quit())
        worker.finished.connect(lambda: worker.deleteLater())
        thread.finished.connect(thread.deleteLater)

        self.station_worker = worker
        self.station_thread = thread
        thread.start()

    def on_stations_loaded(self, stations: List[StationInfo]) -> None:
        self.stations = stations
        self.station_status.setText(f"Найдено станций: {len(stations)}")
        self.station_table.setRowCount(len(stations))
        for row, station in enumerate(stations):
            self.station_table.setItem(row, 0, QTableWidgetItem(station.stationid))
            self.station_table.setItem(row, 1, QTableWidgetItem(station.name))
            self.station_table.setItem(row, 2, QTableWidgetItem(station.src or ""))
            self.station_table.setItem(
                row, 3, QTableWidgetItem(f"{station.lat:.2f}" if station.lat else "")
            )
            self.station_table.setItem(
                row, 4, QTableWidgetItem(f"{station.lon:.2f}" if station.lon else "")
            )
        self.map_view.set_stations(stations)
        self.station_worker = None
        self.station_thread = None

    def on_stations_failed(self, message: str) -> None:
        self.station_status.setText(f"Ошибка: {message}")
        self.append_log(f"Ошибка загрузки списка станций: {message}")
        self.station_worker = None
        self.station_thread = None

    def fill_station_from_selection(self) -> None:
        items = self.station_table.selectedItems()
        if not items:
            return
        station_id = items[0].text()
        self.station_input.setText(station_id)

    def download_selected_station(self) -> None:
        selection = self.station_table.selectionModel().selectedRows()
        if not selection:
            self.append_log("Выберите станцию из списка.")
            return
        row = selection[0].row()
        station = self.stations[row]
        self.station_input.setText(station.stationid)
        self.start_dt.setDateTime(self.stations_dt.dateTime())
        self.end_dt.setDateTime(self.stations_dt.dateTime())
        self.step_input.setValue(12)
        self.append_log(
            f"Скачиваем {station.stationid} за {self.stations_dt.dateTime().toString('yyyy-MM-dd HH:mm')}"
        )
        self.start_download()


def main() -> None:
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
