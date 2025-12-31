"""Тесты для модуля indexer."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import torch
import pytest
from PIL import Image

from src.indexer import ImageDataset, scan_directory, index_images
from src.db import SessionLocal, ImageRecord


@pytest.fixture
def temp_image_dir(tmp_path: Path) -> Path:
    """Фикстура для создания временной директории с тестовыми изображениями."""
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    # Гарантированно создаем файлы, которые пройдут проверку is_image_file
    Image.new("RGB", (10, 10)).save(image_dir / "img1.jpeg")
    Image.new("RGB", (10, 10)).save(image_dir / "img2.jpg") # Используем .jpg
    (image_dir / "not_an_image.txt").touch()
    # "Битый" файл - имеет расширение, но пустой
    (image_dir / "broken.jpg").touch()

    return image_dir


def test_scan_directory(temp_image_dir: Path):
    """Тестирует функцию сканирования директории."""
    files = scan_directory(temp_image_dir)
    # Ожидаем найти все файлы с "имиджевыми" расширениями, включая битые
    assert len(files) == 3
    paths = {p.name for p in files}
    assert "img1.jpeg" in paths
    assert "img2.jpg" in paths
    assert "broken.jpg" in paths
    assert "not_an_image.txt" not in paths


def test_image_dataset(temp_image_dir: Path):
    """Тестирует ImageDataset, включая обработку поврежденных файлов."""
    files = [
        temp_image_dir / "img1.jpeg", # Используем .jpeg, как в фикстуре
        temp_image_dir / "broken.jpg",  # Этот файл вызовет ошибку
    ]
    # Мок предобработки
    preprocess = MagicMock(return_value=torch.zeros((3, 224, 224)))
    dataset = ImageDataset(files, preprocess)

    assert len(dataset) == 2

    # Валидное изображение
    img, path, is_valid = dataset[0]
    assert is_valid
    assert path == str(files[0])
    assert isinstance(img, torch.Tensor)

    # Невалидное изображение (битый файл)
    img, path, is_valid = dataset[1]
    assert not is_valid
    assert path == str(files[1])
    assert isinstance(img, torch.Tensor) # Должен вернуть тензор-пустышку


@patch("src.indexer.get_file_hash", return_value="mock_hash")
@patch("src.indexer.open_clip.create_model_and_transforms")
@patch("src.indexer.SessionLocal")
def test_index_images_new_files(mock_session_local, mock_create_model, mock_get_hash, temp_image_dir: Path, session):
    """
    Тестирует индексацию новых файлов.
    Проверяет, что для каждого изображения создается запись в БД.
    """
    # Мокаем SessionLocal, чтобы он возвращал нашу тестовую сессию
    mock_session_local.return_value.__enter__.return_value = session

    # Настраиваем мок модели CLIP
    mock_model = MagicMock()
    mock_preprocess = MagicMock(return_value=torch.zeros(3, 224, 224))
    mock_create_model.return_value = (mock_model, None, mock_preprocess)

    # Настраиваем, что будет возвращать encode_image
    features = torch.rand(3, 768) # 3 файла в фикстуре
    features_norm = features / features.norm(dim=-1, keepdim=True)
    mock_model.encode_image.return_value = features_norm

    # Запускаем индексацию
    index_images(temp_image_dir, force=True)

    # Проверяем, что в БД появились записи для ДВУХ валидных файлов
    records = session.query(ImageRecord).all()
    assert len(records) == 2
    paths = {Path(r.path).name for r in records}
    assert "img1.jpeg" in paths
    assert "img2.jpg" in paths
