import typer
from typing import Annotated
from pathlib import Path
from src.utils import setup_logging
from src.db import init_db
from src.indexer import index_images
from src.clusterer import cluster_images
from src.gui import run_gui

app = typer.Typer()

@app.callback()
def callback():
    """
    Image Deduplication Tool.
    """
    setup_logging()

@app.command()
def init():
    """Initialize database tables."""
    init_db()
    print("Database initialized.")

@app.command()
def index(
    path: Annotated[Path, typer.Argument(help="Path to the image folder.")],
    limit: Annotated[int, typer.Option("--limit", help="Max images to process (0 = all)")] = 0,
    force: Annotated[bool, typer.Option("--force", help="Force re-indexing even if unchanged")] = False
):
    """Scan folder and compute embeddings."""
    if not path.exists():
        typer.echo("Path does not exist.")
        raise typer.Exit(code=1)
    index_images(path, limit, force)

@app.command()
def cluster():
    """Group images by similarity."""
    cluster_images()

@app.command()
def review(
    read_only: Annotated[bool, typer.Option("--read-only", help="Read-only mode")] = False
):
    """Start GUI for manual review."""
    run_gui(read_only)

if __name__ == "__main__":
    app()
