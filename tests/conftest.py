"""
Общие фикстуры для тестов.
Этот файл автоматически подхватывается pytest.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.db import Base

# Используем БД в памяти для тестов
TEST_DB_URL = "sqlite:///:memory:"


@pytest.fixture(scope="function")
def session():
    """
    Фикстура для создания и очистки сессии БД для каждого теста.
    Доступна для всех тестов в проекте.
    """
    engine = create_engine(TEST_DB_URL)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db_session = Session()
    yield db_session
    db_session.close()
    Base.metadata.drop_all(engine)