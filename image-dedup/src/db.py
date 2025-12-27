from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from src.config import settings


class Base(DeclarativeBase):
    pass


class ImageRecord(Base):
    __tablename__ = "images"

    id: Mapped[int] = mapped_column(primary_key=True)
    path: Mapped[str] = mapped_column(unique=True, nullable=False)
    file_hash: Mapped[str] = mapped_column(index=True)
    size_bytes: Mapped[int] = mapped_column()
    mtime: Mapped[float] = mapped_column()

    # Размерность зависит от модели. ViT-B-16-SigLIP = 768
    embedding: Mapped[Any] = mapped_column(Vector(768))

    cluster_id: Mapped[int | None] = mapped_column(index=True, nullable=True)
    reviewed: Mapped[bool] = mapped_column(default=False)
    to_delete: Mapped[bool] = mapped_column(default=False)

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)

    # Индекс для быстрого поиска по вектору (IVFFlat или HNSW)
    # Для <100k строк можно обойтись без индекса или добавить позже.
    # __table_args__ = (
    #     Index(
    #         "idx_images_embedding",
    #         "embedding",
    #         postgresql_using="hnsw",
    #         postgresql_with={"m": 16, "ef_construction": 64},
    #     ),
    # )


engine = create_engine(settings.DB_URL)
SessionLocal = sessionmaker(bind=engine)


def init_db() -> None:
    # Включаем расширение vector
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    Base.metadata.create_all(engine)
