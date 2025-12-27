import torch
import open_clip
from PIL import Image, UnidentifiedImageError
from pathlib import Path
from torch.utils.data import Dataset, DataLoader
from sqlalchemy import select
from typing import List, Tuple
import logging

from src.db import SessionLocal, ImageRecord
from src.config import settings
from src.utils import get_file_hash, is_image_file

logger = logging.getLogger(__name__)

class ImageDataset(Dataset):
    def __init__(self, file_paths: List[Path], preprocess):
        self.file_paths = file_paths
        self.preprocess = preprocess

    def __len__(self):
        return len(self.file_paths)

    def __getitem__(self, idx):
        path = self.file_paths[idx]
        try:
            image = Image.open(path).convert("RGB")
            image_tensor = self.preprocess(image)
            return image_tensor, str(path), True
        except (UnidentifiedImageError, OSError):
            # Возвращаем пустышку, обработаем флаг valid=False
            return torch.zeros((3, 224, 224)), str(path), False

def scan_directory(root: Path) -> List[Path]:
    return [p for p in root.rglob("*") if p.is_file() and is_image_file(p)]

def index_images(root_dir: Path, limit: int = 0, force: bool = False):
    logger.info(f"Scanning {root_dir}...")
    all_files = scan_directory(root_dir)
    if limit > 0:
        all_files = all_files[:limit]
    
    logger.info(f"Found {len(all_files)} candidates.")

    # 1. Фильтрация (Идемпотентность)
    files_to_process = []
    
    with SessionLocal() as session:
        # Загружаем кэш путей и mtime
        existing = session.execute(select(ImageRecord.path, ImageRecord.mtime, ImageRecord.size_bytes)).all()
        existing_map = {row.path: (row.mtime, row.size_bytes) for row in existing}

    for p in all_files:
        p_str = str(p.absolute())
        stat = p.stat()
        
        if not force and p_str in existing_map:
            old_mtime, old_size = existing_map[p_str]
            if abs(stat.st_mtime - old_mtime) < 0.001 and stat.st_size == old_size:
                continue # Файл не менялся
        
        files_to_process.append(p)

    logger.info(f"Files to process (new/changed): {len(files_to_process)}")
    if not files_to_process:
        return

    # 2. Подготовка модели
    device = settings.DEVICE if torch.cuda.is_available() else "cpu"
    logger.info(f"Loading model {settings.CLIP_MODEL_NAME} on {device}...")
    model, _, preprocess = open_clip.create_model_and_transforms(
        settings.CLIP_MODEL_NAME, pretrained=settings.CLIP_PRETRAINED, device=device
    )
    model.eval()

    dataset = ImageDataset(files_to_process, preprocess)
    dataloader = DataLoader(dataset, batch_size=settings.BATCH_SIZE, num_workers=4, pin_memory=True)

    # 3. Инференс и сохранение
    with SessionLocal() as session:
        with torch.no_grad(), torch.cuda.amp.autocast(enabled=(device=="cuda")):
            for batch_imgs, batch_paths, batch_valid in dataloader:
                batch_imgs = batch_imgs.to(device)
                
                # Считаем эмбеддинги только для валидных картинок
                # Но для простоты батчинга прогоним все, потом отфильтруем
                features = model.encode_image(batch_imgs)
                features /= features.norm(dim=-1, keepdim=True)
                
                features_cpu = features.cpu().numpy()
                
                for i, path_str in enumerate(batch_paths):
                    if not batch_valid[i]:
                        logger.warning(f"Skipping broken image: {path_str}")
                        continue
                        
                    p_obj = Path(path_str)
                    stat = p_obj.stat()
                    file_hash = get_file_hash(p_obj)
                    
                    # Upsert logic
                    record = session.query(ImageRecord).filter_by(path=path_str).first()
                    if not record:
                        record = ImageRecord(path=path_str)
                        session.add(record)
                    
                    record.mtime = stat.st_mtime
                    record.size_bytes = stat.st_size
                    record.file_hash = file_hash
                    record.embedding = features_cpu[i].tolist()
                    record.reviewed = False # Сброс статуса при обновлении
                
                session.commit()
                logger.info(f"Processed batch of {len(batch_paths)}")

    logger.info("Indexing complete.")