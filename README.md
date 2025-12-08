# UWYO Soundings Downloader

Графическое приложение для быстрой загрузки радиозондовых профилей с `weather.uwyo.edu`. Позволяет выбирать станцию, диапазон дат и шаг, видеть список точек на карте за выбранную дату и скачивать данные с прогресс-баром и возможностью отмены. Разработано yarvod.

## Возможности
- Просмотр доступных станций на выбранную дату (`sounding_json`) с отображением на мини-карте.
- Быстрый выбор станции из таблицы и скачивание профиля за конкретную дату.
- Пакетная загрузка профилей за диапазон дат с шагом и параллельностью, логами и кнопкой отмены.
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
  pyinstaller --noconfirm --windowed --name "profile-downloader-${APP_VERSION}" --paths src main.py
  ```

- CI: `.github/workflows/release.yml` собирает артефакты для macOS/Windows по тегу `v*` или вручную через `workflow_dispatch`, вшивает версию из `github.ref_name` и публикует релизные ZIP.

## Структура
- `main.py` — точка входа.
- `src/uwyo_downloader/` — код приложения (UI, сервисы, модели, версия).
- `scripts/build_macos.sh` — локальная сборка macOS с версией.
- `.github/workflows/release.yml` — GitHub Actions для релизов.

## Автор
@yarvod — идеолог и разработчик проекта.