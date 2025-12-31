#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import re
import json
import shutil
import logging
import argparse
import subprocess
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional, Dict, Any

# --- Конфигурация ---
TARGET_TIME = "12:00:00"
DEFAULT_TZ = "Europe/Moscow"
BACKUP_SUFFIX = "_original"
# Теги для записи (Вариант А: Максимальная совместимость)
# QuickTime стандарт (UTC) + Apple Keys (с зоной)
TARGET_TAGS = [
    "QuickTime:CreateDate",
    "QuickTime:ModifyDate",
    "QuickTime:TrackCreateDate",
    "QuickTime:TrackModifyDate",
    "QuickTime:MediaCreateDate",
    "QuickTime:MediaModifyDate",
    "Keys:CreationDate",
]
# Тег, по которому определяем, нужно ли менять файл (Вариант Б: Мягкий режим)
PRIMARY_CHECK_TAG = "QuickTime:CreateDate"

# --- Логирование ---
logger = logging.getLogger("Mp4Fixer")


def setup_logging(log_path: str, verbose: bool):
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    file_handler.setFormatter(file_formatter)

    console_handler = logging.StreamHandler(sys.stdout)
    console_formatter = logging.Formatter("%(levelname)s: %(message)s")
    console_handler.setFormatter(console_formatter)

    logger.setLevel(logging.INFO if not verbose else logging.DEBUG)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)


class ExifToolError(Exception):
    pass


class Mp4DateFixer:
    def __init__(
        self, root: Path, dry_run: bool, limit: Optional[int], timezone_str: str
    ):
        self.root = root
        self.dry_run = dry_run
        self.limit = limit
        self.processed_count = 0
        self.tz = ZoneInfo(timezone_str)

        # Проверка наличия exiftool
        if not shutil.which("exiftool"):
            raise RuntimeError(
                "Exiftool not found. Please install: sudo apt install libimage-exiftool-perl"
            )

    def get_date_from_folder(self, file_path: Path) -> Optional[str]:
        """
        Извлекает дату YYYY-MM-DD из имени РОДИТЕЛЬСКОЙ папки.
        """
        parent_name = file_path.parent.name
        # Строгое начало строки, формат YYYY-MM-DD
        match = re.match(r"^(\d{4}-\d{2}-\d{2})", parent_name)
        if match:
            return match.group(1)
        return None

    def get_metadata(self, file_path: Path) -> Dict[str, Any]:
        """
        Читает метаданные через exiftool.
        Используем -api QuickTimeUTC, чтобы получить время с учетом UTC коррекции.
        """
        cmd = [
            "exiftool",
            "-j",  # JSON output
            "-G1",  # Group names (QuickTime:CreateDate)
            "-a",  # Allow duplicates
            "-api",
            "QuickTimeUTC",  # Interpret QuickTime integers as UTC
            str(file_path),
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            data = json.loads(result.stdout)
            return data[0] if data else {}
        except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
            logger.error(f"Failed to read metadata for {file_path}: {e}")
            return {}

    def construct_target_datetime(self, date_str: str) -> datetime:
        """
        Создает aware datetime объект: YYYY-MM-DD 12:00:00 MSK
        """
        dt_str = f"{date_str} {TARGET_TIME}"
        # Парсим как naive
        dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
        # Присваиваем таймзону
        return dt.replace(tzinfo=self.tz)

    def is_update_needed(
        self, current_meta: Dict[str, Any], target_dt: datetime
    ) -> bool:
        """
        Проверяет PRIMARY_CHECK_TAG.
        Сравниваем timestamp'ы, чтобы избежать проблем с форматом строк.
        """
        if PRIMARY_CHECK_TAG not in current_meta:
            return True  # Тега нет, надо писать

        current_val_str = current_meta[PRIMARY_CHECK_TAG]
        # Более надежная проверка дат
        # Exiftool возвращает дату в формате "YYYY:MM:DD HH:MM:SS" или "YYYY:MM:DD HH:MM:SS+ZZ:ZZ"
        # Мы отсекаем возможную таймзону для упрощенного парсинга
        try:
            current_dt_naive = datetime.strptime(
                current_val_str[:19], "%Y:%m:%d %H:%M:%S"
            )
            # Делаем aware-объект с той же зоной, что и у target_dt
            current_dt = current_dt_naive.replace(tzinfo=target_dt.tzinfo)
            # Сравниваем объекты datetime напрямую
            return current_dt != target_dt
        except (ValueError, TypeError):
            # Если не удалось распарсить, считаем, что нужно обновить
            logger.debug(f"Could not parse date '{current_val_str}'. Update needed.")
            return True

    def update_file(self, file_path: Path, target_dt: datetime):
        """
        Выполняет запись метаданных и обновление FS timestamps.
        """
        # Формируем строку даты для Exiftool: "YYYY:MM:DD HH:MM:SS+03:00"
        # Это важно для Keys:CreationDate и корректного пересчета в UTC для QuickTime тегов
        # Формируем строку с двоеточием в таймзоне, как требует стандарт ISO 8601
        # и как лучше всего понимает Exiftool.
        exif_date_str = target_dt.isoformat(sep=" ", timespec="seconds")

        logger.info(f"Processing: {file_path} -> Target: {exif_date_str}")

        if self.dry_run:
            logger.info("[DRY-RUN] Would execute exiftool update and touch file.")
            return

        # 1. Exiftool Update
        # Мы НЕ используем -overwrite_original, чтобы создался бэкап для верификации
        cmd = [
            "exiftool",
            "-api",
            "QuickTimeUTC",
            "-P",  # Preserve file modification time (мы его потом сами выставим, но пусть пока держит)
        ]

        for tag in TARGET_TAGS:
            cmd.append(f"-{tag}={exif_date_str}")

        cmd.append(str(file_path))

        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True)
        except subprocess.CalledProcessError as e:
            logger.error(f"Exiftool write failed for {file_path}: {e.stderr}")
            return

        # 2. Verification
        if self.verify_update(file_path, target_dt):
            # Success: Delete backup
            backup_file = file_path.with_suffix(file_path.suffix + BACKUP_SUFFIX)
            if backup_file.exists():
                try:
                    backup_file.unlink()
                    logger.debug(f"Verification passed. Backup deleted: {backup_file}")
                except OSError as e:
                    logger.warning(f"Could not delete backup {backup_file}: {e}")

            # 3. Update Filesystem Timestamps (mtime/atime)
            try:
                ts = target_dt.timestamp()
                os.utime(file_path, (ts, ts))
                logger.info(
                    f"Success: Metadata and FS times updated for {file_path.name}"
                )
            except OSError as e:
                logger.error(f"Failed to update filesystem times for {file_path}: {e}")

        else:
            # Failure: Restore backup
            logger.error(f"Verification FAILED for {file_path}. Restoring backup.")
            self.restore_backup(file_path)

    def verify_update(self, file_path: Path, target_dt: datetime) -> bool:
        """
        Читает файл заново и проверяет PRIMARY_CHECK_TAG.
        """
        meta = self.get_metadata(file_path)
        if not meta:
            return False
        return not self.is_update_needed(meta, target_dt)

    def restore_backup(self, file_path: Path):
        backup_file = file_path.with_suffix(file_path.suffix + BACKUP_SUFFIX)
        if backup_file.exists():
            try:
                # На Linux rename атомарен и заменит испорченный файл
                backup_file.replace(file_path)
                logger.info("Backup restored successfully.")
            except OSError as e:
                logger.critical(
                    f"CRITICAL: Failed to restore backup for {file_path}: {e}"
                )
        else:
            logger.critical(f"CRITICAL: Backup file not found for {file_path}!")

    def run(self):
        logger.info(f"Starting scan in: {self.root}")
        mp4_files = sorted(
            [
                f
                for f in self.root.rglob("*")
                if f.is_file() and f.suffix.lower() == ".mp4"
            ]
        )  # Сортировка для порядка в логах, поиск без учета регистра

        logger.info(f"Found {len(mp4_files)} MP4 files.")

        for file_path in mp4_files:
            if self.limit and self.processed_count >= self.limit:
                logger.info(f"Limit of {self.limit} files reached.")
                break

            # 1. Check folder date
            date_str = self.get_date_from_folder(file_path)
            if not date_str:
                logger.debug(f"Skipping {file_path.name}: No date in parent folder.")
                continue

            # 2. Construct Target
            try:
                target_dt = self.construct_target_datetime(date_str)
            except ValueError as e:
                logger.error(f"Invalid date format in folder {file_path.parent}: {e}")
                continue

            # 3. Check current state
            current_meta = self.get_metadata(file_path)
            if not self.is_update_needed(current_meta, target_dt):
                logger.debug(f"Skipping {file_path.name}: Metadata already correct.")
                continue

            # 4. Update
            self.update_file(file_path, target_dt)
            self.processed_count += 1


def main():
    parser = argparse.ArgumentParser(
        description="Batch update MP4 metadata based on parent folder date."
    )
    parser.add_argument(
        "--root", required=True, type=Path, help="Root directory to scan"
    )
    parser.add_argument("--dry-run", action="store_true", help="Do not modify files")
    parser.add_argument("--limit", type=int, help="Max number of files to process")
    parser.add_argument(
        "--log", default="./mp4_date_fixer.log", help="Path to log file"
    )
    parser.add_argument(
        "--timezone", default=DEFAULT_TZ, help=f"Timezone (default: {DEFAULT_TZ})"
    )
    parser.add_argument("--verbose", action="store_true", help="Verbose console output")

    args = parser.parse_args()

    if not args.root.exists():
        print(f"Error: Root path {args.root} does not exist.")
        sys.exit(1)

    setup_logging(args.log, args.verbose)

    fixer = Mp4DateFixer(
        root=args.root,
        dry_run=args.dry_run,
        limit=args.limit,
        timezone_str=args.timezone,
    )

    try:
        fixer.run()
    except KeyboardInterrupt:
        logger.warning("Process interrupted by user.")
        sys.exit(130)
    except Exception:
        logger.exception("Unexpected error occurred.")
        sys.exit(1)


if __name__ == "__main__":
    main()
