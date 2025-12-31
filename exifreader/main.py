import argparse
import datetime
import json
import subprocess
import zlib
from pathlib import Path
from typing import Optional

import exifread


def calculate_crc32(file_path: Path) -> int:
    """Вычисляет CRC32 для файла."""
    hash_crc32 = 0
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_crc32 = zlib.crc32(chunk, hash_crc32)
    return hash_crc32


def safe_move_file(source_path: Path, dest_dir: Path):
    """
    Перемещает файл в целевую директорию с проверкой на существование
    и сравнением CRC32 в случае коллизии имен.
    """
    dest_dir.mkdir(exist_ok=True)

    dest_path = dest_dir / source_path.name

    if dest_path.exists():
        # Файл с таким именем уже существует, сравниваем CRC32
        source_crc = calculate_crc32(source_path)
        dest_crc = calculate_crc32(dest_path)

        if source_crc == dest_crc:
            # Файлы идентичны, пропускаем
            print(f"Skipping identical file: {source_path.name}")
            # Удаляем исходный файл, так как он является дубликатом
            # source_path.unlink()
            # print(f"Removed duplicate file: {source_path.name}")
            return
        else:
            # Файлы разные, ищем новое имя
            i = 1
            while True:
                new_name = f"{source_path.stem}_{i}{source_path.suffix}"
                new_dest_path = dest_dir / new_name
                if not new_dest_path.exists():
                    source_path.rename(new_dest_path)
                    print(
                        f"File '{source_path.name}' renamed to '{new_name}' and moved to '{dest_dir}'"
                    )
                    break
                i += 1
    else:
        # Файл не существует, просто перемещаем
        source_path.rename(dest_path)
        print(f"File '{source_path.name}' moved to '{dest_dir}'")


def get_jpg_creation_date(file_path: Path) -> datetime.date:
    """Извлекает дату создания из JPEG файла (EXIF или дата изменения)."""
    with open(file_path, "rb") as f:
        tags = exifread.process_file(f, details=False, stop_tag="EXIF DateTimeOriginal")
        if "EXIF DateTimeOriginal" in tags:
            date_str = str(tags["EXIF DateTimeOriginal"])
            try:
                return datetime.datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S").date()
            except ValueError:
                pass  # Если формат даты некорректный, переходим к дате изменения

    return datetime.datetime.fromtimestamp(file_path.stat().st_mtime).date()


def get_mov_creation_date(file_path: Path) -> datetime.date:
    """
    Извлекает дату создания из медиафайла с помощью ffprobe.
    Если дата создания недоступна, возвращает дату изменения файла.
    """
    try:
        cmd = [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(file_path),
        ]
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            text=True,
            encoding="utf-8",
        )
        data = json.loads(result.stdout)

        creation_time_str: Optional[str] = None
        if "format" in data and "tags" in data.get("format", {}):
            creation_time_str = data["format"]["tags"].get("creation_time")

        if not creation_time_str and "streams" in data:
            for stream in data.get("streams", []):
                if "tags" in stream:
                    creation_time_str = stream["tags"].get("creation_time")
                    if creation_time_str:
                        break

        if creation_time_str:
            # ffprobe может возвращать время в разных форматах, пробуем несколько
            try:
                if creation_time_str.endswith("Z"):
                    creation_time_str = creation_time_str[:-1] + "+00:00"
                return datetime.datetime.fromisoformat(creation_time_str).date()
            except ValueError:
                # Попробуем разобрать другой возможный формат
                return datetime.datetime.strptime(
                    creation_time_str, "%Y-%m-%dT%H:%M:%S.%f"
                ).date()

    except (
        subprocess.CalledProcessError,
        FileNotFoundError,
        json.JSONDecodeError,
        KeyError,
        ValueError,
    ) as e:
        print(f"Could not get creation date for {file_path.name} via ffprobe: {e}")

    return datetime.datetime.fromtimestamp(file_path.stat().st_mtime).date()


def process_files(source_dir: Path, save_dir: Path, recursive: bool):
    """Рекурсивно обходит папки и перемещает файлы."""
    print(f"Processing files from: {source_dir}")
    if recursive:
        # Используем rglob для рекурсивного поиска
        files_to_process = source_dir.rglob("*")
    else:
        # Используем glob для нерекурсивного поиска
        files_to_process = source_dir.glob("*")

    # Фильтруем, оставляя только файлы
    files_to_process = [f for f in files_to_process if f.is_file()]

    for file_path in files_to_process:
        try:
            date: Optional[datetime.date] = None
            suffix = file_path.suffix.lower()

            if suffix in [".jpg", ".jpeg"]:
                date = get_jpg_creation_date(file_path)
            elif suffix in [".mov", ".mp4", ".mkv", ".avi", ".mts"]:
                date = get_mov_creation_date(file_path)
            else:
                # Пропускаем неподдерживаемые файлы
                continue

            if date:
                target_dir = save_dir / date.isoformat()
                print(f"Processing: {file_path.name} -> {target_dir}")
                safe_move_file(file_path, target_dir)

        except Exception as e:
            # Логируем ошибку, но продолжаем обработку других файлов
            print(f"FATAL: Error processing {file_path.name}: {e}")


def main():
    """Основная функция для парсинга аргументов и запуска обработки."""
    parser = argparse.ArgumentParser(
        description="Организация фотографий и видео по датам EXIF/создания."
    )
    parser.add_argument(
        "-R",
        "--recursive",
        action="store_true",
        help="Рекурсивный обход исходной папки.",
    )
    parser.add_argument(
        "--load",
        type=Path,
        default=Path("."),
        help="Путь к папке с исходными файлами (по умолчанию: текущая директория).",
    )
    parser.add_argument(
        "--save",
        type=Path,
        default=None,
        help="Путь для сохранения отсортированных файлов (по умолчанию: папка --load).",
    )

    args = parser.parse_args()

    # Определяем абсолютные пути
    source_path: Path = args.load.resolve()
    save_path: Path = args.save.resolve() if args.save else source_path

    if not source_path.is_dir():
        print(f"Ошибка: Исходная папка '{source_path}' не существует.")
        exit(1)

    # Создаем папку для сохранения, если ее нет
    save_path.mkdir(exist_ok=True)

    process_files(source_path, save_path, args.recursive)


if __name__ == "__main__":
    main()
