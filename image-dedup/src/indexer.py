"""
Модуль для индексации изображений.

Этот модуль отвечает за сканирование директорий, вычисление эмбеддингов
для изображений с помощью модели CLIP и сохранение их в базе данных.
Ключевые функции включают идемпотентную обработку (пропуск уже
проиндексированных и неизмененных файлов) и пакетную обработку
для эффективности.
"""
import logging
from pathlib import Path
from typing import Any, List, Tuple

import open_clip
import torch
from open_clip.model import CLIP
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from torch.cuda.amp.autocast_mode import autocast
from torch.utils.data import DataLoader, Dataset

from src.config import settings
from src.db import ImageRecord, SessionLocal
from src.utils import get_file_hash, is_image_file

logger = logging.getLogger(__name__)

# Определяем тип для функции предобработки, возвращаемой open_clip
PreprocessFn = Any  # open_clip может возвращать разные типы, Any - проще всего
# Возвращаемый тип для __getitem__
DatasetItem = Tuple[torch.Tensor, str, bool]


class ImageDataset(Dataset[DatasetItem]):
    """
    Кастомный `Dataset` для ленивой загрузки и обработки изображений.

    Он принимает список путей к файлам и функцию предобработки.
    В случае ошибки чтения файла (например, битое изображение),
    возвращает тензор-пустышку и флаг `valid=False`.
    """

    def __init__(self, file_paths: List[Path], preprocess: PreprocessFn) -> None:
        """
        Инициализирует датасет.

        Args:
            file_paths: Список путей к файлам изображений.
            preprocess: Функция для предобработки изображений (из CLIP).
        """
        self.file_paths = file_paths
        self.preprocess = preprocess

    def __len__(self) -> int:
        """Возвращает общее количество изображений в датасете."""
        return len(self.file_paths)

    def __getitem__(self, idx: int) -> DatasetItem:
        """
        Загружает, обрабатывает и возвращает одно изображение по индексу.

        Args:
            idx: Индекс изображения в списке `file_paths`.

        Returns:
            Кортеж (image_tensor, path, is_valid):
            - `image_tensor`: Обработанный тензор изображения или пустышка.
            - `path`: Строковый путь к файлу.
            - `is_valid`: `True`, если изображение успешно загружено, иначе `False`.
        """
        path = self.file_paths[idx]
        try:
            image = Image.open(path).convert("RGB")
            image_tensor = self.preprocess(image)
            return image_tensor, str(path), True
        except (UnidentifiedImageError, OSError) as e:
            # Возвращаем пустышку и флаг, что изображение невалидно.
            # Это позволит обработать ошибку в основном цикле, не прерывая батч.
            logger.debug(f"Не удалось прочитать изображение {path}: {e}")
            return torch.zeros((3, 224, 224)), str(path), False


def scan_directory(root: Path) -> List[Path]:
    """
    Рекурсивно сканирует директорию и возвращает список путей к файлам изображений.

    Args:
        root: Корневая директория для сканирования.

    Returns:
        Список объектов `Path` для найденных изображений.
    """
    return [p for p in root.rglob("*") if p.is_file() and is_image_file(p)]


def index_images(root_dir: Path, limit: int = 0, force: bool = False) -> None:
    """
    Основная функция для индексации изображений в директории.

    Процесс состоит из нескольких шагов:
    1. Сканирование директории для поиска всех файлов изображений.
    2. Фильтрация файлов: исключение тех, что уже есть в БД и не изменялись.
    3. Загрузка модели CLIP.
    4. Создание `DataLoader` для пакетной обработки.
    5. Вычисление эмбеддингов и сохранение/обновление записей в БД.

    Args:
        root_dir: Директория с изображениями для индексации.
        limit: Максимальное количество файлов для обработки (0 - без лимита).
        force: Если `True`, переиндексировать все файлы, игнорируя кэш.
    """
    logger.info(f"Сканирование директории: {root_dir}...")
    all_files = scan_directory(root_dir)
    if limit > 0:
        all_files = all_files[:limit]

    logger.info(f"Найдено {len(all_files)} кандидатов на индексацию.")

    # Шаг 1: Фильтрация файлов для обеспечения идемпотентности
    files_to_process: List[Path] = []
    with SessionLocal() as session:
        # Загружаем существующие записи для быстрой проверки
        stmt = select(ImageRecord.path, ImageRecord.mtime, ImageRecord.size_bytes)
        existing_rows = session.execute(stmt).all()
        existing_map = {row.path: (row.mtime, row.size_bytes) for row in existing_rows}

    for p in all_files:
        p_str = str(p.absolute())
        stat = p.stat()

        if not force and p_str in existing_map:
            old_mtime, old_size = existing_map[p_str]
            # Сравниваем время модификации и размер для определения изменений
            if abs(stat.st_mtime - old_mtime) < 0.001 and stat.st_size == old_size:
                continue  # Файл не изменился, пропускаем

        files_to_process.append(p)

    logger.info(f"Новых или измененных файлов для обработки: {len(files_to_process)}")
    if not files_to_process:
        logger.info("Нет файлов для индексации. Завершение.")
        return

    # Шаг 2: Подготовка модели
    device = settings.DEVICE if torch.cuda.is_available() else "cpu"
    logger.info(f"Загрузка модели {settings.CLIP_MODEL_NAME} на устройстве {device}...")
    model: CLIP
    preprocess: Any
    model, _, preprocess = open_clip.create_model_and_transforms(
        settings.CLIP_MODEL_NAME,
        pretrained=settings.CLIP_PRETRAINED,
        device=device,
    )
    model.eval()

    dataset = ImageDataset(files_to_process, preprocess)
    dataloader: DataLoader[DatasetItem] = DataLoader(
        dataset,
        batch_size=settings.BATCH_SIZE,
        num_workers=settings.NUM_WORKERS,
        pin_memory=True,
    )

    # Шаг 3: Вычисление эмбеддингов и сохранение в БД
    with SessionLocal() as session:
        with torch.no_grad(), autocast(enabled=(device == "cuda")):
            for batch_imgs, batch_paths, batch_valid in dataloader:
                batch_imgs = batch_imgs.to(device)

                # Вычисляем эмбеддинги для всего батча,
                # затем отфильтровываем невалидные изображения.
                features = model.encode_image(batch_imgs)
                features /= features.norm(dim=-1, keepdim=True)

                features_cpu = features.cpu().numpy()

                for i, path_str in enumerate(batch_paths):
                    if not batch_valid[i]:
                        logger.warning(f"Пропуск поврежденного изображения: {path_str}")
                        continue

                    p_obj = Path(path_str)
                    stat_res = p_obj.stat()
                    file_hash = get_file_hash(p_obj)

                    # Логика Upsert: обновляем существующую запись или создаем новую
                    record = session.query(ImageRecord).filter_by(path=path_str).first()
                    if record is None:
                        record = ImageRecord(path=path_str)
                        session.add(record)

                    # Обновляем поля записи
                    record.mtime = stat_res.st_mtime
                    record.size_bytes = stat_res.st_size
                    record.file_hash = file_hash
                    record.embedding = features_cpu[i].tolist()
                    record.reviewed = False
                    record.cluster_id = None # Сбрасываем кластер при переиндексации
                    record.to_delete = False

                session.commit()
                logger.info(f"Обработан батч из {len(batch_paths)} изображений.")

    logger.info("Индексация успешно завершена.")