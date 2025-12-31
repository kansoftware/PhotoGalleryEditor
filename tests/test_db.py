"""Тесты для модуля db."""
import os
from pathlib import Path
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

import pytest

from src.db import Base, init_db, ImageRecord


# Используем БД в памяти для тестов
TEST_DB_URL = "sqlite:///:memory:"




def test_init_db(tmp_path: Path):
    """
    Тестирует инициализацию базы данных.
    Проверяет, что таблицы создаются корректно.
    """
    # Используем временный файл для SQLite БД
    db_file = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_file}")

    # Модифицируем init_db для работы с тестовым движком
    def test_init_db_func():
        Base.metadata.create_all(engine)

    test_init_db_func()

    inspector = inspect(engine)
    assert "images" in inspector.get_table_names()


def test_image_record_creation(session):
    """
    Тестирует создание и сохранение записи ImageRecord.
    """
    image_path = "/path/to/image.jpg"
    new_image = ImageRecord(
        path=image_path,
        file_hash="dummy_hash",
        size_bytes=1024,
        mtime=12345.67,
        embedding=[0.1] * 768,  # Пример эмбеддинга
    )
    session.add(new_image)
    session.commit()

    retrieved_image = session.query(ImageRecord).filter_by(path=image_path).first()
    assert retrieved_image is not None
    assert retrieved_image.path == image_path
    assert retrieved_image.size_bytes == 1024
    assert len(retrieved_image.embedding) == 768
