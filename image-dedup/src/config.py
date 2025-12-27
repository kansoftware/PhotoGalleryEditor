import os
from pydantic_settings import BaseSettings
from pathlib import Path

class Settings(BaseSettings):
    # DB
    DB_URL: str = "postgresql+psycopg://postgres:battery@localhost:5432/imagedb"
    
    # CLIP Model
    # Рекомендую ViT-B-16-SigLIP для баланса. 
    # Для макс. качества: model_name="ViT-L-14", pretrained="laion2b_s32b_b82k"
    CLIP_MODEL_NAME: str = "ViT-B-16-SigLIP" 
    CLIP_PRETRAINED: str = "webli"
    BATCH_SIZE: int = 32  # Подбирать под VRAM. 64 ок для 8GB VRAM
    DEVICE: str = "cuda" # или cpu
    
    # Clustering
    SIMILARITY_THRESHOLD: float = 0.95 # Косинусное сходство (0..1)
    
    # Paths
    LOG_FILE: Path = Path("app.log")
    
    class Config:
        env_file = ".env"

settings = Settings()