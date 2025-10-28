import structlog
import numpy as np
from typing import List, Dict, Optional, Tuple
from sentence_transformers import SentenceTransformer
import faiss
from scipy.spatial.distance import cosine
from sklearn.cluster import DBSCAN

logger = structlog.get_logger()


class EmbeddingService:
    """Serviço para análise semântica usando embeddings"""

    def __init__(self, model_name: str = 'all-MiniLM-L6-v2', cache_client=None):
        self.model_name = model_name
        self.model = None
        self.cache_client = cache_client
        self.index = None
        self.indexed_texts = []
        self.dimension = 384  # Dimensão do modelo all-MiniLM-L6-v2

    async def initialize(self):
        """Inicializar modelo de embeddings"""
        try:
            logger.info('initializing_embedding_model', model=self.model_name)
            self.model = SentenceTransformer(self.model_name)
            logger.info('embedding_model_initialized', model=self.model_name)
        except Exception as e:
            logger.error('embedding_model_initialization_failed', error=str(e))
            raise

    async def generate_embedding(self, text: str, use_cache: bool = True) -> Optional[np.ndarray]:
        """Gerar embedding para texto"""
        try:
            if not self.model:
                logger.warning('embedding_model_not_initialized')
                return None

            # Verificar cache
            if use_cache and self.cache_client:
                cache_key = f'embedding:{hash(text)}'
                cached_embedding = await self.cache_client.get(cache_key)
                if cached_embedding:
                    logger.debug('embedding_cache_hit', text_length=len(text))
                    return np.frombuffer(cached_embedding, dtype=np.float32)

            # Gerar embedding
            embedding = self.model.encode(text, convert_to_numpy=True)

            # Salvar no cache
            if use_cache and self.cache_client:
                await self.cache_client.set(
                    cache_key,
                    embedding.tobytes(),
                    ttl=3600  # 1 hora
                )

            logger.debug('embedding_generated', text_length=len(text), dimension=len(embedding))
            return embedding

        except Exception as e:
            logger.error('generate_embedding_failed', error=str(e))
            return None

    async def batch_generate_embeddings(
        self,
        texts: List[str],
        use_cache: bool = True
    ) -> List[np.ndarray]:
        """Gerar embeddings em lote"""
        try:
            if not self.model:
                logger.warning('embedding_model_not_initialized')
                return []

            embeddings = []
            uncached_texts = []
            uncached_indices = []

            # Verificar cache primeiro
            if use_cache and self.cache_client:
                for i, text in enumerate(texts):
                    cache_key = f'embedding:{hash(text)}'
                    cached_embedding = await self.cache_client.get(cache_key)
                    if cached_embedding:
                        embeddings.append(np.frombuffer(cached_embedding, dtype=np.float32))
                    else:
                        embeddings.append(None)
                        uncached_texts.append(text)
                        uncached_indices.append(i)
            else:
                uncached_texts = texts
                uncached_indices = list(range(len(texts)))
                embeddings = [None] * len(texts)

            # Gerar embeddings para textos não cacheados
            if uncached_texts:
                new_embeddings = self.model.encode(uncached_texts, convert_to_numpy=True)

                # Atualizar lista e cache
                for i, embedding in zip(uncached_indices, new_embeddings):
                    embeddings[i] = embedding
                    if use_cache and self.cache_client:
                        cache_key = f'embedding:{hash(texts[i])}'
                        await self.cache_client.set(
                            cache_key,
                            embedding.tobytes(),
                            ttl=3600
                        )

            logger.info(
                'batch_embeddings_generated',
                total=len(texts),
                cached=len(texts) - len(uncached_texts),
                new=len(uncached_texts)
            )
            return embeddings

        except Exception as e:
            logger.error('batch_generate_embeddings_failed', error=str(e))
            return []

    async def build_index(self, texts: List[str]) -> bool:
        """Construir índice FAISS para busca rápida"""
        try:
            if not self.model:
                logger.warning('embedding_model_not_initialized')
                return False

            # Gerar embeddings
            embeddings = await self.batch_generate_embeddings(texts)
            if not embeddings:
                return False

            # Criar índice FAISS
            embeddings_array = np.array(embeddings).astype('float32')
            self.index = faiss.IndexFlatL2(self.dimension)
            self.index.add(embeddings_array)
            self.indexed_texts = texts

            logger.info('faiss_index_built', num_vectors=len(texts), dimension=self.dimension)
            return True

        except Exception as e:
            logger.error('build_index_failed', error=str(e))
            return False

    async def search_similar(
        self,
        query_text: str,
        top_k: int = 5,
        threshold: float = 0.7
    ) -> List[Dict]:
        """Buscar textos similares"""
        try:
            if not self.index or not self.indexed_texts:
                logger.warning('index_not_built')
                return []

            # Gerar embedding da query
            query_embedding = await self.generate_embedding(query_text)
            if query_embedding is None:
                return []

            # Buscar no índice
            query_array = np.array([query_embedding]).astype('float32')
            distances, indices = self.index.search(query_array, top_k)

            # Converter distância L2 para similaridade
            results = []
            for dist, idx in zip(distances[0], indices[0]):
                # Normalizar distância para similaridade (0-1)
                similarity = 1.0 / (1.0 + dist)

                if similarity >= threshold:
                    results.append({
                        'text': self.indexed_texts[idx],
                        'similarity': float(similarity),
                        'distance': float(dist)
                    })

            logger.info(
                'similarity_search_complete',
                query_length=len(query_text),
                results_found=len(results)
            )
            return results

        except Exception as e:
            logger.error('search_similar_failed', error=str(e))
            return []

    async def calculate_similarity(self, text1: str, text2: str) -> float:
        """Calcular similaridade entre dois textos"""
        try:
            emb1 = await self.generate_embedding(text1)
            emb2 = await self.generate_embedding(text2)

            if emb1 is None or emb2 is None:
                return 0.0

            # Similaridade cosseno (1 - distância cosseno)
            similarity = 1.0 - cosine(emb1, emb2)

            logger.debug('similarity_calculated', similarity=similarity)
            return float(similarity)

        except Exception as e:
            logger.error('calculate_similarity_failed', error=str(e))
            return 0.0

    async def cluster_texts(
        self,
        texts: List[str],
        eps: float = 0.5,
        min_samples: int = 2
    ) -> List[Dict]:
        """Agrupar textos similares usando DBSCAN"""
        try:
            if not texts:
                return []

            # Gerar embeddings
            embeddings = await self.batch_generate_embeddings(texts)
            if not embeddings:
                return []

            # Aplicar DBSCAN
            embeddings_array = np.array(embeddings)
            clustering = DBSCAN(eps=eps, min_samples=min_samples, metric='cosine')
            labels = clustering.fit_predict(embeddings_array)

            # Organizar resultados por cluster
            clusters = {}
            for i, label in enumerate(labels):
                label_key = int(label)
                if label_key not in clusters:
                    clusters[label_key] = []
                clusters[label_key].append({
                    'text': texts[i],
                    'index': i
                })

            # Formatar resultado
            result = [
                {
                    'cluster_id': cluster_id,
                    'size': len(items),
                    'is_noise': cluster_id == -1,
                    'items': items
                }
                for cluster_id, items in clusters.items()
            ]

            logger.info(
                'text_clustering_complete',
                num_texts=len(texts),
                num_clusters=len([c for c in clusters if c != -1]),
                noise_points=len(clusters.get(-1, []))
            )
            return result

        except Exception as e:
            logger.error('cluster_texts_failed', error=str(e))
            return []

    async def detect_semantic_drift(
        self,
        baseline_texts: List[str],
        current_texts: List[str],
        threshold: float = 0.3
    ) -> Dict:
        """Detectar drift semântico entre duas coleções de textos"""
        try:
            if not baseline_texts or not current_texts:
                return {'drift_detected': False, 'reason': 'insufficient_data'}

            # Gerar embeddings
            baseline_embeddings = await self.batch_generate_embeddings(baseline_texts)
            current_embeddings = await self.batch_generate_embeddings(current_texts)

            if not baseline_embeddings or not current_embeddings:
                return {'drift_detected': False, 'reason': 'embedding_generation_failed'}

            # Calcular centróides
            baseline_centroid = np.mean(baseline_embeddings, axis=0)
            current_centroid = np.mean(current_embeddings, axis=0)

            # Calcular distância entre centróides
            drift_distance = cosine(baseline_centroid, current_centroid)

            # Calcular variância intra-cluster
            baseline_variance = np.mean([
                cosine(emb, baseline_centroid) for emb in baseline_embeddings
            ])
            current_variance = np.mean([
                cosine(emb, current_centroid) for emb in current_embeddings
            ])

            # Detectar drift
            drift_detected = drift_distance > threshold

            result = {
                'drift_detected': drift_detected,
                'drift_distance': float(drift_distance),
                'baseline_variance': float(baseline_variance),
                'current_variance': float(current_variance),
                'threshold': threshold,
                'baseline_size': len(baseline_texts),
                'current_size': len(current_texts)
            }

            logger.info(
                'semantic_drift_detected' if drift_detected else 'no_semantic_drift',
                drift_distance=drift_distance,
                threshold=threshold
            )
            return result

        except Exception as e:
            logger.error('detect_semantic_drift_failed', error=str(e))
            return {'drift_detected': False, 'error': str(e)}

    async def find_outliers(
        self,
        texts: List[str],
        threshold_percentile: float = 95.0
    ) -> List[Dict]:
        """Encontrar textos outliers (semanticamente distantes)"""
        try:
            if len(texts) < 3:
                return []

            # Gerar embeddings
            embeddings = await self.batch_generate_embeddings(texts)
            if not embeddings:
                return []

            # Calcular centróide
            centroid = np.mean(embeddings, axis=0)

            # Calcular distâncias ao centróide
            distances = [cosine(emb, centroid) for emb in embeddings]

            # Encontrar threshold
            threshold = np.percentile(distances, threshold_percentile)

            # Identificar outliers
            outliers = []
            for i, dist in enumerate(distances):
                if dist > threshold:
                    outliers.append({
                        'text': texts[i],
                        'index': i,
                        'distance': float(dist),
                        'threshold': float(threshold)
                    })

            logger.info(
                'outliers_detected',
                num_texts=len(texts),
                num_outliers=len(outliers),
                threshold=threshold
            )
            return outliers

        except Exception as e:
            logger.error('find_outliers_failed', error=str(e))
            return []

    async def close(self):
        """Limpar recursos"""
        self.model = None
        self.index = None
        self.indexed_texts = []
        logger.info('embedding_service_closed')
