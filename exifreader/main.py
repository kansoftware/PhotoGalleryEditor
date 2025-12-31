import exifread
import datetime
import os
import subprocess
import json
import zlib
import argparse


def calculate_crc32(file_path):
    """Вычисляет CRC32 для файла."""
    hash_crc32 = 0
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_crc32 = zlib.crc32(chunk, hash_crc32)
    return hash_crc32


def safe_move_file(source_path, dest_dir):
    """
    Перемещает файл в целевую директорию с проверкой на существование
    и сравнением CRC32 в случае коллизии имен.
    """
    if not os.path.isdir(dest_dir):
        os.mkdir(dest_dir)

    lfn = os.path.basename(source_path)
    dest_path = os.path.join(dest_dir, lfn)

    if os.path.exists(dest_path):
        # Файл с таким именем уже существует, сравниваем CRC32
        source_crc = calculate_crc32(source_path)
        dest_crc = calculate_crc32(dest_path)

        if source_crc == dest_crc:
            # Файлы идентичны, пропускаем
            print(f"Skipping identical file: {lfn}")
            return
        else:
            # Файлы разные, ищем новое имя
            i = 1
            while True:
                name, ext = os.path.splitext(lfn)
                new_lfn = f"{name}_{i}{ext}"
                new_dest_path = os.path.join(dest_dir, new_lfn)
                if not os.path.exists(new_dest_path):
                    os.rename(source_path, new_dest_path)
                    print(
                        f"File '{lfn}' renamed to '{new_lfn}' and moved to '{dest_dir}'"
                    )
                    break
                i += 1
    else:
        # Файл не существует, просто перемещаем
        os.rename(source_path, dest_path)
        print(f"File '{lfn}' moved to '{dest_dir}'")


def getjpg(j):
    f = open(j, "rb")
    # Return Exif tags
    tags = exifread.process_file(f)
    if "EXIF DateTimeOriginal" in tags:
        d = tags["EXIF DateTimeOriginal"]
        return datetime.datetime.strptime(str(d), "%Y:%m:%d %H:%M:%S").date()
    else:
        # print(tags)
        return datetime.datetime.fromtimestamp(os.path.getmtime(j)).date()


def getmov(m):
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
            m,
        ]
        result = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, text=True
        )
        data = json.loads(result.stdout)

        creation_time_str = None
        if (
            "format" in data
            and "tags" in data["format"]
            and "creation_time" in data["format"]["tags"]
        ):
            creation_time_str = data["format"]["tags"]["creation_time"]

        # Иногда дата находится в потоке, а не в формате
        if not creation_time_str and "streams" in data:
            for stream in data["streams"]:
                if "tags" in stream and "creation_time" in stream["tags"]:
                    creation_time_str = stream["tags"]["creation_time"]
                    break

        if creation_time_str:
            # ffprobe возвращает время в UTC (с 'Z' на конце)
            if creation_time_str.endswith("Z"):
                creation_time_str = creation_time_str[:-1] + "+00:00"
            return datetime.datetime.fromisoformat(creation_time_str).date()

    except (
        subprocess.CalledProcessError,
        FileNotFoundError,
        json.JSONDecodeError,
        KeyError,
    ):
        # Если ffprobe не удался или не нашел дату, используем дату изменения
        pass

    return datetime.datetime.fromtimestamp(os.path.getmtime(m)).date()


# m = 'y:\\fotos\\2020\\2020-01-01\IMG_5814.MOV'
# j = 'y:\\fotos\\2020\\2020-01-01\IMG_5886.JPG'
# print(getjpg(j))
# print(getmov(m))

if __name__ == "__main__":
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
        type=str,
        default=".",
        help="Путь к папке с исходными файлами (по умолчанию: текущая директория).",
    )
    parser.add_argument(
        "--save",
        type=str,
        default="",
        help="Путь к папке для сохранения отсортированных файлов (по умолчанию: внутри --load).",
    )

    args = parser.parse_args()

    source_path = args.load
    save_path = args.save if args.save else source_path

    if not os.path.isdir(source_path):
        print(f"Ошибка: Исходная папка '{source_path}' не существует.")
        exit(1)

    # Список файлов для обработки
    files_to_process = []

    if args.recursive:
        for root, _, files in os.walk(source_path):
            for file in files:
                files_to_process.append(os.path.join(root, file))
    else:
        files_to_process = [
            os.path.join(source_path, f)
            for f in os.listdir(source_path)
            if os.path.isfile(os.path.join(source_path, f))
        ]

    for file_path in files_to_process:
        lfn = os.path.basename(file_path)
        try:
            file_extension = str(lfn).lower()
            if file_extension.endswith((".jpg", ".jpeg")):
                d = str(getjpg(file_path))
            elif file_extension.endswith((".mov", ".mp4")):
                d = str(getmov(file_path))
            else:
                continue  # Пропускаем файлы с неподдерживаемыми расширениями

            target_dir = os.path.join(save_path, d)
            print(f"Processing: {lfn} -> {target_dir}")
            safe_move_file(file_path, target_dir)
        except Exception as e:
            print(f"Error processing {file_path}: {e}")
