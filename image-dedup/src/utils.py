"""
Вспомогательные утилиты для проекта.

Этот модуль содержит функции для настройки логирования, вычисления хешей файлов
и проверки расширений файлов изображений.
"""
import hashlib
import logging
from pathlib import Path

from src.config import settings


def setup_logging() -> None:
    """
    Настраивает базовую конфигурацию логирования.

    Логи будут одновременно выводиться в файл (согласно `settings.LOG_FILE`)
    и в стандартный поток вывода (консоль).
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(settings.LOG_FILE),
            logging.StreamHandler()
        ]
    )


def get_file_hash(path: Path, chunk_size: int = 8192) -> str:
    """
    Вычисляет хеш-сумму SHA256 для файла.

    Читает файл по частям, чтобы избежать проблем с большими файлами.

    Args:
        path: Путь к файлу.
        chunk_size: Размер части для чтения в байтах.

    Returns:
        Строка с хеш-суммой в шестнадцатеричном формате или пустая строка
        в случае ошибки чтения файла.
    """
    sha = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            while chunk := f.read(chunk_size):
                sha.update(chunk)
        return sha.hexdigest()
    except OSError:
        # В случае ошибки (например, файл не найден) возвращаем пустой хеш
        return ""


def is_image_file(path: Path) -> bool:
    """
    Проверяет, является ли файл изображением по его расширению.

    Args:
        path: Путь к файлу.

    Returns:
        True, если расширение файла соответствует одному из поддерживаемых
        форматов изображений, иначе False.
    """
    return path.suffix.lower() in {'.jpg', '.jpeg'}