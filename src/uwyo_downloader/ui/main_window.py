from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QDateTime, Qt
from PySide6.QtGui import QColor, QIcon, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QCompleter,
    QDateTimeEdit,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenuBar,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..config import APP_VERSION, DEFAULT_OUTPUT_DIR
from ..di import Container
from ..models import SoundingRecord, StationInfo
from ..utils import build_datetimes, make_filename
from .style import BASE_STYLESHEET
from .state import drain_soundings, drain_stations
from .workers import DownloadThread, StationThread, retry_on_lock


class MainWindow(QMainWindow):
    def __init__(self, container: Container) -> None:
        super().__init__()
        self.container = container
        self.setWindowTitle(f"UWYO Soundings Downloader v{APP_VERSION}")
        self.output_dir = DEFAULT_OUTPUT_DIR
        self.download_thread: Optional[DownloadThread] = None
        self._download_handled = False
        self.station_thread: Optional[StationThread] = None
        self._station_handled = False
        self.station_progress: Optional[QProgressDialog] = None
        self.sounding_loading = False
        self.stations: List[StationInfo] = []
        self.sounding_records: List[SoundingRecord] = []
        self.icon_path = self._asset_path("assets/icons/icon-256.png")
        self.page_size = 100
        self.current_page = 1
        self.total_records = 0
        self.total_pages = 1

        self.build_ui()
        self.apply_palette()
        self.build_menu()
        if self.icon_path:
            self.setWindowIcon(QIcon(self.icon_path))

        self.refresh_station_cache()
        self.load_soundings()

    def build_ui(self) -> None:
        main_widget = QWidget()
        main_layout = QHBoxLayout(main_widget)
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(4)
        splitter.addWidget(self.build_download_panel())
        splitter.addWidget(self.build_side_panel())
        splitter.setSizes([400, 520])
        main_layout.addWidget(splitter)
        self.setCentralWidget(main_widget)
        self.resize(1050, 700)

    @staticmethod
    def _to_datetime(qdatetime):
        """
        Приводим QDateTime к datetime, поддерживаем старые биндинги без toPython().
        """
        ts = qdatetime.toSecsSinceEpoch()
        return datetime.utcfromtimestamp(ts)

    @classmethod
    def _to_hour_datetime(cls, qdatetime):
        """
        Приводим к предыдущему синоптическому часу (00 или 12 UTC, без будущего).
        """
        dt = cls._to_datetime(qdatetime)
        return cls._previous_synoptic_utc(dt)

    @staticmethod
    def _nearest_synoptic_utc(dt: datetime) -> datetime:
        """
        Возвращает dt (UTC) на ближайший 00 или 12 час (округление).
        """
        total_hours = dt.hour + dt.minute / 60 + dt.second / 3600
        nearest_slot = round(total_hours / 12) * 12
        day_shift = 0
        if nearest_slot >= 24:
            nearest_slot -= 24
            day_shift = 1
        elif nearest_slot < 0:
            nearest_slot += 24
            day_shift = -1
        snapped = dt.replace(
            hour=int(nearest_slot), minute=0, second=0, microsecond=0
        )
        if day_shift:
            snapped = snapped + timedelta(days=day_shift)
        return snapped

    @staticmethod
    def _previous_synoptic_utc(dt: datetime) -> datetime:
        """
        Возвращает предыдущее синоптическое время (00 или 12 UTC),
        без перехода в будущее. Если сейчас 11 UTC -> 00, если 13 UTC -> 12.
        """
        hour_slot = 12 if dt.hour >= 12 else 0
        return dt.replace(hour=hour_slot, minute=0, second=0, microsecond=0)

    @staticmethod
    def _extract_station_id(raw: str) -> str:
        """
        Достаёт ID станции из строки вида "12345 — Name" или "ABCD Name".
        """
        cleaned = raw.strip()
        if not cleaned:
            return ""
        for sep in ("—", "–", "-"):
            if sep in cleaned:
                cleaned = cleaned.split(sep, 1)[0].strip()
                break
        if " " in cleaned:
            first = cleaned.split()[0].strip()
            if first.isdigit() or first.isupper():
                return first
        return cleaned

    @classmethod
    def _current_synoptic_qdatetime(cls) -> QDateTime:
        now_utc = datetime.utcnow()
        snapped = cls._previous_synoptic_utc(now_utc)
        return QDateTime.fromSecsSinceEpoch(int(snapped.timestamp()), Qt.UTC)

    def build_download_panel(self) -> QWidget:
        box = QGroupBox("Скачать диапазон дат")
        layout = QVBoxLayout(box)

        station_row = QHBoxLayout()
        station_row.addWidget(QLabel("Станция:"))
        self.station_input = QLineEdit()
        self.station_input.setPlaceholderText("ID или название из базы")
        station_row.addWidget(self.station_input)
        self.station_lookup_btn = QPushButton("Найти")
        self.station_lookup_btn.clicked.connect(self.try_resolve_station)
        station_row.addWidget(self.station_lookup_btn)
        layout.addLayout(station_row)

        self.station_hint = QLabel("")
        layout.addWidget(self.station_hint)

        dates_row = QHBoxLayout()
        start_dt_default = self._current_synoptic_qdatetime().addDays(-1)
        self.start_dt = QDateTimeEdit(start_dt_default)
        self.start_dt.setDisplayFormat("yyyy-MM-dd HH:mm")
        self.start_dt.setCalendarPopup(True)
        end_dt_default = self._current_synoptic_qdatetime()
        self.end_dt = QDateTimeEdit(end_dt_default)
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

        save_row = QHBoxLayout()
        self.save_to_folder_checkbox = QCheckBox("Сохранять файлы в папку")
        self.save_to_folder_checkbox.setChecked(True)
        self.save_to_folder_checkbox.stateChanged.connect(self._toggle_folder_inputs)
        save_row.addWidget(self.save_to_folder_checkbox)
        save_row.addStretch()
        layout.addLayout(save_row)

        folder_row = QHBoxLayout()
        self.folder_input = QLineEdit(str(self.output_dir))
        self.folder_input.setPlaceholderText("Папка для сохранения")
        folder_btn = QPushButton("Выбрать...")
        folder_btn.clicked.connect(self.choose_folder)
        folder_row.addWidget(self.folder_input)
        folder_row.addWidget(folder_btn)
        self.folder_row_widget = QWidget()
        self.folder_row_widget.setLayout(folder_row)
        layout.addWidget(self.folder_row_widget)
        self._toggle_folder_inputs(self.save_to_folder_checkbox.isChecked())

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

        layout.addStretch()
        return box

    def build_side_panel(self) -> QWidget:
        box = QGroupBox("Локальные данные")
        layout = QVBoxLayout(box)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.build_stations_tab(), "Станции")
        self.tabs.addTab(self.build_data_tab(), "Профили")
        layout.addWidget(self.tabs)
        return box

    def build_stations_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        control_row = QHBoxLayout()
        control_row.addWidget(QLabel("Дата/время:"))
        self.stations_dt = QDateTimeEdit(self._current_synoptic_qdatetime())
        self.stations_dt.setDisplayFormat("yyyy-MM-dd HH:mm")
        self.stations_dt.setCalendarPopup(True)
        control_row.addWidget(self.stations_dt)
        self.load_stations_btn = QPushButton("Актуализировать")
        self.load_stations_btn.clicked.connect(self.load_stations)
        control_row.addWidget(self.load_stations_btn)
        layout.addLayout(control_row)

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Поиск:"))
        self.station_filter_input = QLineEdit()
        self.station_filter_input.setPlaceholderText("Фильтр по названию или ID")
        self.station_filter_input.textChanged.connect(self.apply_station_filter)
        search_row.addWidget(self.station_filter_input)
        layout.addLayout(search_row)

        self.station_table = QTableWidget()
        self.station_table.setColumnCount(6)
        self.station_table.setHorizontalHeaderLabels(
            ["ID", "Название", "Источник", "Обновлено", "Широта", "Долгота"]
        )
        self.station_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.station_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        header: QHeaderView = self.station_table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(50)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.resizeSection(1, 200)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.station_table.itemSelectionChanged.connect(self.fill_station_from_selection)
        self.station_table.setHorizontalScrollMode(
            QTableWidget.ScrollMode.ScrollPerPixel
        )
        self.station_table.setSizeAdjustPolicy(
            QTableWidget.SizeAdjustPolicy.AdjustIgnored
        )
        layout.addWidget(self.station_table)
        layout.setStretch(2, 1)

        bottom_row = QHBoxLayout()
        self.station_status = QLabel("")
        bottom_row.addWidget(self.station_status)
        bottom_row.addStretch()
        layout.addLayout(bottom_row)
        return tab

    def build_data_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Станция:"))
        self.sounding_station_search = QLineEdit()
        self.sounding_station_search.setPlaceholderText("Поиск по ID или названию (БД)")
        self.sounding_station_search.returnPressed.connect(
            lambda: self.load_soundings(reset_page=True)
        )
        filter_row.addWidget(self.sounding_station_search)
        filter_row.addStretch()
        self.apply_filters_btn = QPushButton("Найти")
        self.apply_filters_btn.clicked.connect(lambda: self.load_soundings(reset_page=True))
        filter_row.addWidget(self.apply_filters_btn)
        layout.addLayout(filter_row)

        pagination_row = QHBoxLayout()
        self.prev_page_btn = QPushButton("← Назад")
        self.prev_page_btn.clicked.connect(lambda: self.change_page(-1))
        self.next_page_btn = QPushButton("Вперед →")
        self.next_page_btn.clicked.connect(lambda: self.change_page(1))
        self.pagination_label = QLabel("Страница 1/1 (0)")
        pagination_row.addWidget(self.prev_page_btn)
        pagination_row.addWidget(self.next_page_btn)
        pagination_row.addWidget(self.pagination_label)
        pagination_row.addStretch()
        layout.addLayout(pagination_row)

        splitter = QSplitter(Qt.Vertical)

        self.sounding_table = QTableWidget()
        self.sounding_table.setColumnCount(4)
        self.sounding_table.setHorizontalHeaderLabels(
            ["ID", "Станция", "Дата", "Загружено"]
        )
        self.sounding_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.sounding_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.sounding_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.sounding_table.customContextMenuRequested.connect(
            self._on_sounding_context_menu
        )
        header: QHeaderView = self.sounding_table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(50)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.resizeSection(1, 160)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.sounding_table.itemSelectionChanged.connect(
            self.on_sounding_selection_changed
        )
        self.sounding_table.setHorizontalScrollMode(
            QTableWidget.ScrollMode.ScrollPerPixel
        )
        self.sounding_table.setAutoScroll(True)
        self.sounding_table.setSizeAdjustPolicy(
            QTableWidget.SizeAdjustPolicy.AdjustIgnored
        )
        splitter.addWidget(self.sounding_table)

        self.payload_table = QTableWidget()
        self.payload_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.payload_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.payload_table.horizontalHeader().setStretchLastSection(False)
        self.payload_table.horizontalHeader().setMinimumSectionSize(50)
        splitter.addWidget(self.payload_table)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter)

        return tab

    def build_menu(self) -> None:
        menu_bar: QMenuBar = self.menuBar()
        about_action = menu_bar.addAction("О приложении")
        about_action.triggered.connect(self.show_about)

    def show_about(self) -> None:
        QMessageBox.information(
            self,
            "О приложении",
            f"UWYO Soundings Downloader\nВерсия: {APP_VERSION}\nАвтор: yarvod",
        )

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
        self.setStyleSheet(BASE_STYLESHEET)

    def choose_folder(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self, "Выберите папку", str(self.output_dir)
        )
        if selected:
            self.output_dir = Path(selected)
            self.folder_input.setText(selected)

    def try_resolve_station(self) -> None:
        query = self.station_input.text().strip()
        station = self.resolve_station(query)
        if station:
            self.station_input.setText(station.stationid)
            self.station_hint.setText(f"{station.stationid} — {station.name}")
        else:
            self.station_hint.setText("Станция не найдена в базе. Актуализируйте список.")

    def start_download(self) -> None:
        if self.download_thread is not None:
            return
        query_raw = self.station_input.text().strip()
        station_id = self._extract_station_id(query_raw)
        query = station_id or query_raw
        if not query:
            self.append_log("Укажите ID станции.")
            return
        station = self.resolve_station(query)
        if station is None:
            self.append_log("Станция не найдена в базе. Обновите список станций.")
            self.station_hint.setText("Станция не найдена в базе.")
            return
        try:
            datetimes = build_datetimes(
                self._to_hour_datetime(self.start_dt.dateTime()),
                self._to_hour_datetime(self.end_dt.dateTime()),
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
        self._download_handled = False

        target_dir = Path(self.folder_input.text()).expanduser()
        self.output_dir = target_dir
        thread = DownloadThread(
            station.stationid,
            datetimes,
            target_dir,
            station,
            save_to_disk=self.save_to_folder_checkbox.isChecked(),
        )
        thread.progress.connect(self.on_progress)
        thread.done.connect(self._on_download_done)
        thread.finished.connect(lambda: self._on_download_finished("Остановлено"))

        self.download_thread = thread
        thread.start()
        self.station_hint.setText(f"{station.stationid} — {station.name}")

    def cancel_download(self) -> None:
        if self.download_thread:
            self.download_thread.terminate()
            self.append_log("Останавливаем...")

    def on_progress(self, current: int, total: int) -> None:
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(current)
        self.progress_label.setText(f"{current}/{total}")

    def _on_download_done(self, success: bool, message: str) -> None:
        if self._download_handled:
            return
        self._download_handled = True
        self._finalize_download(success, message)

    def _on_download_finished(self, message: str) -> None:
        if self._download_handled:
            return
        self._download_handled = True
        self._finalize_download(False, message)

    def _finalize_download(self, success: bool, message: str) -> None:
        payloads = drain_soundings()
        if payloads:
            try:
                def _write() -> int:
                    with self.container.session() as session:
                        station_repo = self.container.station_repo(session)
                        sounding_repo = self.container.sounding_repo(session)
                        saved = 0
                        for item in payloads:
                            station_repo.ensure_station(item.station_id, item.station_name)
                            sounding_repo.upsert_sounding(
                                station_id=item.station_id,
                                station_name=item.station_name,
                                captured_at=item.captured_at,
                                payload_json=item.payload_json,
                            )
                            saved += 1
                        return saved

                saved = retry_on_lock(_write, retries=5, delay=0.15)
                self.append_log(f"В БД записано профилей: {saved}")
                self.load_soundings(reset_page=True)
            except Exception as exc:  # noqa: BLE001
                self.append_log(f"Ошибка сохранения в БД: {exc}")
        self.append_log(message)
        self.progress_label.setText(message[:30])
        self.download_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.download_thread = None

    def append_log(self, message: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{stamp}] {message}"
        print(line, flush=True)

    def _toggle_folder_inputs(self, checked: bool | int) -> None:
        visible = bool(checked)
        self.folder_input.setEnabled(visible)
        if hasattr(self, "folder_row_widget"):
            self.folder_row_widget.setVisible(visible)

    def load_stations(self) -> None:
        if self.station_thread is not None:
            return
        dt = self._to_hour_datetime(self.stations_dt.dateTime())
        self.station_status.setText("Загрузка списка...")
        self.load_stations_btn.setEnabled(False)
        self.station_table.setEnabled(False)
        self.station_filter_input.setEnabled(False)
        self._show_station_progress("Загрузка списка станций...")
        self._station_handled = False

        thread = StationThread(dt)
        thread.done.connect(self._on_stations_done)
        thread.finished.connect(lambda: self._on_stations_finished("Отменено"))

        self.station_thread = thread
        thread.start()

    def _on_stations_done(self, success: bool, message: str) -> None:
        if self._station_handled:
            return
        self._station_handled = True
        self._finalize_stations(success, message)

    def _on_stations_finished(self, message: str) -> None:
        if self._station_handled:
            return
        self._station_handled = True
        self._finalize_stations(False, message)

    def _finalize_stations(self, success: bool, message: str) -> None:
        stations = drain_stations()
        if success and stations:
            try:
                def _write() -> int:
                    with self.container.session() as session:
                        repo = self.container.station_repo(session)
                        return repo.upsert_many(stations)

                saved = retry_on_lock(_write, retries=5, delay=0.15)
                self.append_log(f"Станций сохранено: {saved}")
            except Exception as exc:  # noqa: BLE001
                self.append_log(f"Ошибка сохранения станций: {exc}")
                self._finish_station_update(f"Ошибка: {exc}")
                self.station_thread = None
                return
            try:
                with self.container.session() as session:
                    repo = self.container.station_repo(session)
                    db_stations = repo.list_all()
                self.stations = db_stations
                self.populate_station_table()
                self.refresh_station_completers()
                self._finish_station_update(f"Станций в базе: {len(db_stations)}")
            except Exception as exc:  # noqa: BLE001
                self.append_log(f"Ошибка чтения БД: {exc}")
                self._finish_station_update(f"Ошибка: {exc}")
        else:
            self.append_log(message)
            self._finish_station_update(message)

    def _finish_station_update(self, status: Optional[str] = None) -> None:
        self.station_thread = None
        if status is not None:
            self.station_status.setText(status)
        self.load_stations_btn.setEnabled(True)
        self.station_table.setEnabled(True)
        self.station_filter_input.setEnabled(True)
        self._close_station_progress()

    def fill_station_from_selection(self) -> None:
        items = self.station_table.selectedItems()
        if not items:
            return
        station_id = items[0].text()
        self.station_input.setText(station_id)
        station = self.resolve_station(station_id)
        if station:
            self.station_hint.setText(f"{station.stationid} — {station.name}")

    def apply_station_filter(self) -> None:
        query = self.station_filter_input.text().strip().lower()
        row_count = self.station_table.rowCount()
        visible_rows: List[int] = []
        self.station_table.setUpdatesEnabled(False)
        for row in range(row_count):
            id_item = self.station_table.item(row, 0)
            name_item = self.station_table.item(row, 1)
            hay = (
                (id_item.text() if id_item else "")
                + " "
                + (name_item.text() if name_item else "")
            ).lower()
            visible = query in hay
            self.station_table.setRowHidden(row, not visible)
            if visible:
                visible_rows.append(row)
        if visible_rows:
            self.station_table.selectRow(visible_rows[0])
        self.station_table.setUpdatesEnabled(True)

    def refresh_station_cache(self) -> None:
        try:
            with self.container.session() as session:
                repo = self.container.station_repo(session)
                self.stations = repo.list_all()
                self.populate_station_table()
                self.refresh_station_completers()
                self.station_status.setText(f"Станций в базе: {len(self.stations)}")
        except Exception as exc:  # noqa: BLE001
            self.station_status.setText(f"Ошибка чтения БД: {exc}")
            self.append_log(f"Ошибка чтения БД: {exc}")

    def populate_station_table(self) -> None:
        self.station_table.setUpdatesEnabled(False)
        self.station_table.setRowCount(len(self.stations))
        for row, station in enumerate(self.stations):
            self.station_table.setItem(row, 0, QTableWidgetItem(station.stationid))
            self.station_table.setItem(row, 1, QTableWidgetItem(station.name))
            self.station_table.setItem(row, 2, QTableWidgetItem(station.src or ""))
            updated = (
                station.updated_at.strftime("%Y-%m-%d %H:%M")
                if station.updated_at
                else ""
            )
            self.station_table.setItem(row, 3, QTableWidgetItem(updated))
            self.station_table.setItem(
                row, 4, QTableWidgetItem(f"{station.lat:.2f}" if station.lat else "")
            )
            self.station_table.setItem(
                row, 5, QTableWidgetItem(f"{station.lon:.2f}" if station.lon else "")
            )
        self.apply_station_filter()
        self.station_table.setUpdatesEnabled(True)

    def refresh_station_completers(self) -> None:
        suggestions = [f"{s.stationid} — {s.name}" for s in self.stations]
        completer = QCompleter(suggestions, self)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        completer.activated.connect(self._on_station_completed)
        self.station_input.setCompleter(completer)

        if hasattr(self, "sounding_station_search"):
            alt = QCompleter(suggestions, self)
            alt.setCaseSensitivity(Qt.CaseInsensitive)
            alt.setFilterMode(Qt.MatchContains)
            alt.activated.connect(self._on_sounding_search_completed)
            self.sounding_station_search.setCompleter(alt)

    def _on_station_completed(self, text: str) -> None:
        station_id = self._extract_station_id(text)
        self.station_input.setText(station_id)
        station = self.resolve_station(station_id)
        if station:
            self.station_hint.setText(f"{station.stationid} — {station.name}")

    def _on_sounding_search_completed(self, text: str) -> None:
        station_id = self._extract_station_id(text)
        self.sounding_station_search.setText(station_id)

    def resolve_station(self, query: str) -> Optional[StationInfo]:
        cleaned = query.strip()
        station_id = self._extract_station_id(cleaned)
        search_term = station_id or cleaned
        if not search_term:
            return None
        with self.container.session() as session:
            repo = self.container.station_repo(session)
            if station_id:
                exact = repo.get_by_id(station_id)
                if exact:
                    return exact
            matches = repo.search(search_term, limit=10)
        if not matches:
            return None
        if len(matches) > 1:
            self.append_log(
                f"Найдено {len(matches)} станций по запросу '{query}', использую {matches[0].stationid}"
            )
        return matches[0]

    def load_soundings(self, reset_page: bool = False) -> None:
        if self.sounding_loading:
            return
        if reset_page:
            self.current_page = 1
        self.sounding_loading = True
        try:
            station_query = self.sounding_station_search.text().strip() or None

            def _read_soundings() -> tuple[list[SoundingRecord], int]:
                with self.container.session() as session:
                    station_ids: Optional[list[str]] = None
                    if station_query:
                        parsed_id = self._extract_station_id(station_query)
                        station_repo = self.container.station_repo(session)
                        if parsed_id and not station_repo.get_by_id(parsed_id):
                            self.current_page = 1
                            self.total_pages = 1
                            self.total_records = 0
                            return [], 0
                        station_ids = [parsed_id] if parsed_id else None
                    repo = self.container.sounding_repo(session)
                    total = repo.count(
                        station_ids=station_ids,
                        start=None,
                        end=None,
                    )
                    total_pages = max(1, (total + self.page_size - 1) // self.page_size)
                    page = min(self.current_page, total_pages)
                    offset = (page - 1) * self.page_size
                    records = repo.list(
                        station_ids=station_ids,
                        start=None,
                        end=None,
                        limit=self.page_size,
                        offset=offset,
                    )
                    self.current_page = page
                    self.total_pages = total_pages
                    self.total_records = total
                    return records, total

            records, _ = retry_on_lock(_read_soundings, retries=5, delay=0.1)
            self.sounding_records = records
            self.populate_sounding_table()
            self._update_pagination()
        except Exception as exc:  # noqa: BLE001
            self.sounding_records = []
            self.populate_sounding_table()
            self.append_log(f"Ошибка чтения профилей: {exc}")
            self.total_records = 0
            self.total_pages = 1
            self.current_page = 1
            self._update_pagination()
        finally:
            self.sounding_loading = False

    def populate_sounding_table(self) -> None:
        self.sounding_table.setRowCount(len(self.sounding_records))
        for row, record in enumerate(self.sounding_records):
            self.sounding_table.setItem(
                row, 0, QTableWidgetItem(str(record.record_id))
            )
            station_label = record.station_name or record.station_id
            self.sounding_table.setItem(
                row, 1, QTableWidgetItem(f"{record.station_id} — {station_label}")
            )
            self.sounding_table.setItem(
                row,
                2,
                QTableWidgetItem(record.captured_at.strftime("%Y-%m-%d %H:%M")),
            )
            self.sounding_table.setItem(
                row,
                3,
                QTableWidgetItem(record.downloaded_at.strftime("%Y-%m-%d %H:%M")),
            )
        if self.sounding_records:
            self.sounding_table.selectRow(0)
            self.display_payload(self.sounding_records[0])
        else:
            self.clear_payload_view()

    def on_sounding_selection_changed(self) -> None:
        selection = self.sounding_table.selectionModel().selectedRows()
        if not selection:
            self.clear_payload_view()
            return
        row = selection[0].row()
        if 0 <= row < len(self.sounding_records):
            self.display_payload(self.sounding_records[row])

    def change_page(self, delta: int) -> None:
        target = self.current_page + delta
        if target < 1 or target > self.total_pages:
            return
        self.current_page = target
        self.load_soundings()

    def _update_pagination(self) -> None:
        self.total_pages = max(1, self.total_pages)
        self.pagination_label.setText(
            f"Страница {self.current_page}/{self.total_pages} (всего {self.total_records})"
        )
        self.prev_page_btn.setEnabled(self.current_page > 1)
        self.next_page_btn.setEnabled(self.current_page < self.total_pages)

    def reset_sounding_filters(self) -> None:
        self.sounding_station_search.clear()
        self.load_soundings(reset_page=True)

    def display_payload(self, record: SoundingRecord) -> None:
        payload = record.parsed_payload()
        columns = payload.get("columns") or []
        rows = payload.get("rows") or []
        self.payload_table.setUpdatesEnabled(False)
        self.payload_table.setColumnCount(len(columns))
        self.payload_table.setRowCount(len(rows))
        self.payload_table.setHorizontalHeaderLabels([str(c) for c in columns])
        for r_idx, row in enumerate(rows):
            for c_idx, col in enumerate(columns):
                val = row.get(col, "")
                item = QTableWidgetItem(str(val))
                self.payload_table.setItem(r_idx, c_idx, item)
        self.payload_table.resizeColumnsToContents()
        self.payload_table.setUpdatesEnabled(True)

    def _payload_to_text(self, record: SoundingRecord) -> str:
        payload = record.parsed_payload()
        raw = payload.get("raw")
        if isinstance(raw, str) and raw.strip():
            return raw
        return record.payload_json

    def _on_sounding_context_menu(self, pos) -> None:
        row = self.sounding_table.rowAt(pos.y())
        if row < 0 or row >= len(self.sounding_records):
            return
        self.sounding_table.selectRow(row)
        record = self.sounding_records[row]
        menu = QMenu(self)
        save_action = menu.addAction("Сохранить профиль в папку...")
        chosen = menu.exec(self.sounding_table.mapToGlobal(pos))
        if chosen == save_action:
            self._save_sounding_record(record)

    def _save_sounding_record(self, record: SoundingRecord) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "Выберите папку для сохранения",
            str(self.output_dir),
        )
        if not folder:
            return
        target_dir = Path(folder).expanduser()
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            file_path = make_filename(
                record.station_name or record.station_id,
                record.captured_at,
                target_dir,
            )
            file_path.write_text(self._payload_to_text(record), encoding="utf-8")
            self.append_log(f"Профиль сохранён: {file_path}")
        except Exception as exc:  # noqa: BLE001
            self.append_log(f"Не удалось сохранить профиль: {exc}")
            QMessageBox.warning(self, "Ошибка сохранения", str(exc))

    def clear_payload_view(self) -> None:
        self.payload_table.clearContents()
        self.payload_table.setRowCount(0)
        self.payload_table.setColumnCount(0)

    def _show_station_progress(self, message: str) -> None:
        dlg = QProgressDialog(message, "Отменить", 0, 0, self)
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.setAutoClose(False)
        dlg.setAutoReset(False)
        dlg.canceled.connect(self._cancel_station_update)
        dlg.show()
        self.station_progress = dlg

    def _close_station_progress(self) -> None:
        if self.station_progress:
            self.station_progress.close()
            self.station_progress = None

    def _cancel_station_update(self) -> None:
        if self.station_thread:
            try:
                self.station_thread.terminate()
                self.append_log("Останавливаем актуализацию станций...")
            except Exception:  # noqa: BLE001
                pass

    @staticmethod
    def _asset_path(rel: str) -> Optional[str]:
        """
        Resolve asset path for both dev and PyInstaller bundle.
        """
        base_paths = []
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            base_paths.append(Path(sys._MEIPASS))  # type: ignore[attr-defined]
        try:
            base_paths.append(Path(__file__).resolve().parents[3])  # project root
        except IndexError:
            pass
        for base in base_paths:
            candidate = base / rel
            if candidate.exists():
                return str(candidate)
        return None


def main() -> None:
    from PySide6.QtWidgets import QApplication
    from ..di import get_container

    container = get_container()
    container.ensure_ready()
    app = QApplication(sys.argv)
    window = MainWindow(container)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
