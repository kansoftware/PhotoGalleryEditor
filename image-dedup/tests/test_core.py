from pathlib import Path

from src.utils import get_file_hash, is_image_file


def test_is_image_file():
    assert is_image_file(Path("test.jpg")) is True
    assert is_image_file(Path("TEST.JPEG")) is True
    assert is_image_file(Path("test.png")) is False # Мы договорились только jpg

def test_file_hash(tmp_path):
    p = tmp_path / "test.txt"
    p.write_bytes(b"hello world")
    # sha256 of "hello world"
    expected = "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"
    assert get_file_hash(p) == expected