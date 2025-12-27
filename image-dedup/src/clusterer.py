import faiss
import numpy as np
import networkx as nx
from sqlalchemy import select, update
import logging

from src.db import SessionLocal, ImageRecord
from src.config import settings

logger = logging.getLogger(__name__)

def cluster_images():
    logger.info("Loading embeddings from DB...")
    with SessionLocal() as session:
        # Загружаем ID и векторы
        # Внимание: для 100k векторов (768 float) это ~300MB RAM. Допустимо.
        results = session.execute(select(ImageRecord.id, ImageRecord.embedding).where(ImageRecord.embedding.is_not(None))).all()
        
    if not results:
        logger.warning("No embeddings found.")
        return

    ids = np.array([r.id for r in results], dtype=np.int64)
    embeddings = np.array([r.embedding for r in results], dtype=np.float32)
    
    # Нормализация (на всякий случай, хотя CLIP уже нормализован)
    faiss.normalize_L2(embeddings)
    
    d = embeddings.shape[1]
    n = embeddings.shape[0]
    
    logger.info(f"Building FAISS index for {n} vectors...")
    # Используем IndexFlatIP (Inner Product) = Cosine Similarity для нормализованных векторов
    index = faiss.IndexFlatIP(d)
    
    # Если есть GPU для FAISS:
    # res = faiss.StandardGpuResources()
    # index = faiss.index_cpu_to_gpu(res, 0, index)
    
    index.add(embeddings)
    
    # Поиск соседей. Range Search эффективнее для кластеризации по порогу
    # radius = threshold. Но FAISS range_search использует L2 distance для L2 индекса
    # или Inner Product для IP индекса.
    # Для IP: чем больше, тем ближе. Мы ищем соседей с similarity > threshold.
    
    lims, D, I = index.range_search(embeddings, settings.SIMILARITY_THRESHOLD)
    
    logger.info("Building graph...")
    G = nx.Graph()
    G.add_nodes_from(ids)
    
    # lims - это индексы начала/конца результатов для каждого вектора i
    for i in range(n):
        start = lims[i]
        end = lims[i+1]
        # Соседи вектора i
        neighbors_indices = I[start:end]
        # neighbors_scores = D[start:end]
        
        src_id = ids[i]
        for j_idx in neighbors_indices:
            if i == j_idx: continue # self-loop
            dst_id = ids[j_idx]
            G.add_edge(src_id, dst_id)
            
    logger.info("Finding connected components...")
    components = list(nx.connected_components(G))
    
    # Фильтруем одиночные (не кластеры)
    clusters = [c for c in components if len(c) > 1]
    logger.info(f"Found {len(clusters)} clusters with >1 images.")
    
    # Сохраняем в БД
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
        
    logger.info("Clustering saved to DB.")