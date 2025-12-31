"""
Главный модуль Photo Gallery Editor.

Этот модуль использует Typer для создания интерфейса командной строки (CLI)
с вложенными командами для управления медиафайлами и поиском дубликатов.
"""
from pathlib import Path
from typing import Annotated, Optional

import typer

# --- Импорты из под-модулей ---
# Прямые импорты, так как структура проекта теперь плоская внутри src
from .clusterer import cluster_images
from .db import init_db
from .gui import run_gui
from .indexer import index_images
from .utils import setup_logging

# Импорты из нового модуля 'manage'
from .manage.sorter import process_files
from .manage.mp4_fixer import Mp4DateFixer, DEFAULT_TZ


# --- Главное приложение ---
app = typer.Typer(
    name="photogallery-editor",
    help="Утилита для управления фотогалереей: сортировка и поиск дубликатов.",
    no_args_is_help=True,
)

# --- Под-приложение для работы с дубликатами ---
duplicates_app = typer.Typer(
    name="duplicates",
    help="Команды для поиска и управления дубликатами изображений.",
    no_args_is_help=True,
)


@duplicates_app.command("init")
def duplicates_init() -> None:
    """Инициализирует таблицы в базе данных для поиска дубликатов."""
    init_db()
    typer.echo("База данных для дубликатов успешно инициализирована.")


@duplicates_app.command("index")
def duplicates_index(
    path: Annotated[Path, typer.Argument(help="Путь к папке с изображениями.")],
    limit: Annotated[
        int,
        typer.Option(
            "--limit", help="Макс. кол-во изображений для обработки (0 = все)"
        ),
    ] = 0,
    force: Annotated[
        bool, typer.Option("--force", help="Принудительно переиндексировать все файлы")
    ] = False,
) -> None:
    """Сканирует папку с изображениями и вычисляет для них эмбеддинги."""
    if not path.exists():
        typer.echo(f"Ошибка: Указанный путь не существует: {path}")
        raise typer.Exit(code=1)
    index_images(path, limit, force)


@duplicates_app.command("cluster")
def duplicates_cluster() -> None:
    """Группирует похожие изображения на основе их эмбеддингов."""
    cluster_images()


@duplicates_app.command("review")
def duplicates_review(
    readonly: Annotated[
        bool,
        typer.Option(
            "--read-only",
            help="Запустить в режиме 'только для чтения' или разрешить изменения.",
            is_flag=True,
            flag_value=True,
        ),
    ] = False,
) -> None:
    """Запускает GUI для ручного разбора кластеров дубликатов."""
    run_gui(readonly=readonly)


# --- Под-приложение для управления файлами ---
manage_app = typer.Typer(
    name="manage",
    help="Команды для сортировки и исправления метаданных медиафайлов.",
    no_args_is_help=True,
)


@manage_app.command("sort")
def manage_sort(
    load_path: Annotated[
        Path,
        typer.Option(
            "--load",
            help="Путь к папке с исходными файлами (по умолчанию: текущая директория).",
        ),
    ] = Path("."),
    save_path: Annotated[
        Optional[Path],
        typer.Option(
            "--save",
            help="Путь для сохранения отсортированных файлов (по умолчанию: папка --load).",
        ),
    ] = None,
    recursive: Annotated[
        bool, typer.Option("-R", "--recursive", help="Рекурсивный обход исходной папки.")
    ] = False,
) -> None:
    """Сортирует фото и видео по папкам на основе даты создания."""
    source_path = load_path.resolve()
    destination_path = save_path.resolve() if save_path else source_path

    if not source_path.is_dir():
        typer.echo(f"Ошибка: Исходная папка '{source_path}' не существует.")
        raise typer.Exit(1)

    destination_path.mkdir(exist_ok=True)
    process_files(source_path, destination_path, recursive)
    typer.echo("Сортировка завершена.")


@manage_app.command("fix-mp4-date")
def manage_fix_mp4_date(
    root: Annotated[Path, typer.Option(help="Корневая директория для сканирования.")],
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Не изменять файлы, только логировать.")
    ] = False,
    limit: Annotated[
        Optional[int], typer.Option("--limit", help="Макс. кол-во файлов для обработки.")
    ] = None,
    timezone: Annotated[
        str, typer.Option("--timezone", help=f"Временная зона (по умолчанию: {DEFAULT_TZ})")
    ] = DEFAULT_TZ,
) -> None:
    """Обновляет метаданные MP4 на основе даты из имени родительской папки."""
    try:
        fixer = Mp4DateFixer(
            root=root, dry_run=dry_run, limit=limit, timezone_str=timezone
        )
        fixer.run()
        typer.echo("Исправление дат MP4 завершено.")
    except Exception as e:
        typer.echo(f"Критическая ошибка: {e}", err=True)
        raise typer.Exit(1)


# --- Регистрация под-приложений и callback ---
app.add_typer(duplicates_app)
app.add_typer(manage_app)


@app.callback()
def callback() -> None:
    """
    Главная функция обратного вызова для настройки приложения.
    Инициализирует логирование перед выполнением любой команды.
    """
    setup_logging()


if __name__ == "__main__":
    app()
