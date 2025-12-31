# Photo Gallery Editor

Единая утилита для управления вашей фотогалереей. Включает в себя инструменты для сортировки медиафайлов, исправления метаданных и поиска дубликатов.

## Требования

- Python 3.11+
- `virtualenv` для создания виртуального окружения
- Внешние зависимости:
    - `ffmpeg` (для команды `manage sort`)
    - `exiftool` (для команды `manage fix-mp4-date`)
    - `docker` и `docker-compose` (для команды `duplicates *`)

## Установка

1.  **Клонируйте репозиторий:**
    ```bash
    git clone git@github.com:kansoftware/PhotoGalleryEditor.git
    cd PhotoGalleryEditor
    ```

2.  **Установите внешние зависимости:**

    *   **Для Debian/Ubuntu:**
        ```bash
        sudo apt update
        sudo apt install ffmpeg libimage-exiftool-perl docker-compose
        ```
    *   **Для macOS (используя Homebrew):**
        ```bash
        brew install ffmpeg exiftool docker
        ```

3.  **Создайте и активируйте виртуальное окружение:**
    ```bash
    python3 -m venv .venv
    . .venv/bin/activate
    ```

4.  **Установите Python-зависимости:**
    ```bash
    pip install -r requirements.txt
    ```

    *Примечание: если у вас GPU от NVIDIA, для лучшей производительности установите `torch` отдельно:*
    
    ```bash
    pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
    ```


## Использование

Основной интерфейс предоставляется через `src/main.py`.

```bash
python -m src.main --help
```

### Управление файлами (`manage`)

#### Сортировка по дате (`manage sort`)
Сортирует фото и видео по папкам `YYYY-MM-DD` на основе метаданных.

```bash
python -m src.main manage sort --load /path/to/photos --save /path/to/sorted-photos -R
```

#### Исправление даты в MP4 (`manage fix-mp4-date`)
Устанавливает дату создания в MP4-файлах, основываясь на имени родительской папки (например, `2023-12-31/video.mp4`).

```bash
python -m src.main manage fix-mp4-date --root /path/to/videos
```

### Поиск дубликатов (`duplicates`)

#### 1. Запуск базы данных
Перед использованием команд `duplicates` запустите PostgreSQL в Docker:
```bash
docker-compose up -d
```

#### 2. Инициализация БД (`duplicates init`)
```bash
python -m src.main duplicates init
```

#### 3. Индексация (`duplicates index`)
Сканирует изображения и сохраняет их векторные представления.
```bash
python -m src.main duplicates index /path/to/images
```

#### 4. Кластеризация (`duplicates cluster`)
Группирует похожие изображения.
```bash
python -m src.main duplicates cluster
```

#### 5. Просмотр (`duplicates review`)
Запускает GUI для просмотра и удаления дубликатов.
```bash
python -m src.main duplicates review
