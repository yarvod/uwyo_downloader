# UWYO Soundings Downloader

Графическое приложение для быстрой загрузки радиозондовых профилей с `weather.uwyo.edu`. Сохраняет станции и выгруженные профили в локальную SQLite-базу (создаётся рядом с исполняемым файлом, путь можно переопределить `UWYO_APP_DATA`), позволяет искать станции по ID/имени, фильтровать загруженные данные и скачивать пакетом с прогресс-баром и возможностью отмены. Разработано yarvod.

## Возможности
- Актуализация списка станций из `sounding_json` с сохранением в SQLite и автодополнением при вводе.
- Поиск станции по ID или имени перед загрузкой.
- Пакетная загрузка профилей за диапазон дат с шагом и параллельностью, логами и кнопкой отмены, запись загруженного текста в БД.
- Просмотр локально сохранённых профилей во вкладке с фильтром по станции и интервалу времени.
- Отрисовка версии приложения (берётся из тега/GitHub Actions или переменной окружения `APP_VERSION`).
- Сборка standalone-бинарей для macOS и Windows через PyInstaller и GitHub Actions.

## Установка и запуск
```bash
python3 -m pip install -r requirements.txt
python3 main.py
```
Альтернатива: `PYTHONPATH=src python3 -m uwyo_downloader`

## Сборка
- Локально (macOS):
  ```bash
  APP_VERSION=v1.0.0 ./scripts/build_macos.sh
  ```
  Если `APP_VERSION` не задан, возьмётся последний git-тег или `dev`.

- PyInstaller вручную:
  ```bash
  APP_VERSION=v1.0.0 python - <<'PY'
  from pathlib import Path; import os
  Path("src/uwyo_downloader/version.py").write_text(f'__version__ = "{os.environ["APP_VERSION"]}"\n')
  PY
  pyinstaller --noconfirm --windowed \
    --name "profile-downloader-${APP_VERSION}" \
    --paths src \
    --icon assets/icons/app.icns \
    --hidden-import logging.config \
    --add-data "assets/icons/icon-256.png:assets/icons" \
    --add-data "src/uwyo_downloader/db/alembic:uwyo_downloader/db/alembic" \
    main.py
  ```
  На Windows используйте `.ico` в `--icon` и `;` в `--add-data`.

- CI: `.github/workflows/release.yml` собирает артефакты для macOS/Windows по тегу `v*` или вручную через `workflow_dispatch`, вшивает версию из `github.ref_name` и публикует релизные ZIP.

## Структура
- `main.py` — точка входа.
- `src/uwyo_downloader/` — код приложения (UI, сервисы, модели, версия).
- `src/uwyo_downloader/db/` — SQLite-обёртка, миграции и репозитории.
- `scripts/build_macos.sh` — локальная сборка macOS с версией.
- `.github/workflows/release.yml` — GitHub Actions для релизов.

## Автор
@yarvod — идеолог и разработчик проекта.
