from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, Index
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session
from pgvector.sqlalchemy import Vector
from sqlalchemy import text
from datetime import datetime
from src.config import settings

class Base(DeclarativeBase):
    pass

class ImageRecord(Base):
    __tablename__ = "images"

    id = Column(Integer, primary_key=True)
    path = Column(String, unique=True, nullable=False)
    file_hash = Column(String, index=True)
    size_bytes = Column(Integer)
    mtime = Column(Float)
    
    # Размерность зависит от модели. ViT-B-16-SigLIP = 768
    embedding = Column(Vector(768)) 
    
    cluster_id = Column(Integer, index=True, nullable=True)
    reviewed = Column(Boolean, default=False)
    to_delete = Column(Boolean, default=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Индекс для быстрого поиска по вектору (IVFFlat или HNSW)
    # Для <100k строк можно обойтись без индекса или добавить позже.
    # __table_args__ = (Index('idx_images_embedding', 'embedding', postgresql_using='hnsw', postgresql_with={'m': 16, 'ef_construction': 64}),)

engine = create_engine(settings.DB_URL)
SessionLocal = sessionmaker(bind=engine)

def init_db():
    # Включаем расширение vector
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    Base.metadata.create_all(engine)