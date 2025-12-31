import datetime
import subprocess
import zlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Импортируем функции из основного скрипта
from exifreader.main import (
    calculate_crc32,
    get_jpg_creation_date,
    get_mov_creation_date,
    safe_move_file,
)


@pytest.fixture
def temp_dir(tmp_path: Path) -> Path:
    """Создает временную директорию для тестов."""
    return tmp_path


def test_calculate_crc32(temp_dir: Path):
    """Тестирует вычисление CRC32."""
    # Создаем тестовый файл
    file_path = temp_dir / "test.txt"
    content = b"hello world"
    file_path.write_bytes(content)

    # Вычисляем CRC32 вручную
    expected_crc = zlib.crc32(content)
    # Проверяем, что функция возвращает тот же результат
    assert calculate_crc32(file_path) == expected_crc


def test_safe_move_file_simple_move(temp_dir: Path):
    """Тестирует простое перемещение файла."""
    source_dir = temp_dir / "source"
    source_dir.mkdir()
    dest_dir = temp_dir / "dest"
    dest_dir.mkdir()

    file_to_move = source_dir / "file.txt"
    file_to_move.write_text("content")

    safe_move_file(file_to_move, dest_dir)

    # Проверяем, что файл перемещен
    assert not file_to_move.exists()
    assert (dest_dir / "file.txt").exists()


def test_safe_move_file_with_rename(temp_dir: Path):
    """Тестирует перемещение с переименованием при коллизии."""
    source_dir = temp_dir / "source"
    source_dir.mkdir()
    dest_dir = temp_dir / "dest"
    dest_dir.mkdir()

    # Создаем файл в исходной и целевой папке
    source_file = source_dir / "file.txt"
    source_file.write_text("new content")
    dest_file = dest_dir / "file.txt"
    dest_file.write_text("old content")

    safe_move_file(source_file, dest_dir)

    # Проверяем, что исходный файл перемещен и переименован
    assert not source_file.exists()
    assert dest_file.exists()  # Старый файл остался
    assert (dest_dir / "file_1.txt").exists()  # Новый файл переименован
    assert (dest_dir / "file_1.txt").read_text() == "new content"


def test_safe_move_identical_file(temp_dir: Path):
    """Тестирует пропуск перемещения идентичного файла."""
    source_dir = temp_dir / "source"
    source_dir.mkdir()
    dest_dir = temp_dir / "dest"
    dest_dir.mkdir()

    content = "identical content"
    source_file = source_dir / "file.txt"
    source_file.write_text(content)
    dest_file = dest_dir / "file.txt"
    dest_file.write_text(content)

    # Мокаем pathlib.Path.unlink, чтобы проверить его вызов
    with patch("pathlib.Path.unlink") as mock_unlink:
        safe_move_file(source_file, dest_dir)
        # Проверяем, что был вызван метод удаления для нашего исходного файла
        # safe_move_file вызывает source_path.unlink()
        mock_unlink.assert_called_once_with()

    # Проверяем, что целевой файл не изменился
    assert dest_file.read_text() == content
    # Исходный файл не был удален, т.к. unlink был замокан
    assert source_file.exists()


@patch("exifread.process_file")
def test_get_jpg_creation_date_from_exif(mock_process_file, temp_dir: Path):
    """Тестирует получение даты из EXIF."""
    file_path = temp_dir / "photo.jpg"
    file_path.touch()

    # Мокаем ответ от exifread
    mock_process_file.return_value = {
        "EXIF DateTimeOriginal": "2023:10:31 10:00:00"
    }
    date = get_jpg_creation_date(file_path)
    assert date == datetime.date(2023, 10, 31)


@patch("exifread.process_file", return_value={})
def test_get_jpg_creation_date_from_mtime(mock_process_file, temp_dir: Path):
    """Тестирует получение даты из времени модификации, если EXIF пуст."""
    file_path = temp_dir / "photo.jpg"
    file_path.touch()

    # Задаем время модификации
    mtime = datetime.datetime(2023, 1, 1).timestamp()

    # Мокируем pathlib.Path.stat, чтобы он возвращал нужное время
    with patch("pathlib.Path.stat", return_value=MagicMock(st_mtime=mtime)):
        date = get_jpg_creation_date(file_path)
        assert date == datetime.date(2023, 1, 1)


@patch("subprocess.run")
def test_get_mov_creation_date_from_ffprobe(mock_subprocess_run, temp_dir: Path):
    """Тестирует получение даты из ffprobe."""
    file_path = temp_dir / "video.mov"
    file_path.touch()

    # Мокаем ответ от ffprobe
    ffprobe_output = {
        "format": {"tags": {"creation_time": "2023-10-31T12:00:00.000000Z"}}
    }
    mock_subprocess_run.return_value = MagicMock(
        stdout=str(ffprobe_output).replace("'", '"'), check=True
    )

    date = get_mov_creation_date(file_path)
    assert date == datetime.date(2023, 10, 31)


@patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "cmd"))
def test_get_mov_creation_date_from_mtime_on_error(
    mock_subprocess_run, temp_dir: Path
):
    """Тестирует получение даты из mtime при ошибке ffprobe."""
    file_path = temp_dir / "video.mov"
    file_path.touch()

    mtime = datetime.datetime(2023, 2, 2).timestamp()
    # Мокируем pathlib.Path.stat, чтобы он возвращал нужное время
    with patch("pathlib.Path.stat", return_value=MagicMock(st_mtime=mtime)):
        date = get_mov_creation_date(file_path)
        assert date == datetime.date(2023, 2, 2)