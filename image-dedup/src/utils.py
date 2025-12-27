import logging
import hashlib
from pathlib import Path
from src.config import settings

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(settings.LOG_FILE),
            logging.StreamHandler()
        ]
    )

def get_file_hash(path: Path, chunk_size: int = 8192) -> str:
    """Считает SHA256 файла."""
    sha = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            while chunk := f.read(chunk_size):
                sha.update(chunk)
        return sha.hexdigest()
    except OSError:
        return ""

def is_image_file(path: Path) -> bool:
    return path.suffix.lower() in {'.jpg', '.jpeg'}