# Image Deduplication Pipeline (Debian 12)

Production-ready прототип для поиска и группировки похожих изображений с использованием CLIP (GPU) и PostgreSQL (pgvector).

## Требования

- Debian 12 (Bookworm)
- Python 3.11+
- NVIDIA GPU + Drivers (рекомендуется)
- Docker & Docker Compose (для БД)

## Установка

1. **Клонирование и настройка окружения:**
   ```bash
   git clone https://github.com/your-repo/image-dedup.git
   cd image-dedup
   
   # Создание и активация виртуального окружения
   python3 -m venv .venv
   source .venv/bin/activate
   
   # Установка зависимостей
   pip install -r requirements.txt
   ```

2. **Запуск Базы Данных:**
   ```bash
   docker-compose up -d
   ```
   *Убедитесь, что порт 5432 свободен.*

3. **Инициализация схемы БД:**
   ```bash
   python -m src.main init
   ```

## Использование

### 1. Индексация (Поиск и расчет эмбеддингов)
Сканирует папку рекурсивно, находит JPG, считает векторы на GPU.
```bash
python -m src.main index /path/to/your/images --limit 1000
```
*Опции:*
- `--limit N`: обработать только N файлов.
- `--force`: пересчитать даже если файл не менялся.

### 2. Кластеризация
Группирует похожие изображения (Cosine Similarity > 0.92).
```bash
python -m src.main cluster
```

### 3. Ручной разбор (GUI)
Запускает графический интерфейс для просмотра групп.
```bash
python -m src.main review
```
*В GUI:*
- Слева список групп.
- Справа картинки.
- Кнопка "Keep First": оставляет первую, остальные помечает `to_delete=True`.

## Конфигурация
Настройки находятся в `src/config.py` или могут быть переопределены через `.env` файл:
```env
DB_URL=postgresql+psycopg://user:password@localhost:5432/imagedb
BATCH_SIZE=32
SIMILARITY_THRESHOLD=0.95
```

## Тесты
```bash
pytest
```