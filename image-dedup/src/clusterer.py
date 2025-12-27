import logging

import faiss
import networkx as nx
import numpy as np
from sqlalchemy import select, update

from src.config import settings
from src.db import ImageRecord, SessionLocal

logger = logging.getLogger(__name__)


def cluster_images() -> None:
    """
    Выполняет кластеризацию изображений на основе их эмбеддингов.

    Процесс включает следующие шаги:
    1. Загрузка эмбеддингов из базы данных.
    2. Построение индекса FAISS для быстрого поиска ближайших соседей.
    3. Поиск пар изображений, сходство которых превышает заданный порог.
    4. Построение графа, где рёбра соединяют похожие изображения.
    5. Поиск связных компонент в графе, которые и являются кластерами.
    6. Сохранение информации о кластерах (cluster_id) в базу данных.
    """
    logger.info("Загрузка эмбеддингов из БД...")
    with SessionLocal() as session:
        # Загружаем ID и векторы
        # Внимание: для 100k векторов (768 float) это ~300MB RAM. Допустимо.
        stmt = select(ImageRecord.id, ImageRecord.embedding).where(
            ImageRecord.embedding.is_not(None)
        )
        results = session.execute(stmt).all()

    if not results:
        logger.warning("Эмбеддинги для кластеризации не найдены.")
        return

    ids: np.ndarray = np.array([r.id for r in results], dtype=np.int64)
    embeddings: np.ndarray = np.array([r.embedding for r in results], dtype=np.float32)

    # Нормализация (на всякий случай, хотя CLIP уже нормализован)
    faiss.normalize_L2(embeddings)

    d: int = embeddings.shape[1]
    n: int = embeddings.shape[0]

    logger.info(f"Построение индекса FAISS для {n} векторов...")
    # Используем IndexFlatIP (Inner Product) = Cosine Similarity для нормализованных векторов
    index = faiss.IndexFlatIP(d)

    # Если есть GPU для FAISS:
    # res = faiss.StandardGpuResources()
    # index = faiss.index_cpu_to_gpu(res, 0, index)

    index.add(embeddings)  # type: ignore

    # Поиск соседей. Range Search эффективнее для кластеризации по порогу
    # radius = threshold. Но FAISS range_search использует L2 distance для L2 индекса
    # или Inner Product для IP индекса.
    # Для IP: чем больше, тем ближе. Мы ищем соседей с similarity > threshold.

    lims, _, indices = index.range_search(  # type: ignore
        embeddings, settings.SIMILARITY_THRESHOLD
    )

    logger.info("Построение графа связей...")
    G = nx.Graph()
    G.add_nodes_from(ids)

    # lims - это индексы начала/конца результатов для каждого вектора i
    for i in range(n):
        start, end = lims[i], lims[i + 1]
        # Соседи вектора i
        neighbors_indices = indices[start:end]
        # neighbors_scores = D[start:end]

        src_id = ids[i]
        for j_idx in neighbors_indices:
            if i == j_idx:
                continue  # self-loop
            dst_id = ids[j_idx]
            G.add_edge(src_id, dst_id)

    logger.info("Поиск связных компонент (кластеров)...")
    components = list(nx.connected_components(G))

    # Фильтруем одиночные (не кластеры)
    clusters = [c for c in components if len(c) > 1]
    logger.info(f"Найдено {len(clusters)} кластеров размером > 1.")

    logger.info("Сохранение информации о кластерах в БД...")
    with SessionLocal() as session:
        # Сначала сбрасываем старые кластеры
        session.execute(update(ImageRecord).values(cluster_id=None))

        for cluster_idx, node_set in enumerate(clusters):
            # cluster_idx + 1, чтобы ID начинались с 1
            node_list = list(node_set)
            session.execute(
                update(ImageRecord)
                .where(ImageRecord.id.in_(node_list))
                .values(cluster_id=cluster_idx + 1)
            )
        session.commit()

    logger.info("Кластеризация успешно завершена и сохранена в БД.")
