"""
Главный модуль приложения для дедупликации изображений.

Этот модуль использует Typer для создания интуитивно понятного интерфейса командной
строки (CLI) с несколькими командами для управления процессом поиска дубликатов.
"""
from pathlib import Path
from typing import Annotated

import typer

from src.clusterer import cluster_images
from src.db import init_db
from src.gui import run_gui
from src.indexer import index_images
from src.utils import setup_logging

app = typer.Typer()


@app.callback()
def callback() -> None:
    """
    Главная функция обратного вызова для настройки приложения.

    Инициализирует логирование перед выполнением любой команды.
    """
    setup_logging()


@app.command()
def init() -> None:
    """Инициализирует таблицы в базе данных."""
    init_db()
    typer.echo("База данных успешно инициализирована.")


@app.command()
def index(
    path: Annotated[Path, typer.Argument(help="Путь к папке с изображениями.")],
    limit: Annotated[
        int, typer.Option("--limit", help="Макс. кол-во изображений для обработки (0 = все)")
    ] = 0,
    force: Annotated[
        bool, typer.Option("--force", help="Принудительно переиндексировать все файлы")
    ] = False,
) -> None:
    """
    Сканирует папку с изображениями и вычисляет для них эмбеддинги.

    Args:
        path: Путь к директории с изображениями.
        limit: Ограничение на количество обрабатываемых изображений.
        force: Флаг для принудительной переиндексации.
    """
    if not path.exists():
        typer.echo(f"Ошибка: Указанный путь не существует: {path}")
        raise typer.Exit(code=1)
    index_images(path, limit, force)


@app.command()
def cluster() -> None:
    """Группирует похожие изображения на основе их эмбеддингов."""
    cluster_images()


@app.command()
def review(
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
    """
    Запускает графический интерфейс (GUI) для ручного разбора кластеров.

    Args:
        readonly: Если True, GUI не позволит вносить изменения.
    """
    run_gui(readonly=readonly)


if __name__ == "__main__":
    app()
