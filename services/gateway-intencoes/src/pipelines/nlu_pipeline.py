"""Pipeline NLU usando spaCy para análise de texto e classificação de intenções"""
import spacy
import re
import hashlib
import json
import logging
import yaml
from pathlib import Path
from typing import List, Dict, Any, Optional
from models.intent_envelope import NLUResult, Entity, IntentDomain
from config.settings import get_settings
from cache.redis_client import get_redis_client

logger = logging.getLogger(__name__)

class NLUPipeline:
    def __init__(self, language_model: str = None, confidence_threshold: float = None):
        self.settings = get_settings()
        self.language_model = language_model or self.settings.nlu_language_model
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

    async def initialize(self):
        """Carregar modelos spaCy e configurações"""
        try:
            # Carregar modelo principal
            logger.info(f"Carregando modelo spaCy principal: {self.language_model}")
            self.nlp = spacy.load(self.language_model)
            self.nlp_models['default'] = self.nlp

            # Tentar carregar modelos para idiomas suportados
            for lang_code, model_name in self.supported_models.items():
                try:
                    if model_name != self.language_model:  # Evitar recarregar modelo principal
                        logger.info(f"Carregando modelo {model_name} para idioma {lang_code}")
                        model = spacy.load(model_name)
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
            # Tentar carregar de arquivo local primeiro
            rules_path = Path("/app/config/nlu_rules.yaml")
            if rules_path.exists():
                with open(rules_path, 'r', encoding='utf-8') as f:
                    self.classification_rules = yaml.safe_load(f)
                logger.info(f"Regras de classificação carregadas de {rules_path}")
            else:
                # Usar regras padrão se arquivo não existir
                self.classification_rules = self._get_default_classification_rules()
                logger.info("Usando regras de classificação padrão")

        except Exception as e:
            logger.error(f"Erro carregando regras de classificação: {e}")
            self.classification_rules = self._get_default_classification_rules()

    def _get_default_classification_rules(self) -> Dict[str, Any]:
        """Retornar regras de classificação padrão"""
        return {
            "domains": {
                "BUSINESS": {
                    "keywords": ["negócio", "venda", "cliente", "relatório", "dashboard", "business", "sales", "report"],
                    "patterns": [
                        r"\b(relatório|dashboard)\b",
                        r"\b(vendas?|clientes?)\b",
                        r"\b(business|sales|customer)\b"
                    ],
                    "subcategories": {
                        "reporting": ["relatório", "dashboard", "report", "analytics"],
                        "sales": ["venda", "vendas", "sales", "selling"],
                        "customer": ["cliente", "clientes", "customer", "client"]
                    }
                },
                "TECHNICAL": {
                    "keywords": ["api", "bug", "performance", "otimizar", "código", "system", "technical", "development"],
                    "patterns": [
                        r"\b(api|bug|performance)\b",
                        r"\b(código|code|system)\b",
                        r"\b(technical|development)\b"
                    ],
                    "subcategories": {
                        "bug": ["bug", "erro", "error", "issue"],
                        "performance": ["performance", "otimizar", "optimize", "slow"],
                        "development": ["código", "code", "development", "programming"]
                    }
                },
                "INFRASTRUCTURE": {
                    "keywords": ["deploy", "servidor", "kubernetes", "docker", "infrastructure", "deployment"],
                    "patterns": [
                        r"\b(deploy|deployment|servidor|server)\b",
                        r"\b(kubernetes|docker|k8s)\b",
                        r"\b(infrastructure|infra)\b"
                    ],
                    "subcategories": {
                        "deployment": ["deploy", "deployment", "release"],
                        "containers": ["docker", "kubernetes", "k8s", "container"],
                        "servers": ["servidor", "server", "host"]
                    }
                },
                "SECURITY": {
                    "keywords": ["segurança", "autenticação", "permissão", "acesso", "security", "auth"],
                    "patterns": [
                        r"\b(segurança|security|auth)\b",
                        r"\b(autenticação|authentication|login)\b",
                        r"\b(permissão|permission|access)\b"
                    ],
                    "subcategories": {
                        "authentication": ["autenticação", "authentication", "login", "auth"],
                        "authorization": ["permissão", "permission", "authorization", "access"],
                        "security": ["segurança", "security", "vulnerability"]
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
            }
        }

    def is_ready(self) -> bool:
        return self._ready and self.nlp is not None

    async def process(self, text: str, language: str = "pt-AO", context: Dict[str, Any] = None) -> NLUResult:
        """Processar texto para extrair intenção com cache e detecção de idioma"""
        if not self.is_ready():
            raise RuntimeError("Pipeline NLU não inicializado")

        # Validar qualidade do texto
        if not self._validate_text_quality(text):
            raise ValueError("Texto não atende critérios de qualidade")

        # Verificar cache se habilitado
        cache_key = None
        if self.settings.nlu_cache_enabled and self.redis_client:
            cache_key = self._get_cache_key(text, language, context)
            cached_result = await self._get_cached_result(cache_key)
            if cached_result:
                logger.debug(f"Resultado NLU obtido do cache: {cache_key}")
                return cached_result

        # Detectar idioma automaticamente se não especificado claramente
        detected_language = await self._detect_language(text, language)

        # Selecionar modelo apropriado para o idioma
        nlp_model = self._get_model_for_language(detected_language)

        # Normalizar texto
        normalized_text = self._normalize_text(text)

        # Processar texto com spaCy
        doc = nlp_model(normalized_text)

        # Mascarar PII
        processed_text = self._mask_pii(text)

        # Extrair entidades
        entities = self._extract_entities(doc)

        # Classificar domínio e intenção usando regras configuráveis
        domain, classification, confidence = await self._classify_intent_advanced(
            text, entities, detected_language, context
        )

        # Extrair palavras-chave
        keywords = self._extract_keywords(doc)

        # Criar resultado
        result = NLUResult(
            processed_text=processed_text,
            domain=domain,
            classification=classification,
            confidence=confidence,
            entities=entities,
            keywords=keywords,
            requires_manual_validation=confidence < self.confidence_threshold
        )

        # Salvar no cache se habilitado
        if self.settings.nlu_cache_enabled and self.redis_client and cache_key:
            await self._cache_result(cache_key, result)

        logger.info(
            f"NLU processado: domínio={domain.value}, classificação={classification}, "
            f"confidence={confidence:.2f}, idioma={detected_language}"
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
                "requires_manual_validation": result.requires_manual_validation
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
        text = re.sub(r'\\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Z|a-z]{2,}\\b', '[EMAIL]', text)
        # CPF
        text = re.sub(r'\\b\\d{3}\\.\\d{3}\\.\\d{3}-\\d{2}\\b', '[CPF]', text)
        # Telefone
        text = re.sub(r'\\b\\d{2}\\s?\\d{4,5}-?\\d{4}\\b', '[PHONE]', text)
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

            # Calcular confidence baseado no score e contexto
            confidence = min(0.95, max_score / 5.0)  # Normalizar para 0-0.95

            # Bonus de confidence se temos contexto relevante
            if context and context.get('user_role'):
                confidence = min(0.98, confidence + 0.1)

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