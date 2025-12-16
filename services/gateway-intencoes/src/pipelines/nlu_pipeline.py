"""Pipeline NLU usando spaCy para análise de texto e classificação de intenções"""
import spacy
import re
import hashlib
import json
import logging
import yaml
from contextlib import nullcontext
from pathlib import Path
from typing import List, Dict, Any, Optional
from models.intent_envelope import NLUResult, Entity, IntentDomain
from config.settings import get_settings
from cache.redis_client import get_redis_client

logger = logging.getLogger(__name__)
try:
    from neural_hive_observability import get_tracer
    tracer = get_tracer()
except ImportError:
    tracer = None

class NLUPipeline:
    def __init__(self, language_model: str = None, confidence_threshold: float = None):
        self.settings = get_settings()
        self.language_model = language_model or self.settings.nlu_language_model
        self.model_cache_dir = Path(self.settings.nlu_model_cache_dir)
        self.confidence_threshold = confidence_threshold or self.settings.nlu_confidence_threshold
        self.nlp = None
        self.nlp_models = {}  # Cache de modelos por idioma
        self._ready = False
        self.redis_client = None
        self.classification_rules = {}
        self.language_detection_enabled = True
        self.supported_models = {
            'pt': 'pt_core_news_sm',
            'en': 'en_core_web_sm',
            'es': 'es_core_news_sm'
        }
        self.last_adaptive_threshold = None  # Último threshold adaptativo calculado

    async def initialize(self):
        """Carregar modelos spaCy e configurações"""
        try:
            # Carregar modelo principal do volume persistente
            logger.info(f"Carregando modelo spaCy principal: {self.language_model}")
            self.nlp = self._load_model_from_cache(self.language_model)
            self.nlp_models['default'] = self.nlp

            # Tentar carregar modelos para idiomas suportados
            for lang_code, model_name in self.supported_models.items():
                try:
                    if model_name != self.language_model:  # Evitar recarregar modelo principal
                        logger.info(f"Carregando modelo {model_name} para idioma {lang_code}")
                        model = self._load_model_from_cache(model_name)
                        self.nlp_models[lang_code] = model
                except OSError:
                    logger.warning(f"Modelo {model_name} não encontrado para idioma {lang_code}")

            # Configurar cliente Redis para cache
            if self.settings.nlu_cache_enabled:
                self.redis_client = await get_redis_client()

            # Carregar regras de classificação
            await self.load_classification_rules()

            self._ready = True
            logger.info(f"NLU Pipeline inicializado com {len(self.nlp_models)} modelos")

        except Exception as e:
            logger.error(f"Erro inicializando pipeline NLU: {e}")
            raise

    async def load_classification_rules(self):
        """Carregar regras de classificação de arquivo de configuração"""
        try:
            # Carregar regras padrão primeiro
            self.classification_rules = self._get_default_classification_rules()

            # Tentar carregar de arquivo local e mesclar com padrões
            rules_path = Path(self.settings.nlu_rules_config_path)
            if rules_path.exists():
                with open(rules_path, 'r', encoding='utf-8') as f:
                    custom_rules = yaml.safe_load(f)
                    if custom_rules:
                        # Mesclar regras customizadas com padrões
                        self._merge_classification_rules(custom_rules)
                        logger.info(f"Regras de classificação customizadas carregadas de {rules_path}")
            else:
                logger.info(f"Arquivo de regras {rules_path} não encontrado, usando regras padrão")

        except Exception as e:
            logger.error(f"Erro carregando regras de classificação: {e}")
            self.classification_rules = self._get_default_classification_rules()

    def _merge_classification_rules(self, custom_rules: Dict[str, Any]):
        """Mesclar regras customizadas com regras padrão"""
        if "domains" in custom_rules:
            for domain_name, domain_config in custom_rules["domains"].items():
                if domain_name in self.classification_rules["domains"]:
                    # Mesclar keywords, patterns e subcategories
                    default_domain = self.classification_rules["domains"][domain_name]
                    if "keywords" in domain_config:
                        default_domain["keywords"].extend(domain_config["keywords"])
                    if "patterns" in domain_config:
                        default_domain["patterns"].extend(domain_config["patterns"])
                    if "subcategories" in domain_config:
                        default_domain["subcategories"].update(domain_config["subcategories"])
                else:
                    # Adicionar novo domínio
                    self.classification_rules["domains"][domain_name] = domain_config

        if "quality_thresholds" in custom_rules:
            self.classification_rules["quality_thresholds"].update(custom_rules["quality_thresholds"])

        if "confidence_boosters" in custom_rules:
            self.classification_rules["confidence_boosters"].update(custom_rules["confidence_boosters"])

    def _get_default_classification_rules(self) -> Dict[str, Any]:
        """Retornar regras de classificação padrão"""
        return {
            "domains": {
                "BUSINESS": {
                    "keywords": [
                        # Portuguese
                        "negócio", "venda", "vendas", "cliente", "clientes", "relatório", "dashboard",
                        "analytics", "métrica", "kpi", "receita", "faturamento", "lucro", "marketing",
                        "campanha", "conversão", "funil", "lead", "prospect",
                        # English
                        "business", "sales", "customer", "report", "revenue", "profit", "campaign",
                        "conversion", "funnel"
                    ],
                    "patterns": [
                        r"\b(relatório|dashboard|report)\b",
                        r"\b(vendas?|sales|selling)\b",
                        r"\b(clientes?|customers?|client)\b",
                        r"\b(receita|revenue|income)\b",
                        r"\b(marketing|campanha|campaign)\b"
                    ],
                    "subcategories": {
                        "reporting": ["relatório", "dashboard", "report", "analytics", "métrica", "kpi"],
                        "sales": ["venda", "vendas", "sales", "selling", "conversão", "conversion"],
                        "customer": ["cliente", "clientes", "customer", "client", "prospect", "lead"],
                        "marketing": ["marketing", "campanha", "campaign", "anúncio", "ad"]
                    }
                },
                "TECHNICAL": {
                    "keywords": [
                        # Portuguese
                        "api", "bug", "erro", "performance", "otimizar", "código", "função", "método",
                        "classe", "algoritmo", "database", "query", "sql", "implementar", "desenvolver",
                        "programar", "debug", "teste", "integração",
                        # English
                        "code", "function", "method", "class", "algorithm", "develop", "implement",
                        "programming", "debugging", "testing", "system", "technical", "development"
                    ],
                    "patterns": [
                        r"\b(api|rest|graphql|grpc)\b",
                        r"\b(bug|erro|error|issue|falha)\b",
                        r"\b(performance|otimizar|optimize|slow|lento)\b",
                        r"\b(código|code|function|método|class)\b",
                        r"\b(database|sql|query|banco)\b"
                    ],
                    "subcategories": {
                        "bug": ["bug", "erro", "error", "issue", "falha", "problem"],
                        "performance": ["performance", "otimizar", "optimize", "slow", "lento", "latency"],
                        "development": ["código", "code", "desenvolver", "develop", "implementar", "implement"],
                        "testing": ["teste", "test", "unit", "integration", "qa"]
                    }
                },
                "INFRASTRUCTURE": {
                    "keywords": [
                        # Portuguese
                        "deploy", "deployment", "servidor", "server", "kubernetes", "k8s", "docker",
                        "container", "pod", "cluster", "node", "infra", "infraestrutura", "devops",
                        "pipeline", "helm", "terraform", "ansible",
                        # English
                        "infrastructure", "orchestration", "provisioning", "scaling", "monitoring", "ci/cd"
                    ],
                    "patterns": [
                        r"\b(deploy|deployment|release)\b",
                        r"\b(servidor|server|host|vm)\b",
                        r"\b(kubernetes|k8s|docker|container)\b",
                        r"\b(infra|infrastructure|devops)\b",
                        r"\b(ci/cd|pipeline|automation)\b"
                    ],
                    "subcategories": {
                        "deployment": ["deploy", "deployment", "release", "rollout"],
                        "containers": ["docker", "kubernetes", "k8s", "container", "pod"],
                        "servers": ["servidor", "server", "host", "vm", "node"],
                        "automation": ["ci/cd", "pipeline", "terraform", "ansible", "automation"]
                    }
                },
                "SECURITY": {
                    "keywords": [
                        # Portuguese
                        "segurança", "security", "autenticação", "authentication", "autorização",
                        "authorization", "permissão", "permission", "acesso", "access", "token", "jwt",
                        "oauth", "saml", "ssl", "tls", "criptografia", "encryption", "vulnerabilidade",
                        "vulnerability", "firewall", "iam",
                        # English
                        "auth", "login", "credential", "certificate", "key"
                    ],
                    "patterns": [
                        r"\b(segurança|security|secure)\b",
                        r"\b(autenticação|authentication|auth|login)\b",
                        r"\b(autorização|authorization|permission|acesso)\b",
                        r"\b(criptografia|encryption|crypto|ssl|tls)\b",
                        r"\b(vulnerabilidade|vulnerability|exploit|cve)\b"
                    ],
                    "subcategories": {
                        "authentication": ["autenticação", "authentication", "login", "auth", "credential"],
                        "authorization": ["autorização", "authorization", "permission", "acesso", "access", "iam"],
                        "encryption": ["criptografia", "encryption", "ssl", "tls", "certificate", "key"],
                        "security": ["segurança", "security", "vulnerabilidade", "vulnerability", "firewall"]
                    }
                }
            },
            "quality_thresholds": {
                "min_text_length": 3,
                "max_text_length": 10000,
                "min_words": 2,
                "spam_patterns": [
                    r"^(.)\1{10,}$",  # Caracteres repetidos
                    r"^\d+$",  # Apenas números
                    r"^[!@#$%^&*()]+$"  # Apenas símbolos
                ]
            },
            "confidence_boosters": {
                "text_length_boost": {"threshold": 50, "boost": 0.05},
                "entity_presence_boost": {"threshold": 2, "boost": 0.05},
                "multiple_subcategories_boost": {"threshold": 2, "boost": 0.05},
                "context_role_match_boost": {"boost": 0.10}
            }
        }

    def _load_model_from_cache(self, model_name: str):
        """Carregar modelo spaCy do volume persistente"""
        # Tentar carregar do diretório de cache primeiro
        model_path = self.model_cache_dir / model_name

        if model_path.exists():
            logger.info(f"Carregando modelo do cache: {model_path}")
            # Adicionar o diretório de cache ao sys.path temporariamente
            import sys
            cache_str = str(self.model_cache_dir)
            if cache_str not in sys.path:
                sys.path.insert(0, cache_str)
            try:
                return spacy.load(str(model_path))
            except Exception as e:
                logger.warning(f"Falha ao carregar do cache {model_path}, tentando instalação padrão: {e}")

        # Fallback para instalação padrão do spaCy
        logger.info(f"Carregando modelo da instalação padrão: {model_name}")
        return spacy.load(model_name)

    def is_ready(self) -> bool:
        return self._ready and self.nlp is not None

    async def process(self, text: str, language: str = "pt-AO", context: Dict[str, Any] = None) -> NLUResult:
        """Processar texto para extrair intenção com cache e detecção de idioma"""
        if not self.is_ready():
            raise RuntimeError("Pipeline NLU não inicializado")

        span_context = tracer.start_as_current_span("nlu.process") if tracer else nullcontext()
        with span_context as span:
            if span:
                span.set_attribute("neural.hive.component", "gateway")
                span.set_attribute("neural.hive.layer", "experiencia")
                span.set_attribute("neural.hive.nlu.language", language)
                span.set_attribute("neural.hive.nlu.text_length", len(text))
                span.set_attribute("neural.hive.nlu.cache_enabled", self.settings.nlu_cache_enabled)

            # Validar qualidade do texto
            if not self._validate_text_quality(text):
                if span:
                    span.set_attribute("neural.hive.nlu.validation_failed", True)
                raise ValueError("Texto não atende critérios de qualidade")

            # Verificar cache se habilitado
            cache_key = None
            if self.settings.nlu_cache_enabled and self.redis_client:
                cache_key = self._get_cache_key(text, language, context)
                cached_result = await self._get_cached_result(cache_key)
                if cached_result:
                    if span:
                        span.set_attribute("neural.hive.nlu.cache_hit", True)
                        span.set_attribute("neural.hive.nlu.domain", cached_result.domain.value)
                        span.set_attribute("neural.hive.nlu.confidence", cached_result.confidence)
                    logger.debug(f"Resultado NLU obtido do cache: {cache_key}")
                    return cached_result
                if span:
                    span.set_attribute("neural.hive.nlu.cache_hit", False)

            # Detectar idioma automaticamente se não especificado claramente
            detected_language = await self._detect_language(text, language)
            if span:
                span.set_attribute("neural.hive.nlu.detected_language", detected_language)

            # Selecionar modelo apropriado para o idioma
            nlp_model = self._get_model_for_language(detected_language)

            # Normalizar texto
            normalized_text = self._normalize_text(text)

            # Processar texto com spaCy
            doc = nlp_model(normalized_text)

            # Mascarar PII
            processed_text = self._mask_pii(text)

            # Extrair entidades
            entities_context = tracer.start_as_current_span("nlu.extract_entities") if tracer else nullcontext()
            with entities_context as entities_span:
                entities = self._extract_entities(doc)
                if entities_span:
                    entities_span.set_attribute("neural.hive.nlu.entities_count", len(entities))
                    if entities:
                        entities_span.set_attribute(
                            "neural.hive.nlu.entity_types",
                            ", ".join(set(e.type for e in entities))
                        )

            # Classificar domínio e intenção usando regras configuráveis
            classify_context = tracer.start_as_current_span("nlu.classify_intent") if tracer else nullcontext()
            with classify_context as classify_span:
                domain, classification, confidence = await self._classify_intent_advanced(
                    text, entities, detected_language, context
                )
                if classify_span:
                    classify_span.set_attribute("neural.hive.nlu.domain", domain.value)
                    classify_span.set_attribute("neural.hive.nlu.classification", classification)
                    classify_span.set_attribute("neural.hive.nlu.confidence", confidence)

            # Extrair palavras-chave
            keywords_context = tracer.start_as_current_span("nlu.extract_keywords") if tracer else nullcontext()
            with keywords_context as keywords_span:
                keywords = self._extract_keywords(doc)
                if keywords_span:
                    keywords_span.set_attribute("neural.hive.nlu.keywords_count", len(keywords))

            # Calcular threshold adaptativo se habilitado
            adaptive_threshold = self.confidence_threshold
            if self.settings.nlu_adaptive_threshold_enabled:
                adaptive_threshold = self._calculate_adaptive_threshold(text, context, confidence, entities)
                if span:
                    span.set_attribute("neural.hive.nlu.adaptive_threshold", adaptive_threshold)

            # Store adaptive threshold for routing decisions
            self.last_adaptive_threshold = adaptive_threshold

            # Determinar confidence_status
            if confidence >= 0.75:
                confidence_status = "high"
            elif confidence >= 0.5:
                confidence_status = "medium"
            else:
                confidence_status = "low"

            if span:
                span.set_attribute("neural.hive.nlu.confidence_status", confidence_status)
                span.set_attribute("neural.hive.nlu.requires_validation", confidence < adaptive_threshold)

            # Criar resultado
            result = NLUResult(
                processed_text=processed_text,
                domain=domain,
                classification=classification,
                confidence=confidence,
                entities=entities,
                keywords=keywords,
                requires_manual_validation=confidence < adaptive_threshold,
                confidence_status=confidence_status,
                adaptive_threshold=adaptive_threshold
            )

            # Salvar no cache se habilitado
            if self.settings.nlu_cache_enabled and self.redis_client and cache_key:
                await self._cache_result(cache_key, result)

            if span:
                span.set_attribute("neural.hive.nlu.result.domain", domain.value)
                span.set_attribute("neural.hive.nlu.result.confidence", confidence)

            logger.info(
                f"NLU processado: domínio={domain.value}, classificação={classification}, "
                f"confidence={confidence:.2f}, status={confidence_status}, "
                f"threshold_base={self.confidence_threshold:.2f}, threshold_adaptive={adaptive_threshold:.2f}, "
                f"idioma={detected_language}"
            )

            return result

    def _validate_text_quality(self, text: str) -> bool:
        """Validar qualidade do texto de entrada"""
        if not text or not text.strip():
            return False

        thresholds = self.classification_rules.get("quality_thresholds", {})

        # Verificar comprimento
        if len(text) < thresholds.get("min_text_length", 3):
            return False

        if len(text) > thresholds.get("max_text_length", 10000):
            return False

        # Verificar número de palavras
        words = text.split()
        if len(words) < thresholds.get("min_words", 1):
            return False

        # Verificar padrões de spam
        spam_patterns = thresholds.get("spam_patterns", [])
        for pattern in spam_patterns:
            if re.search(pattern, text):
                logger.warning(f"Texto rejeitado por padrão de spam: {pattern}")
                return False

        return True

    def _get_cache_key(self, text: str, language: str, context: Dict[str, Any]) -> str:
        """Gerar chave de cache para o texto"""
        # Normalizar texto para cache
        normalized = self._normalize_text(text)

        # Incluir contexto relevante na chave
        context_key = ""
        if context:
            context_key = json.dumps(context, sort_keys=True)

        # Criar hash da combinação
        content = f"{normalized}|{language}|{context_key}"
        return f"nlu:cache:{hashlib.md5(content.encode()).hexdigest()}"

    async def _get_cached_result(self, cache_key: str) -> Optional[NLUResult]:
        """Obter resultado do cache"""
        try:
            cached_data = await self.redis_client.get(cache_key)
            if cached_data:
                # Deserializar resultado
                data = json.loads(cached_data)
                # Migração defensiva: adicionar confidence_status se não existir
                if "confidence_status" not in data:
                    confidence = data.get("confidence", 0.0)
                    if confidence >= 0.75:
                        data["confidence_status"] = "high"
                    elif confidence >= 0.5:
                        data["confidence_status"] = "medium"
                    else:
                        data["confidence_status"] = "low"
                return NLUResult(**data)
        except Exception as e:
            logger.error(f"Erro obtendo do cache NLU: {e}")
        return None

    async def _cache_result(self, cache_key: str, result: NLUResult):
        """Salvar resultado no cache"""
        try:
            # Serializar resultado
            data = {
                "processed_text": result.processed_text,
                "domain": result.domain.value,
                "classification": result.classification,
                "confidence": result.confidence,
                "entities": [{"type": e.type, "value": e.value, "confidence": e.confidence, "start": e.start, "end": e.end} for e in result.entities],
                "keywords": result.keywords,
                "requires_manual_validation": result.requires_manual_validation,
                "confidence_status": result.confidence_status,
                "adaptive_threshold": result.adaptive_threshold
            }

            await self.redis_client.set(
                cache_key,
                json.dumps(data),
                ttl=self.settings.nlu_cache_ttl_seconds
            )
        except Exception as e:
            logger.error(f"Erro salvando no cache NLU: {e}")

    async def _detect_language(self, text: str, provided_language: str) -> str:
        """Detectar idioma automaticamente se necessário"""
        # Se idioma foi claramente especificado (código de 2 letras), usar ele
        if provided_language and len(provided_language) == 2:
            return provided_language

        # Tentar detectar usando spaCy
        try:
            # Usar modelo padrão para detecção inicial
            doc = self.nlp(text[:200])  # Usar apenas primeiros 200 caracteres

            # Estratégia simples: verificar proporção de palavras reconhecidas
            if hasattr(doc, 'lang_'):
                detected = doc.lang_
                if detected in self.supported_models:
                    return detected
        except Exception as e:
            logger.warning(f"Erro na detecção de idioma: {e}")

        # Fallback para português
        return 'pt'

    def _get_model_for_language(self, language: str):
        """Obter modelo spaCy apropriado para o idioma"""
        if language in self.nlp_models:
            return self.nlp_models[language]

        # Fallback para modelo padrão
        return self.nlp

    def _normalize_text(self, text: str) -> str:
        """Normalizar texto para processamento"""
        # Remover espaços extras
        text = re.sub(r'\s+', ' ', text.strip())

        # Converter para lowercase para análise
        # (manter original para preservar informações de contexto)
        return text

    def _mask_pii(self, text: str) -> str:
        """Mascarar informações pessoais"""
        # Email
        text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL]', text)
        # CPF
        text = re.sub(r'\b\d{3}\.\d{3}\.\d{3}-\d{2}\b', '[CPF]', text)
        # Telefone
        text = re.sub(r'\b\d{2}\s?\d{4,5}-?\d{4}\b', '[PHONE]', text)
        return text

    def _extract_entities(self, doc) -> List[Entity]:
        """Extrair entidades nomeadas"""
        entities = []
        for ent in doc.ents:
            entities.append(Entity(
                type=ent.label_,
                value=ent.text,
                confidence=0.8,  # Valor padrão
                start=ent.start_char,
                end=ent.end_char
            ))
        return entities

    async def _classify_intent_advanced(self, text: str, entities: List[Entity], language: str, context: Dict[str, Any]) -> tuple:
        """Classificar domínio e tipo de intenção usando regras configuráveis"""
        text_lower = text.lower()
        domains_config = self.classification_rules.get("domains", {})
        confidence_boosters = self.classification_rules.get("confidence_boosters", {})

        domain_scores = {}
        subcategory_scores = {}

        # Calcular scores para cada domínio
        for domain_name, domain_config in domains_config.items():
            score = 0
            found_subcategories = []

            # Score baseado em keywords
            keywords = domain_config.get("keywords", [])
            keyword_matches = sum(1 for keyword in keywords if keyword in text_lower)
            score += keyword_matches * 2  # Peso maior para keywords

            # Score baseado em patterns regex
            patterns = domain_config.get("patterns", [])
            pattern_matches = sum(1 for pattern in patterns if re.search(pattern, text_lower))
            score += pattern_matches * 3  # Peso ainda maior para patterns

            # Verificar subcategorias
            subcategories = domain_config.get("subcategories", {})
            for subcat_name, subcat_keywords in subcategories.items():
                subcat_score = sum(1 for keyword in subcat_keywords if keyword in text_lower)
                if subcat_score > 0:
                    found_subcategories.append((subcat_name, subcat_score))
                    score += subcat_score

            domain_scores[domain_name] = score
            subcategory_scores[domain_name] = found_subcategories

        # Ajustar scores baseado em entidades
        for entity in entities:
            if entity.type in ['ORG', 'PRODUCT']:  # Entidades de negócio
                domain_scores['BUSINESS'] = domain_scores.get('BUSINESS', 0) + 1
            elif entity.type in ['MISC', 'EVENT']:  # Entidades técnicas
                domain_scores['TECHNICAL'] = domain_scores.get('TECHNICAL', 0) + 1

        # Selecionar melhor domínio
        if domain_scores and max(domain_scores.values()) > 0:
            best_domain_name = max(domain_scores, key=domain_scores.get)
            max_score = domain_scores[best_domain_name]

            # Calcular confidence base com fórmula mais generosa
            confidence = min(0.95, (max_score / 3.0) * 0.85)

            # Base boost: adicionar confiança mínima para textos válidos
            confidence = min(0.95, confidence + 0.15)

            # Aplicar boosts adaptativos
            # Boost por tamanho do texto
            text_length_config = confidence_boosters.get("text_length_boost", {})
            if len(text) > text_length_config.get("threshold", 50):
                confidence = min(0.95, confidence + text_length_config.get("boost", 0.05))

            # Boost por presença de entidades
            entity_config = confidence_boosters.get("entity_presence_boost", {})
            if len(entities) >= entity_config.get("threshold", 2):
                confidence = min(0.95, confidence + entity_config.get("boost", 0.05))

            # Boost por múltiplas subcategorias
            subcats = subcategory_scores.get(best_domain_name, [])
            multi_subcat_config = confidence_boosters.get("multiple_subcategories_boost", {})
            if len(subcats) >= multi_subcat_config.get("threshold", 2):
                confidence = min(0.95, confidence + multi_subcat_config.get("boost", 0.05))

            # Boost por match de contexto (user role vs domain)
            if context and context.get('user_role'):
                user_role = context.get('user_role', '').lower()
                role_match_config = confidence_boosters.get("context_role_match_boost", {})
                # Verificar se o role corresponde ao domínio
                if (best_domain_name == 'TECHNICAL' and 'developer' in user_role) or \
                   (best_domain_name == 'BUSINESS' and any(r in user_role for r in ['manager', 'analyst', 'business'])) or \
                   (best_domain_name == 'INFRASTRUCTURE' and any(r in user_role for r in ['devops', 'sre', 'admin'])) or \
                   (best_domain_name == 'SECURITY' and 'security' in user_role):
                    confidence = min(0.95, confidence + role_match_config.get("boost", 0.10))

            # Converter nome do domínio para enum
            try:
                best_domain = IntentDomain[best_domain_name]
            except KeyError:
                best_domain = IntentDomain.TECHNICAL  # Fallback

        else:
            best_domain = IntentDomain.TECHNICAL  # Default
            confidence = 0.2

        # Determinar classificação específica (subcategoria)
        classification = "general"
        if best_domain.name in subcategory_scores:
            subcats = subcategory_scores[best_domain.name]
            if subcats:
                # Pegar subcategoria com maior score
                best_subcat = max(subcats, key=lambda x: x[1])
                classification = best_subcat[0]

        return best_domain, classification, confidence

    def _calculate_adaptive_threshold(self, text: str, context: Dict[str, Any], confidence: float, entities: List[Entity]) -> float:
        """Calcular threshold adaptativo baseado em qualidade do texto e contexto"""
        # Começar com threshold base
        threshold = self.confidence_threshold

        # Fatores de ajuste (reduzem o threshold para permitir mais textos passarem)
        adjustments = []

        # Ajuste baseado em comprimento do texto (textos maiores = menor threshold)
        word_count = len(text.split())
        if word_count > 20:
            adjustments.append(-0.10)  # Reduzir threshold em 0.10
        elif word_count > 10:
            adjustments.append(-0.05)  # Reduzir threshold em 0.05

        # Ajuste baseado em presença de entidades (mais entidades = menor threshold)
        if len(entities) >= 3:
            adjustments.append(-0.10)
        elif len(entities) >= 1:
            adjustments.append(-0.05)

        # Ajuste baseado em contexto rico (presença de informações de contexto)
        if context:
            context_fields = sum(1 for v in context.values() if v is not None and v != "")
            if context_fields >= 3:
                adjustments.append(-0.05)

        # Aplicar ajustes
        for adjustment in adjustments:
            threshold = max(0.3, min(0.8, threshold + adjustment))

        return threshold

    def explain_classification(self, text: str, result: NLUResult) -> Dict[str, Any]:
        """Explicar por que um texto foi classificado em determinado domínio"""
        text_lower = text.lower()
        domain_name = result.domain.name
        domains_config = self.classification_rules.get("domains", {})

        explanation = {
            "domain": domain_name,
            "classification": result.classification,
            "confidence": result.confidence,
            "reasoning": {
                "matched_keywords": [],
                "matched_patterns": [],
                "entity_influences": [],
                "text_quality_factors": []
            }
        }

        if domain_name in domains_config:
            domain_config = domains_config[domain_name]

            # Identificar keywords que fizeram match
            keywords = domain_config.get("keywords", [])
            for keyword in keywords:
                if keyword in text_lower:
                    explanation["reasoning"]["matched_keywords"].append(keyword)

            # Identificar patterns que fizeram match
            patterns = domain_config.get("patterns", [])
            for pattern in patterns:
                if re.search(pattern, text_lower):
                    explanation["reasoning"]["matched_patterns"].append(pattern)

        # Analisar influência das entidades
        for entity in result.entities:
            explanation["reasoning"]["entity_influences"].append({
                "type": entity.type,
                "value": entity.value,
                "confidence": entity.confidence
            })

        # Fatores de qualidade do texto
        if len(text) < 20:
            explanation["reasoning"]["text_quality_factors"].append("Texto curto pode reduzir precisão")

        if result.confidence < 0.5:
            explanation["reasoning"]["text_quality_factors"].append("Baixa confidence - classificação incerta")

        return explanation

    def _extract_keywords(self, doc) -> List[str]:
        """Extrair palavras-chave relevantes"""
        keywords = []
        for token in doc:
            if (not token.is_stop and
                not token.is_punct and
                token.pos_ in ['NOUN', 'VERB', 'ADJ'] and
                len(token.text) > 2):
                keywords.append(token.lemma_.lower())
        return list(set(keywords))[:10]  # Máximo 10 keywords

    async def close(self):
        """Limpar recursos"""
        self.nlp = None
        self._ready = False
