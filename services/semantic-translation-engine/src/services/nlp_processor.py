"""
NLP Processor para extração avançada de keywords, objectives e entidades

Utiliza spaCy para processamento de linguagem natural com suporte bilíngue
(português/inglês) e cache Redis para otimização de performance.
"""

import hashlib
import time
import structlog
from typing import Dict, List, Optional, TYPE_CHECKING
from collections import Counter

if TYPE_CHECKING:
    from src.clients.redis_client import RedisClient

from src.observability.metrics import (
    nlp_extraction_duration,
    nlp_cache_hits_total,
    nlp_cache_misses_total,
    nlp_extraction_errors_total,
    nlp_keywords_extracted,
    nlp_objectives_extracted,
    nlp_entities_extracted
)

logger = structlog.get_logger()

# Mapeamento de verbos para objectives canônicos
VERB_MAPPINGS = {
    'create': [
        'criar', 'gerar', 'construir', 'desenvolver', 'implementar',
        'create', 'generate', 'build', 'develop', 'implement', 'make', 'add'
    ],
    'update': [
        'atualizar', 'modificar', 'alterar', 'editar', 'ajustar', 'corrigir',
        'update', 'modify', 'alter', 'edit', 'adjust', 'fix', 'change'
    ],
    'delete': [
        'deletar', 'remover', 'excluir', 'apagar', 'eliminar',
        'delete', 'remove', 'exclude', 'erase', 'eliminate', 'drop'
    ],
    'query': [
        'buscar', 'consultar', 'listar', 'obter', 'recuperar', 'pesquisar',
        'encontrar', 'verificar', 'checar', 'analisar', 'examinar',
        'query', 'search', 'list', 'get', 'retrieve', 'fetch', 'find',
        'check', 'analyze', 'examine', 'read', 'show', 'display'
    ],
    'transform': [
        'transformar', 'converter', 'migrar', 'adaptar', 'refatorar',
        'processar', 'formatar', 'normalizar',
        'transform', 'convert', 'migrate', 'adapt', 'refactor',
        'process', 'format', 'normalize', 'parse'
    ]
}

# POS tags relevantes para extração de keywords
KEYWORD_POS_TAGS = {'NOUN', 'VERB', 'ADJ', 'PROPN'}

# Padrões de tecnologia para reconhecimento
TECHNOLOGY_PATTERNS = {
    'REST', 'GraphQL', 'gRPC', 'SOAP', 'WebSocket',
    'MongoDB', 'PostgreSQL', 'MySQL', 'Redis', 'Neo4j', 'Kafka',
    'Docker', 'Kubernetes', 'AWS', 'GCP', 'Azure',
    'Python', 'Java', 'JavaScript', 'TypeScript', 'Go', 'Rust',
    'FastAPI', 'Django', 'Flask', 'Spring', 'Express', 'React', 'Vue'
}


class NLPProcessor:
    """Processador NLP para extração avançada usando spaCy"""

    def __init__(
        self,
        redis_client: Optional['RedisClient'] = None,
        cache_enabled: bool = True,
        cache_ttl_seconds: int = 600,
        model_pt: str = 'pt_core_news_sm',
        model_en: str = 'en_core_web_sm'
    ):
        """
        Inicializa o NLP Processor

        Args:
            redis_client: Cliente Redis para cache (opcional)
            cache_enabled: Habilita cache de resultados NLP
            cache_ttl_seconds: TTL do cache em segundos
            model_pt: Nome do modelo spaCy português
            model_en: Nome do modelo spaCy inglês
        """
        self.redis_client = redis_client
        self._cache_enabled = cache_enabled
        self._cache_ttl = cache_ttl_seconds
        self._model_pt_name = model_pt
        self._model_en_name = model_en
        self._nlp_pt = None
        self._nlp_en = None
        self._initialized = False

    async def initialize(self):
        """Inicializa modelos spaCy de forma lazy"""
        if self._initialized:
            return

        try:
            import spacy

            # Carregar modelos com componentes mínimos para performance
            self._nlp_pt = spacy.load(
                self._model_pt_name,
                disable=['ner']  # NER será usado apenas quando necessário
            )
            self._nlp_en = spacy.load(
                self._model_en_name,
                disable=['ner']
            )

            # Modelos completos para extração de entidades
            self._nlp_pt_full = spacy.load(self._model_pt_name)
            self._nlp_en_full = spacy.load(self._model_en_name)

            self._initialized = True
            logger.info(
                'NLP Processor inicializado',
                models=[self._model_pt_name, self._model_en_name],
                cache_enabled=self._cache_enabled,
                cache_ttl=self._cache_ttl
            )

        except Exception as e:
            logger.error('Falha ao inicializar NLP Processor', error=str(e))
            raise

    def is_ready(self) -> bool:
        """Verifica se o processador está pronto"""
        return self._initialized

    def _detect_language(self, text: str) -> str:
        """
        Detecta idioma do texto baseado em heurísticas simples

        Args:
            text: Texto para análise

        Returns:
            Código do idioma ('pt' ou 'en')
        """
        # Palavras indicativas de português
        pt_indicators = {
            'de', 'para', 'com', 'que', 'uma', 'um', 'do', 'da', 'dos', 'das',
            'em', 'no', 'na', 'nos', 'nas', 'pelo', 'pela', 'ao', 'aos',
            'criar', 'atualizar', 'deletar', 'buscar', 'sistema', 'usuário'
        }

        text_lower = text.lower()
        words = set(text_lower.split())

        pt_count = len(words & pt_indicators)

        # Se mais de 2 palavras portuguesas, considera português
        return 'pt' if pt_count >= 2 else 'en'

    def _get_model_for_language(self, language: str):
        """
        Retorna modelo spaCy para o idioma

        Args:
            language: Código do idioma

        Returns:
            Modelo spaCy
        """
        return self._nlp_pt if language == 'pt' else self._nlp_en

    def _get_full_model_for_language(self, language: str):
        """
        Retorna modelo spaCy completo (com NER) para o idioma

        Args:
            language: Código do idioma

        Returns:
            Modelo spaCy completo
        """
        return self._nlp_pt_full if language == 'pt' else self._nlp_en_full

    def _generate_cache_key(self, operation: str, text: str) -> str:
        """
        Gera chave de cache para operação NLP

        Args:
            operation: Tipo de operação (keywords, objectives, entities)
            text: Texto processado

        Returns:
            Chave de cache
        """
        text_hash = hashlib.md5(text.encode()).hexdigest()[:16]
        return f'nlp:{operation}:{text_hash}'

    async def _get_cached_extraction(self, cache_key: str) -> Optional[Dict]:
        """
        Obtém resultado de extração do cache

        Args:
            cache_key: Chave de cache

        Returns:
            Resultado cacheado ou None
        """
        if not self._cache_enabled or not self.redis_client:
            return None

        try:
            result = await self.redis_client.get_cached_query(cache_key)
            if result:
                nlp_cache_hits_total.inc()
            else:
                nlp_cache_misses_total.inc()
            return result
        except Exception as e:
            nlp_cache_misses_total.inc()
            logger.warning('Erro ao obter cache NLP', key=cache_key, error=str(e))
            return None

    async def _cache_extraction(
        self,
        cache_key: str,
        result: Dict,
        ttl: Optional[int] = None
    ):
        """
        Armazena resultado de extração no cache

        Args:
            cache_key: Chave de cache
            result: Resultado a cachear
            ttl: TTL em segundos
        """
        if not self._cache_enabled or not self.redis_client:
            return

        try:
            await self.redis_client.cache_query_result(
                cache_key,
                result,
                ttl or self._cache_ttl
            )
        except Exception as e:
            logger.warning('Erro ao cachear NLP', key=cache_key, error=str(e))

    async def extract_keywords_async(
        self,
        text: str,
        max_keywords: int = 10
    ) -> List[str]:
        """
        Extrai keywords do texto usando POS tagging e lematização (versão async com cache)

        Args:
            text: Texto para análise
            max_keywords: Número máximo de keywords

        Returns:
            Lista de keywords ordenadas por relevância
        """
        # Verificar cache
        cache_key = self._generate_cache_key('keywords', f'{text}:{max_keywords}')
        cached = await self._get_cached_extraction(cache_key)
        if cached is not None:
            logger.debug('Keywords obtidas do cache', cache_key=cache_key)
            return cached

        # Processar e cachear resultado
        keywords = self.extract_keywords(text, max_keywords)

        # Armazenar no cache
        await self._cache_extraction(cache_key, keywords)

        return keywords

    def extract_keywords(self, text: str, max_keywords: int = 10) -> List[str]:
        """
        Extrai keywords do texto usando POS tagging e lematização

        Args:
            text: Texto para análise
            max_keywords: Número máximo de keywords

        Returns:
            Lista de keywords ordenadas por relevância
        """
        start_time = time.perf_counter()

        if not self._initialized:
            logger.warning('NLP não inicializado, usando fallback')
            return self._extract_keywords_fallback(text, max_keywords)

        try:
            language = self._detect_language(text)
            nlp = self._get_model_for_language(language)
            doc = nlp(text)

            # Extrair tokens relevantes
            keywords_counter = Counter()

            for token in doc:
                # Filtrar por POS tag e não ser stop word
                if (
                    token.pos_ in KEYWORD_POS_TAGS
                    and not token.is_stop
                    and not token.is_punct
                    and len(token.lemma_) > 2
                ):
                    # Usar lema normalizado
                    lemma = token.lemma_.lower()
                    keywords_counter[lemma] += 1

            # Ordenar por frequência e retornar top N
            keywords = [
                word for word, _ in keywords_counter.most_common(max_keywords)
            ]

            # Métricas
            duration = time.perf_counter() - start_time
            nlp_extraction_duration.labels(operation='keywords').observe(duration)
            nlp_keywords_extracted.observe(len(keywords))

            logger.debug(
                'Keywords extraídas via NLP',
                count=len(keywords),
                language=language,
                duration_ms=round(duration * 1000, 2),
                text_preview=text[:50]
            )

            return keywords

        except Exception as e:
            nlp_extraction_errors_total.labels(
                operation='keywords',
                error_type=type(e).__name__
            ).inc()
            logger.warning('Erro na extração NLP de keywords', error=str(e))
            return self._extract_keywords_fallback(text, max_keywords)

    def _extract_keywords_fallback(self, text: str, max_keywords: int) -> List[str]:
        """
        Fallback para extração de keywords quando NLP não disponível

        Args:
            text: Texto para análise
            max_keywords: Número máximo de keywords

        Returns:
            Lista de keywords
        """
        stop_words = {
            'o', 'a', 'de', 'para', 'com', 'em', 'um', 'uma', 'do', 'da',
            'que', 'no', 'na', 'os', 'as', 'dos', 'das', 'nos', 'nas',
            'the', 'a', 'an', 'of', 'to', 'for', 'with', 'in', 'on', 'and',
            'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has'
        }

        words = text.lower().split()
        keywords = [
            w for w in words
            if w not in stop_words and len(w) > 2 and w.isalnum()
        ]

        return keywords[:max_keywords]

    async def extract_objectives_async(self, text: str) -> List[str]:
        """
        Extrai objectives do texto usando análise sintática de verbos (versão async com cache)

        Args:
            text: Texto para análise

        Returns:
            Lista de objectives canônicos
        """
        # Verificar cache
        cache_key = self._generate_cache_key('objectives', text)
        cached = await self._get_cached_extraction(cache_key)
        if cached is not None:
            logger.debug('Objectives obtidos do cache', cache_key=cache_key)
            return cached

        # Processar e cachear resultado
        objectives = self.extract_objectives(text)

        # Armazenar no cache
        await self._cache_extraction(cache_key, objectives)

        return objectives

    def extract_objectives(self, text: str) -> List[str]:
        """
        Extrai objectives do texto usando análise sintática de verbos

        Args:
            text: Texto para análise

        Returns:
            Lista de objectives canônicos
        """
        start_time = time.perf_counter()

        if not self._initialized:
            logger.warning('NLP não inicializado, usando fallback')
            return self._extract_objectives_fallback(text)

        try:
            language = self._detect_language(text)
            nlp = self._get_model_for_language(language)
            doc = nlp(text)

            objectives = set()

            for token in doc:
                # Identificar verbos principais (ROOT ou complementos verbais)
                if token.pos_ == 'VERB' and token.dep_ in {'ROOT', 'xcomp', 'ccomp', 'advcl'}:
                    verb_lemma = token.lemma_.lower()

                    # Mapear verbo para objective canônico
                    for objective, verbs in VERB_MAPPINGS.items():
                        if verb_lemma in verbs:
                            objectives.add(objective)
                            break

            # Se nenhum objective encontrado, verificar por matching direto
            if not objectives:
                text_lower = text.lower()
                for objective, verbs in VERB_MAPPINGS.items():
                    for verb in verbs:
                        if verb in text_lower:
                            objectives.add(objective)
                            break

            # Fallback para 'query' se nenhum encontrado
            if not objectives:
                objectives.add('query')

            result = list(objectives)

            # Métricas
            duration = time.perf_counter() - start_time
            nlp_extraction_duration.labels(operation='objectives').observe(duration)
            nlp_objectives_extracted.observe(len(result))

            logger.debug(
                'Objectives extraídos via NLP',
                objectives=result,
                language=language,
                duration_ms=round(duration * 1000, 2),
                text_preview=text[:50]
            )

            return result

        except Exception as e:
            nlp_extraction_errors_total.labels(
                operation='objectives',
                error_type=type(e).__name__
            ).inc()
            logger.warning('Erro na extração NLP de objectives', error=str(e))
            return self._extract_objectives_fallback(text)

    def _extract_objectives_fallback(self, text: str) -> List[str]:
        """
        Fallback para extração de objectives quando NLP não disponível

        Args:
            text: Texto para análise

        Returns:
            Lista de objectives
        """
        objectives = []
        text_lower = text.lower()

        if any(v in text_lower for v in VERB_MAPPINGS['create']):
            objectives.append('create')
        if any(v in text_lower for v in VERB_MAPPINGS['update']):
            objectives.append('update')
        if any(v in text_lower for v in VERB_MAPPINGS['delete']):
            objectives.append('delete')
        if any(v in text_lower for v in VERB_MAPPINGS['query']):
            objectives.append('query')
        if any(v in text_lower for v in VERB_MAPPINGS['transform']):
            objectives.append('transform')

        if not objectives:
            objectives.append('query')

        return objectives

    async def extract_entities_advanced_async(self, text: str) -> List[Dict]:
        """
        Extrai entidades avançadas usando NER e noun chunks (versão async com cache)

        Args:
            text: Texto para análise

        Returns:
            Lista de entidades com tipo, valor e confiança
        """
        # Verificar cache
        cache_key = self._generate_cache_key('entities', text)
        cached = await self._get_cached_extraction(cache_key)
        if cached is not None:
            logger.debug('Entidades obtidas do cache', cache_key=cache_key)
            return cached

        # Processar e cachear resultado
        entities = self.extract_entities_advanced(text)

        # Armazenar no cache
        await self._cache_extraction(cache_key, entities)

        return entities

    def extract_entities_advanced(self, text: str) -> List[Dict]:
        """
        Extrai entidades avançadas usando NER e noun chunks

        Args:
            text: Texto para análise

        Returns:
            Lista de entidades com tipo, valor e confiança
        """
        start_time = time.perf_counter()

        if not self._initialized:
            logger.warning('NLP não inicializado, retornando lista vazia')
            return []

        try:
            language = self._detect_language(text)
            nlp = self._get_full_model_for_language(language)
            doc = nlp(text)

            entities = []
            seen_values = set()

            # Extrair Named Entities do spaCy
            for ent in doc.ents:
                value = ent.text.strip()
                if value and value.lower() not in seen_values:
                    seen_values.add(value.lower())
                    entities.append({
                        'type': self._map_spacy_entity_type(ent.label_),
                        'value': value,
                        'confidence': 0.85,
                        'start': ent.start_char,
                        'end': ent.end_char
                    })

            # Extrair noun chunks como potenciais recursos
            for chunk in doc.noun_chunks:
                value = chunk.text.strip()
                # Filtrar chunks muito curtos ou já extraídos
                if (
                    len(value) > 2
                    and value.lower() not in seen_values
                    and not chunk.root.is_stop
                ):
                    seen_values.add(value.lower())
                    entities.append({
                        'type': 'RESOURCE',
                        'value': value,
                        'confidence': 0.70,
                        'start': chunk.start_char,
                        'end': chunk.end_char
                    })

            # Identificar tecnologias mencionadas
            text_upper = text.upper()
            for tech in TECHNOLOGY_PATTERNS:
                if tech.upper() in text_upper and tech.lower() not in seen_values:
                    seen_values.add(tech.lower())
                    # Encontrar posição no texto
                    idx = text.upper().find(tech.upper())
                    entities.append({
                        'type': 'TECHNOLOGY',
                        'value': tech,
                        'confidence': 0.95,
                        'start': idx,
                        'end': idx + len(tech)
                    })

            # Métricas
            duration = time.perf_counter() - start_time
            nlp_extraction_duration.labels(operation='entities').observe(duration)
            nlp_entities_extracted.observe(len(entities))

            logger.debug(
                'Entidades extraídas via NLP',
                count=len(entities),
                language=language,
                duration_ms=round(duration * 1000, 2),
                text_preview=text[:50]
            )

            return entities

        except Exception as e:
            nlp_extraction_errors_total.labels(
                operation='entities',
                error_type=type(e).__name__
            ).inc()
            logger.warning('Erro na extração NLP de entidades', error=str(e))
            return []

    def _map_spacy_entity_type(self, spacy_label: str) -> str:
        """
        Mapeia label de entidade spaCy para tipo customizado

        Args:
            spacy_label: Label do spaCy

        Returns:
            Tipo customizado
        """
        mapping = {
            'ORG': 'RESOURCE',
            'PRODUCT': 'RESOURCE',
            'WORK_OF_ART': 'RESOURCE',
            'PER': 'RESOURCE',
            'PERSON': 'RESOURCE',
            'LOC': 'RESOURCE',
            'GPE': 'RESOURCE',
            'MISC': 'RESOURCE',
            'EVENT': 'OPERATION',
            'DATE': 'ATTRIBUTE',
            'TIME': 'ATTRIBUTE',
            'MONEY': 'ATTRIBUTE',
            'QUANTITY': 'ATTRIBUTE',
            'PERCENT': 'ATTRIBUTE',
            'CARDINAL': 'ATTRIBUTE',
            'ORDINAL': 'ATTRIBUTE'
        }

        return mapping.get(spacy_label, 'RESOURCE')
