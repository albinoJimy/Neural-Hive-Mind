"""Pipeline NLU centralizado - extraído e adaptado do gateway-intencoes.

Este serviço implementa o processamento de linguagem natural com:
- Classificação de domínio (BUSINESS/TECHNICAL/INFRASTRUCTURE/SECURITY)
- Extração de entidades nomeadas (NER)
- Cálculo de confiança adaptativo
- Cache Redis
- Detecção de idioma (pt/en/es)

INV-1: NLU Result Compatibility - domain, entities, confidence, keywords
"""

import asyncio
import hashlib
import json
import logging
import re
import unicodedata
from contextlib import nullcontext
from pathlib import Path
from typing import Any

import spacy
import yaml

from src.config.settings import get_settings
from src.models.nlu import (
    CalculateConfidenceResponse,
    Entity,
    EntityType,
    NLUResult,
    UnifiedDomain,
)

logger = logging.getLogger(__name__)

# Import tracer if available
try:
    from opentelemetry import trace

    tracer = trace.get_tracer(__name__)
except ImportError:
    tracer = None


class NLUPipelineService:
    """Serviço centralizado de NLU."""

    def __init__(self):
        self.settings = get_settings()
        self.nlp = None
        self.nlp_models = {}
        self._ready = False
        self.redis_client = None
        self.classification_rules = {}
        self.supported_models = {
            "pt": "pt_core_news_sm",
            "en": "en_core_web_sm",
            "es": "es_core_news_sm",
        }
        self.last_adaptive_threshold = None

        # Otimização: Estruturas pré-compiladas
        self.compiled_patterns = {}
        self.keyword_sets = {}
        self.subcategory_keyword_sets = {}

    async def initialize(self):
        """Inicializar o pipeline NLU."""
        try:
            logger.info("Inicializando NLU Pipeline Service...")

            # Carregar modelo principal
            logger.info(f"Carregando modelo spaCy: {self.settings.nlu_language_model}")
            self.nlp = self._load_model(self.settings.nlu_language_model)
            self.nlp_models["default"] = self.nlp

            # Carregar modelos para idiomas suportados
            for lang_code, model_name in self.supported_models.items():
                try:
                    if model_name != self.settings.nlu_language_model:
                        model = self._load_model(model_name)
                        self.nlp_models[lang_code] = model
                        logger.info(
                            f"Modelo {model_name} carregado para idioma {lang_code}"
                        )
                except OSError:
                    logger.warning(
                        f"Modelo {model_name} não encontrado para idioma {lang_code}"
                    )

            # Carregar regras de classificação
            await self._load_classification_rules()

            # Configurar Redis se habilitado
            if self.settings.nlu_cache_enabled:
                await self._setup_redis()

            # Cache warming se habilitado
            if self.settings.enable_cache_warming and self.settings.nlu_cache_enabled:
                await self._warmup_cache()

            self._ready = True
            logger.info(
                f"NLU Pipeline Service inicializado com {len(self.nlp_models)} modelos"
            )

        except Exception as e:
            logger.exception(f"Erro inicializando NLU Pipeline: {e}")
            raise

    def _load_model(self, model_name: str):
        """Carregar modelo spaCy do cache ou instalação padrão."""
        model_path = self.settings.nlu_model_cache_dir / model_name

        if model_path.exists():
            logger.info(f"Carregando modelo do cache: {model_path}")
            import sys

            cache_str = str(self.settings.nlu_model_cache_dir)
            if cache_str not in sys.path:
                sys.path.insert(0, cache_str)
            try:
                return spacy.load(str(model_path))
            except Exception as e:
                logger.warning(f"Falha ao carregar do cache: {e}")

        logger.info(f"Carregando modelo da instalação padrão: {model_name}")
        return spacy.load(model_name)

    async def _load_classification_rules(self):
        """Carregar regras de classificação de arquivo ou usar padrões."""
        try:
            self.classification_rules = self._get_default_rules()

            # Tentar carregar de arquivo local
            rules_path = Path(self.settings.nlu_rules_config_path)
            if rules_path.exists():
                with open(rules_path, encoding="utf-8") as f:
                    custom_rules = yaml.safe_load(f)
                    if custom_rules:
                        self._merge_rules(custom_rules)
                        logger.info(f"Regras customizadas carregadas de {rules_path}")

            # Preparar estruturas otimizadas
            self._prepare_optimized_structures()

        except Exception as e:
            logger.exception(f"Erro carregando regras: {e}")
            self.classification_rules = self._get_default_rules()
            self._prepare_optimized_structures()

    def _get_default_rules(self) -> dict[str, Any]:
        """Retornar regras de classificação padrão."""
        return {
            "domains": {
                "BUSINESS": {
                    "keywords": [
                        "negócio",
                        "venda",
                        "vendas",
                        "cliente",
                        "clientes",
                        "relatório",
                        "dashboard",
                        "analytics",
                        "métrica",
                        "kpi",
                        "receita",
                        "faturamento",
                        "lucro",
                        "marketing",
                        "campanha",
                        "conversão",
                        "funil",
                        "lead",
                        "prospect",
                        "business",
                        "sales",
                        "customer",
                        "report",
                        "revenue",
                        "profit",
                        "campaign",
                        "conversion",
                        "funnel",
                    ],
                    "patterns": [
                        r"\b(relatório|dashboard|report)\b",
                        r"\b(vendas?|sales|selling)\b",
                        r"\b(clientes?|customers?|client)\b",
                        r"\b(receita|revenue|income)\b",
                        r"\b(marketing|campanha|campaign)\b",
                    ],
                    "subcategories": {
                        "reporting": [
                            "relatório",
                            "dashboard",
                            "report",
                            "analytics",
                            "métrica",
                            "kpi",
                        ],
                        "sales": [
                            "venda",
                            "vendas",
                            "sales",
                            "selling",
                            "conversão",
                            "conversion",
                        ],
                        "customer": [
                            "cliente",
                            "clientes",
                            "customer",
                            "client",
                            "prospect",
                            "lead",
                        ],
                        "marketing": [
                            "marketing",
                            "campanha",
                            "campaign",
                            "anúncio",
                            "ad",
                        ],
                    },
                },
                "TECHNICAL": {
                    "keywords": [
                        "api",
                        "bug",
                        "erro",
                        "error",
                        "performance",
                        "otimizar",
                        "código",
                        "code",
                        "função",
                        "function",
                        "método",
                        "method",
                        "classe",
                        "class",
                        "algoritmo",
                        "algorithm",
                        "database",
                        "query",
                        "sql",
                        "implementar",
                        "implement",
                        "desenvolver",
                        "develop",
                        "programar",
                        "programming",
                        "debug",
                        "teste",
                        "test",
                        "integração",
                        "system",
                        "technical",
                        "development",
                    ],
                    "patterns": [
                        r"\b(api|rest|graphql|grpc)\b",
                        r"\b(bug|erro|error|issue|falha)\b",
                        r"\b(performance|otimizar|optimize|slow|lento)\b",
                        r"\b(código|code|function|método|class)\b",
                        r"\b(database|sql|query|banco)\b",
                    ],
                    "subcategories": {
                        "bug": ["bug", "erro", "error", "issue", "falha", "problem"],
                        "performance": [
                            "performance",
                            "otimizar",
                            "optimize",
                            "slow",
                            "lento",
                            "latency",
                        ],
                        "development": [
                            "código",
                            "code",
                            "desenvolver",
                            "develop",
                            "implementar",
                            "implement",
                        ],
                        "testing": ["teste", "test", "unit", "integration", "qa"],
                    },
                },
                "INFRASTRUCTURE": {
                    "keywords": [
                        "deploy",
                        "deployment",
                        "servidor",
                        "server",
                        "kubernetes",
                        "k8s",
                        "docker",
                        "container",
                        "pod",
                        "cluster",
                        "node",
                        "infra",
                        "infraestrutura",
                        "devops",
                        "pipeline",
                        "helm",
                        "terraform",
                        "ansible",
                        "infrastructure",
                        "orchestration",
                        "provisioning",
                        "scaling",
                        "monitoring",
                        "ci/cd",
                    ],
                    "patterns": [
                        r"\b(deploy|deployment|release)\b",
                        r"\b(servidor|server|host|vm)\b",
                        r"\b(kubernetes|k8s|docker|container)\b",
                        r"\b(infra|infrastructure|devops)\b",
                        r"\b(ci/cd|pipeline|automation)\b",
                    ],
                    "subcategories": {
                        "deployment": ["deploy", "deployment", "release", "rollout"],
                        "containers": [
                            "docker",
                            "kubernetes",
                            "k8s",
                            "container",
                            "pod",
                        ],
                        "servers": ["servidor", "server", "host", "vm", "node"],
                        "automation": [
                            "ci/cd",
                            "pipeline",
                            "terraform",
                            "ansible",
                            "automation",
                        ],
                    },
                },
                "SECURITY": {
                    "keywords": [
                        "segurança",
                        "security",
                        "autenticação",
                        "authentication",
                        "autorização",
                        "authorization",
                        "permissão",
                        "permission",
                        "acesso",
                        "access",
                        "token",
                        "jwt",
                        "oauth",
                        "saml",
                        "ssl",
                        "tls",
                        "criptografia",
                        "encryption",
                        "vulnerabilidade",
                        "vulnerability",
                        "firewall",
                        "iam",
                        "auth",
                        "login",
                        "credential",
                        "certificate",
                        "key",
                    ],
                    "patterns": [
                        r"\b(segurança|security|secure)\b",
                        r"\b(autenticação|authentication|auth|login)\b",
                        r"\b(autorização|authorization|permission|acesso)\b",
                        r"\b(criptografia|encryption|crypto|ssl|tls)\b",
                        r"\b(vulnerabilidade|vulnerability|exploit|cve)\b",
                    ],
                    "subcategories": {
                        "authentication": [
                            "autenticação",
                            "authentication",
                            "login",
                            "auth",
                            "credential",
                        ],
                        "authorization": [
                            "autorização",
                            "authorization",
                            "permission",
                            "acesso",
                            "access",
                            "iam",
                        ],
                        "encryption": [
                            "criptografia",
                            "encryption",
                            "ssl",
                            "tls",
                            "certificate",
                            "key",
                        ],
                        "security": [
                            "segurança",
                            "security",
                            "vulnerabilidade",
                            "vulnerability",
                            "firewall",
                        ],
                    },
                },
            },
            "quality_thresholds": {
                "min_text_length": 3,
                "max_text_length": 10000,
                "min_words": 2,
                "spam_patterns": [
                    r"^(.)\1{10,}$",
                    r"^\d+$",
                    r"^[!@#$%^&*()]+$",
                ],
            },
            "confidence_boosters": {
                "text_length_boost": {"threshold": 50, "boost": 0.05},
                "entity_presence_boost": {"threshold": 2, "boost": 0.05},
                "multiple_subcategories_boost": {"threshold": 2, "boost": 0.05},
                "context_role_match_boost": {"boost": 0.10},
            },
        }

    def _merge_rules(self, custom_rules: dict[str, Any]):
        """Mesclar regras customizadas com padrões."""
        if "domains" in custom_rules:
            for domain_name, domain_config in custom_rules["domains"].items():
                if domain_name in self.classification_rules["domains"]:
                    default_domain = self.classification_rules["domains"][domain_name]
                    if "keywords" in domain_config:
                        default_domain["keywords"].extend(domain_config["keywords"])
                    if "patterns" in domain_config:
                        default_domain["patterns"].extend(domain_config["patterns"])
                    if "subcategories" in domain_config:
                        default_domain["subcategories"].update(
                            domain_config["subcategories"]
                        )
                else:
                    self.classification_rules["domains"][domain_name] = domain_config

    @staticmethod
    def _strip_accents(text: str) -> str:
        """Normaliza texto removendo diacríticos (acentos).

        Garante que o matching de keywords é robusto a texto escrito sem acentos
        (ex.: 'seguranca' casa com 'segurança'). Sem isto, intents sem acentos
        caem no fallback TECHNICAL/0.2.
        """
        return "".join(
            c
            for c in unicodedata.normalize("NFKD", text.lower())
            if not unicodedata.combining(c)
        )

    def _prepare_optimized_structures(self):
        """Pré-compilar patterns e criar keyword sets."""
        domains_config = self.classification_rules.get("domains", {})

        for domain_name, domain_config in domains_config.items():
            # Compilar regex patterns
            patterns = domain_config.get("patterns", [])
            self.compiled_patterns[domain_name] = [re.compile(p) for p in patterns]

            # Converter keywords para set (normalizadas sem acentos para matching robusto)
            keywords = domain_config.get("keywords", [])
            self.keyword_sets[domain_name] = {self._strip_accents(k) for k in keywords}

            # Converter subcategories (também normalizadas)
            subcategories = domain_config.get("subcategories", {})
            self.subcategory_keyword_sets[domain_name] = {
                subcat_name: {self._strip_accents(k) for k in subcat_keywords}
                for subcat_name, subcat_keywords in subcategories.items()
            }

    async def _setup_redis(self):
        """Configurar cliente Redis."""
        try:
            import aioredis

            self.redis_client = await aioredis.from_url(
                self.settings.redis_url,
                max_connections=self.settings.redis_pool_size,
                socket_timeout=self.settings.redis_socket_timeout,
                decode_responses=True,
            )
            logger.info(f"Redis client configurado: {self.settings.redis_url}")
        except Exception as e:
            logger.warning(f"Erro configurando Redis: {e}. Cache desabilitado.")
            self.redis_client = None

    async def _warmup_cache(self):
        """Aquecer cache com queries frequentes."""
        if not self.redis_client:
            return

        warmup_queries = self.settings.warmup_queries
        logger.info(f"Iniciando cache warming com {len(warmup_queries)} queries")

        async def warmup_query(query: str):
            try:
                cache_key = self._get_cache_key(query, "pt", None)
                existing = await self.redis_client.get(cache_key)
                if existing:
                    return

                # Processar query para cache
                nlp_model = self.nlp_models.get("pt", self.nlp)
                doc = nlp_model(query)
                entities = self._extract_entities(doc)
                domain, classification, confidence = self._classify_domain(
                    query, entities, "pt", None
                )
                keywords = self._extract_keywords(doc)

                result = NLUResult(
                    processed_text=query,
                    domain=domain,
                    classification=classification,
                    confidence=confidence,
                    entities=entities,
                    keywords=keywords,
                    original_language="pt",
                )

                await self._cache_result(cache_key, result)
            except Exception as e:
                logger.warning(f"Erro no warmup para query '{query}': {e}")

        await asyncio.gather(
            *[warmup_query(q) for q in warmup_queries], return_exceptions=True
        )
        logger.info("Cache warming concluído")

    def is_ready(self) -> bool:
        """Verificar se pipeline está pronto."""
        return self._ready and self.nlp is not None

    async def parse(
        self, text: str, language: str = "pt", context: dict[str, Any] | None = None
    ) -> NLUResult:
        """Processar texto completo (Parse - opera��o principal)."""
        if not self.is_ready():
            raise RuntimeError("NLU Pipeline não inicializado")

        span_context = (
            tracer.start_as_current_span("nlu.parse") if tracer else nullcontext()
        )

        with span_context as span:
            if span:
                span.set_attribute("nlu.text_length", len(text))
                span.set_attribute("nlu.language", language)

            # Validar texto
            if not self._validate_text(text):
                raise ValueError("Texto não atende critérios de qualidade")

            # Verificar cache
            cache_key = None
            cached = None
            if self.settings.nlu_cache_enabled and self.redis_client:
                cache_key = self._get_cache_key(text, language, context)
                cached = await self._get_cached(cache_key)
                if cached:
                    if span:
                        span.set_attribute("nlu.cache_hit", True)
                    return cached

            if span:
                span.set_attribute("nlu.cache_hit", False)

            # Detectar idioma
            detected_lang = await self._detect_language(text, language)
            nlp_model = self._get_model_for_language(detected_lang)

            # Normalizar e processar
            normalized_text = self._normalize_text(text)
            doc = nlp_model(normalized_text)

            # Extrair entidades e classificar
            entities = self._extract_entities(doc)
            domain, classification, confidence = self._classify_domain(
                text, entities, detected_lang, context
            )
            keywords = self._extract_keywords(doc)

            # Calcular threshold adaptativo
            adaptive_threshold = self.settings.nlu_confidence_threshold
            if self.settings.nlu_adaptive_threshold_enabled:
                adaptive_threshold = self._calculate_adaptive_threshold(
                    text, context, confidence, entities
                )

            # Determinar confidence status
            if confidence >= 0.75:
                confidence_status = "high"
            elif confidence >= 0.5:
                confidence_status = "medium"
            else:
                confidence_status = "low"

            # Criar resultado (INV-1: domain, entities, confidence, keywords)
            result = NLUResult(
                processed_text=normalized_text,
                domain=domain,
                classification=classification,
                confidence=confidence,
                entities=entities,
                keywords=keywords,
                original_language=detected_lang,
                requires_manual_validation=confidence < adaptive_threshold,
                confidence_status=confidence_status,
                adaptive_threshold=adaptive_threshold,
            )

            # Salvar no cache
            if self.settings.nlu_cache_enabled and self.redis_client and cache_key:
                await self._cache_result(cache_key, result)

            return result

    async def classify_domain(
        self, text: str, language: str = "pt", context: dict[str, Any] | None = None
    ) -> tuple[UnifiedDomain, str, float]:
        """Classificar domínio do texto."""
        if not self.is_ready():
            raise RuntimeError("NLU Pipeline não inicializado")

        nlp_model = self._get_model_for_language(language)
        doc = nlp_model(text)
        entities = self._extract_entities(doc)
        return self._classify_domain(text, entities, language, context)

    async def extract_entities(self, text: str, language: str = "pt") -> list[Entity]:
        """Extrair entidades nomeadas do texto."""
        if not self.is_ready():
            raise RuntimeError("NLU Pipeline não inicializado")

        nlp_model = self._get_model_for_language(language)
        doc = nlp_model(text)
        return self._extract_entities(doc)

    async def calculate_confidence(
        self, nlu_result: NLUResult
    ) -> CalculateConfidenceResponse:
        """Calcular métricas de confiança detalhadas."""
        confidence = nlu_result.confidence
        adaptive_threshold = (
            nlu_result.adaptive_threshold or self.settings.nlu_confidence_threshold
        )

        # Confidence status
        if confidence >= 0.75:
            confidence_status = "high"
        elif confidence >= 0.5:
            confidence_status = "medium"
        else:
            confidence_status = "low"

        # Factor scores
        factor_scores = {
            "base_confidence": confidence,
            "text_length_factor": min(0.1, len(nlu_result.processed_text) / 1000),
            "entity_count_factor": min(0.1, len(nlu_result.entities) / 10),
            "keyword_count_factor": min(0.1, len(nlu_result.keywords) / 20),
        }

        return CalculateConfidenceResponse(
            confidence=confidence,
            confidence_status=confidence_status,
            adaptive_threshold=adaptive_threshold,
            requires_manual_validation=confidence < adaptive_threshold,
            factor_scores=factor_scores,
        )

    async def detect_language(
        self, text: str
    ) -> tuple[str, float, list[tuple[str, float]]]:
        """Detectar idioma do texto."""
        return await self._detect_language(text, None, return_candidates=True)

    def _validate_text(self, text: str) -> bool:
        """Validar qualidade do texto."""
        if not text or not text.strip():
            return False

        thresholds = self.classification_rules.get("quality_thresholds", {})

        if len(text) < thresholds.get("min_text_length", 3):
            return False

        if len(text) > thresholds.get("max_text_length", 10000):
            return False

        words = text.split()
        if len(words) < thresholds.get("min_words", 1):
            return False

        spam_patterns = thresholds.get("spam_patterns", [])
        for pattern in spam_patterns:
            if re.search(pattern, text):
                return False

        return True

    def _get_cache_key(
        self, text: str, language: str, context: dict[str, Any] | None
    ) -> str:
        """Gerar chave de cache."""
        normalized = self._normalize_text(text)
        context_key = json.dumps(context, sort_keys=True) if context else ""
        content = f"v2:{normalized}|{language}|{context_key}"
        return f"nlu:cache:{hashlib.md5(content.encode()).hexdigest()}"

    async def _get_cached(self, cache_key: str) -> NLUResult | None:
        """Obter resultado do cache."""
        if not self.redis_client:
            return None

        try:
            cached_data = await asyncio.wait_for(
                self.redis_client.get(cache_key), timeout=0.005
            )
            if cached_data:
                data = (
                    json.loads(cached_data)
                    if isinstance(cached_data, str)
                    else cached_data
                )
                return NLUResult(**data)
        except (TimeoutError, asyncio.TimeoutError):
            logger.debug(f"Cache lookup timeout: {cache_key[:20]}...")
        except Exception as e:
            logger.warning(f"Erro obtendo do cache: {e}")

        return None

    async def _cache_result(self, cache_key: str, result: NLUResult):
        """Salvar resultado no cache."""
        if not self.redis_client:
            return

        try:
            data = {
                "processed_text": result.processed_text,
                "domain": result.domain.value,
                "classification": result.classification,
                "confidence": result.confidence,
                "entities": [
                    {
                        "type": e.type.value,
                        "value": e.value,
                        "confidence": e.confidence,
                        "start": e.start,
                        "end": e.end,
                    }
                    for e in result.entities
                ],
                "keywords": result.keywords,
                "original_language": result.original_language,
                "requires_manual_validation": result.requires_manual_validation,
                "confidence_status": result.confidence_status,
                "adaptive_threshold": result.adaptive_threshold,
            }
            await self.redis_client.set(
                cache_key, json.dumps(data), ex=self.settings.nlu_cache_ttl_seconds
            )
        except Exception as e:
            logger.warning(f"Erro salvando no cache: {e}")

    async def _detect_language(
        self,
        text: str,
        provided_language: str | None = None,
        return_candidates: bool = False,
    ) -> tuple[str, float] | tuple[str, float, list[tuple[str, float]]]:
        """Detectar idioma do texto."""
        # Se idioma fornecido claramente
        if provided_language and len(provided_language) == 2:
            if return_candidates:
                return provided_language, 1.0, []
            return provided_language, 1.0

        # Detectar usando spaCy
        try:
            doc = self.nlp(text[:200])
            if hasattr(doc, "lang_"):
                detected = doc.lang_
                if detected in self.supported_models:
                    if return_candidates:
                        return (
                            detected,
                            0.8,
                            [(detected, 0.8), ("pt", 0.1), ("en", 0.1)],
                        )
                    return detected, 0.8
        except Exception as e:
            logger.warning(f"Erro na detecção de idioma: {e}")

        # Fallback para português
        if return_candidates:
            return "pt", 0.5, [("pt", 0.5), ("en", 0.25), ("es", 0.25)]
        return "pt", 0.5

    def _get_model_for_language(self, language: str):
        """Obter modelo spaCy para idioma."""
        if language in self.nlp_models:
            return self.nlp_models[language]
        return self.nlp

    def _normalize_text(self, text: str) -> str:
        """Normalizar texto."""
        return re.sub(r"\s+", " ", text.strip())

    def _extract_entities(self, doc) -> list[Entity]:
        """Extrair entidades nomeadas (INV-1: type, value, confidence, start, end)."""
        entities = []
        for ent in doc.ents:
            # Mapear spaCy labels para EntityType
            entity_type = self._map_entity_type(ent.label_)
            entities.append(
                Entity(
                    type=entity_type,
                    value=ent.text,
                    confidence=0.8,
                    start=ent.start_char,
                    end=ent.end_char,
                    label=ent.label_,
                )
            )
        return entities

    def _map_entity_type(self, spacy_label: str) -> EntityType:
        """Mapear label spaCy para EntityType."""
        mapping = {
            "PERSON": EntityType.PERSON,
            "ORG": EntityType.ORG,
            "GPE": EntityType.GPE,
            "LOC": EntityType.LOC,
            "DATE": EntityType.DATE,
            "TIME": EntityType.TIME,
            "MONEY": EntityType.MONEY,
            "PERCENT": EntityType.PERCENT,
            "CARDINAL": EntityType.CARDINAL,
            "ORDINAL": EntityType.ORDINAL,
            "QUANTITY": EntityType.QUANTITY,
            "PRODUCT": EntityType.PRODUCT,
            "EVENT": EntityType.EVENT,
            "WORK_OF_ART": EntityType.WORK_OF_ART,
            "LAW": EntityType.LAW,
            "LANGUAGE": EntityType.LANGUAGE,
        }
        return mapping.get(spacy_label, EntityType.UNKNOWN)

    def _classify_domain(
        self,
        text: str,
        entities: list[Entity],
        language: str,
        context: dict[str, Any] | None,
    ) -> tuple[UnifiedDomain, str, float]:
        """Classificar domínio usando regras configuráveis."""
        text_lower = text.lower()
        # text_words normalizado (sem acentos) para keyword/subcategory matching robusto;
        # text_lower (com acentos) é mantido para os patterns regex.
        text_words = set(self._strip_accents(text_lower).split())
        domains_config = self.classification_rules.get("domains", {})

        domain_scores = {}
        subcategory_scores = {}

        # Calcular scores
        for domain_name, _domain_config in domains_config.items():
            score = 0
            found_subcategories = []

            # Keyword matching
            keyword_set = self.keyword_sets.get(domain_name, set())
            keyword_matches = len(text_words & keyword_set)
            score += keyword_matches * 2

            # Pattern matching
            compiled = self.compiled_patterns.get(domain_name, [])
            pattern_matches = sum(
                1 for pattern in compiled if pattern.search(text_lower)
            )
            score += pattern_matches * 3

            # Subcategory matching
            subcategory_sets = self.subcategory_keyword_sets.get(domain_name, {})
            for subcat_name, subcat_keyword_set in subcategory_sets.items():
                subcat_matches = len(text_words & subcat_keyword_set)
                if subcat_matches > 0:
                    found_subcategories.append((subcat_name, subcat_matches))
                    score += subcat_matches

            domain_scores[domain_name] = score
            subcategory_scores[domain_name] = found_subcategories

        # Ajustar scores baseado em entidades
        for entity in entities:
            if entity.type in [EntityType.ORG, EntityType.PRODUCT]:
                domain_scores["BUSINESS"] = domain_scores.get("BUSINESS", 0) + 1
            elif entity.type in [EntityType.MONEY, EntityType.PERCENT]:
                domain_scores["BUSINESS"] = domain_scores.get("BUSINESS", 0) + 1

        # Selecionar melhor domínio
        if domain_scores and max(domain_scores.values()) > 0:
            best_domain_name = max(domain_scores, key=domain_scores.get)
            max_score = domain_scores[best_domain_name]

            # Calcular confidence
            confidence = min(0.95, (max_score / 3.0) * 0.85 + 0.15)

            # Aplicar boosts
            text_length_config = self.classification_rules.get(
                "confidence_boosters", {}
            ).get("text_length_boost", {})
            if len(text) > text_length_config.get("threshold", 50):
                confidence = min(
                    0.95, confidence + text_length_config.get("boost", 0.05)
                )

            entity_config = self.classification_rules.get(
                "confidence_boosters", {}
            ).get("entity_presence_boost", {})
            if len(entities) >= entity_config.get("threshold", 2):
                confidence = min(0.95, confidence + entity_config.get("boost", 0.05))

            # Converter para UnifiedDomain
            try:
                best_domain = UnifiedDomain[best_domain_name]
            except KeyError:
                best_domain = UnifiedDomain.TECHNICAL

        else:
            best_domain = UnifiedDomain.TECHNICAL
            confidence = 0.2

        # Determinar classificação (subcategoria)
        classification = "general"
        if best_domain.name in subcategory_scores:
            subcats = subcategory_scores[best_domain.name]
            if subcats:
                best_subcat = max(subcats, key=lambda x: x[1])
                classification = best_subcat[0]

        return best_domain, classification, confidence

    def _calculate_adaptive_threshold(
        self,
        text: str,
        context: dict[str, Any] | None,
        confidence: float,
        entities: list[Entity],
    ) -> float:
        """Calcular threshold adaptativo."""
        threshold = self.settings.nlu_confidence_threshold
        adjustments = []

        # Ajuste por tamanho do texto
        word_count = len(text.split())
        if word_count > 20:
            adjustments.append(-0.10)
        elif word_count > 10:
            adjustments.append(-0.05)

        # Ajuste por entidades
        if len(entities) >= 3:
            adjustments.append(-0.10)
        elif len(entities) >= 1:
            adjustments.append(-0.05)

        # Ajuste por contexto
        if context:
            context_fields = sum(
                1 for v in context.values() if v is not None and v != ""
            )
            if context_fields >= 3:
                adjustments.append(-0.05)

        # Aplicar ajustes
        for adjustment in adjustments:
            threshold = max(0.3, min(0.8, threshold + adjustment))

        return threshold

    def _extract_keywords(self, doc) -> list[str]:
        """Extrair palavras-chave (INV-1: keywords)."""
        keywords = []
        for token in doc:
            if (
                not token.is_stop
                and not token.is_punct
                and token.pos_ in ["NOUN", "VERB", "ADJ"]
                and len(token.text) > 2
            ):
                keywords.append(token.lemma_.lower())
        return list(set(keywords))[:5]

    async def close(self):
        """Limpar recursos."""
        self.nlp = None
        self._ready = False
        if self.redis_client:
            await self.redis_client.close()
            self.redis_client = None


# Global service instance
_nlu_service: NLUPipelineService | None = None


async def get_nlu_service() -> NLUPipelineService:
    """Retorna instância singleton do serviço NLU."""
    global _nlu_service
    if _nlu_service is None:
        _nlu_service = NLUPipelineService()
        await _nlu_service.initialize()
    return _nlu_service
