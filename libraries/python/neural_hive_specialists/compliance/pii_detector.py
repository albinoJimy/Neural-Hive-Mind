"""
Detector e anonimizador de PII usando Presidio.
"""
import structlog
from typing import Dict, List, Any, Tuple, Optional
from functools import lru_cache
import hashlib

logger = structlog.get_logger(__name__)


class PIIDetector:
    """
    Detecta e anonimiza informações pessoalmente identificáveis (PII) em texto.

    Usa Microsoft Presidio para detectar entidades PII como:
    - PERSON: nomes de pessoas
    - EMAIL_ADDRESS: emails
    - PHONE_NUMBER: telefones
    - CREDIT_CARD: cartões de crédito
    - LOCATION: localizações
    - DATE_TIME: datas

    Suporta múltiplas estratégias de anonimização:
    - replace: substituir por placeholder (ex: <PERSON>)
    - mask: mascarar com asteriscos (ex: ***@***.com)
    - redact: remover completamente
    - hash: substituir por hash SHA-256 truncado
    """

    def __init__(self, config):
        """
        Inicializa PIIDetector com configuração.

        Args:
            config: SpecialistConfig com configurações de PII detection
        """
        self.config = config
        self.enabled = config.enable_pii_detection

        if not self.enabled:
            logger.info("PIIDetector desabilitado por configuração")
            return

        # Lazy import para evitar erro se Presidio não instalado
        try:
            from presidio_analyzer import AnalyzerEngine
            from presidio_analyzer.nlp_engine import NlpEngineProvider
            from presidio_anonymizer import AnonymizerEngine
            from presidio_anonymizer.entities import OperatorConfig

            self.AnalyzerEngine = AnalyzerEngine
            self.AnonymizerEngine = AnonymizerEngine
            self.OperatorConfig = OperatorConfig

            # Configurar NLP engines para múltiplos idiomas
            nlp_configuration = {"nlp_engine_name": "spacy", "models": []}

            # Mapear idiomas para modelos spaCy
            language_models = {"pt": "pt_core_news_sm", "en": "en_core_web_sm"}

            supported_languages = []
            for lang in config.pii_detection_languages:
                if lang in language_models:
                    nlp_configuration["models"].append(
                        {"lang_code": lang, "model_name": language_models[lang]}
                    )
                    supported_languages.append(lang)
                else:
                    logger.warning(
                        "Idioma não suportado para PII detection - ignorado",
                        language=lang,
                        supported_languages=list(language_models.keys()),
                    )

            # Criar NLP engine provider
            try:
                nlp_engine = NlpEngineProvider(
                    nlp_configuration=nlp_configuration
                ).create_engine()

                # Inicializar engines Presidio com NLP engine configurado
                self.analyzer = AnalyzerEngine(
                    nlp_engine=nlp_engine, supported_languages=supported_languages
                )
                self.anonymizer = AnonymizerEngine()
                self.supported_languages = supported_languages

                logger.info(
                    "PIIDetector inicializado com sucesso",
                    languages=supported_languages,
                    entities=config.pii_entities_to_detect,
                    strategy=config.pii_anonymization_strategy,
                )

            except Exception as nlp_error:
                logger.error(
                    "Falha ao carregar modelos spaCy - PII detection desabilitado",
                    error=str(nlp_error),
                    hint="Execute: python -m spacy download pt_core_news_sm && python -m spacy download en_core_web_sm",
                )
                self.enabled = False
                return

        except ImportError as e:
            logger.error(
                "Falha ao importar Presidio - PII detection desabilitado",
                error=str(e),
                hint="Instale presidio-analyzer e presidio-anonymizer",
            )
            self.enabled = False

        except Exception as e:
            logger.error("Falha ao inicializar Presidio engines", error=str(e))
            self.enabled = False

    def detect_pii(self, text: str, language: str = "pt") -> List[Any]:
        """
        Detecta entidades PII em texto.

        Args:
            text: Texto para analisar
            language: Código de idioma (pt, en)

        Returns:
            Lista de RecognizerResult com entidades detectadas
        """
        if not self.enabled or not text:
            return []

        # Validar e fazer fallback de idioma se não suportado
        if (
            hasattr(self, "supported_languages")
            and language not in self.supported_languages
        ):
            logger.warning(
                "Idioma não suportado - usando fallback para 'en'",
                requested_language=language,
                supported_languages=self.supported_languages,
            )
            language = (
                "en"
                if "en" in self.supported_languages
                else self.supported_languages[0]
            )

        try:
            results = self.analyzer.analyze(
                text=text,
                language=language,
                entities=self.config.pii_entities_to_detect,
            )

            logger.debug(
                "PII detection executada",
                text_length=len(text),
                entities_found=len(results),
                language=language,
            )

            return results

        except Exception as e:
            logger.warning(
                "Erro ao detectar PII - retornando lista vazia",
                error=str(e),
                text_length=len(text) if text else 0,
            )
            return []

    def anonymize_text(self, text: str, language: str = "pt") -> Tuple[str, List[Dict]]:
        """
        Anonimiza texto detectando e substituindo PII.

        Args:
            text: Texto para anonimizar
            language: Código de idioma

        Returns:
            Tupla (texto_anonimizado, metadados_pii)

        Exemplo:
            >>> text = "João Silva mora em São Paulo, email joao@example.com"
            >>> anonymized, metadata = detector.anonymize_text(text)
            >>> print(anonymized)
            "<PERSON> mora em <LOCATION>, email <EMAIL_ADDRESS>"
            >>> print(metadata)
            [{'entity_type': 'PERSON', 'start': 0, 'end': 10, ...}, ...]
        """
        if not self.enabled or not text:
            return text, []

        # Validar e fazer fallback de idioma se não suportado
        if (
            hasattr(self, "supported_languages")
            and language not in self.supported_languages
        ):
            logger.warning(
                "Idioma não suportado - usando fallback para 'en'",
                requested_language=language,
                supported_languages=self.supported_languages,
            )
            language = (
                "en"
                if "en" in self.supported_languages
                else self.supported_languages[0]
            )

        try:
            # Detectar PII
            analyzer_results = self.detect_pii(text, language)

            if not analyzer_results:
                return text, []

            # Obter operadores de anonimização
            operators = self._get_anonymization_operators()

            # Anonimizar texto
            anonymized_result = self.anonymizer.anonymize(
                text=text, analyzer_results=analyzer_results, operators=operators
            )

            # Construir metadados
            metadata = []
            for result in analyzer_results:
                metadata.append(
                    {
                        "entity_type": result.entity_type,
                        "start": result.start,
                        "end": result.end,
                        "score": result.score,
                        "anonymized": True,
                    }
                )

            logger.info(
                "Texto anonimizado com sucesso",
                original_length=len(text),
                anonymized_length=len(anonymized_result.text),
                entities_count=len(metadata),
            )

            return anonymized_result.text, metadata

        except Exception as e:
            logger.error(
                "Erro ao anonimizar texto - retornando texto original", error=str(e)
            )
            return text, []

    def anonymize_dict(
        self, data: Dict[str, Any], fields_to_scan: List[str], language: str = "pt"
    ) -> Tuple[Dict[str, Any], List[Dict]]:
        """
        Varre dicionário recursivamente anonimizando campos especificados.

        Args:
            data: Dicionário para processar
            fields_to_scan: Lista de nomes de campos para varrer
            language: Código de idioma

        Returns:
            Tupla (dicionário_anonimizado, metadados_agregados)
        """
        if not self.enabled:
            return data, []

        anonymized_data = data.copy()
        all_metadata = []

        for field in fields_to_scan:
            value = self._get_nested_value(data, field)

            if value and isinstance(value, str):
                anonymized_value, metadata = self.anonymize_text(value, language)

                if metadata:
                    self._set_nested_value(anonymized_data, field, anonymized_value)

                    # Adicionar contexto ao metadata
                    for meta in metadata:
                        meta["field"] = field
                    all_metadata.extend(metadata)

        return anonymized_data, all_metadata

    def _get_anonymization_operators(self) -> Dict[str, Any]:
        """
        Mapeia estratégia de anonimização para operadores Presidio.

        Returns:
            Dicionário com operadores para cada tipo de entidade
        """
        strategy = self.config.pii_anonymization_strategy

        if strategy == "replace":
            # Substituir por placeholder
            return None  # Presidio usa replace por padrão

        elif strategy == "mask":
            # Mascarar com asteriscos
            operators = {}
            for entity in self.config.pii_entities_to_detect:
                operators[entity] = self.OperatorConfig(
                    "mask",
                    {
                        "type": "mask",
                        "masking_char": "*",
                        "chars_to_mask": 100,
                        "from_end": False,
                    },
                )
            return operators

        elif strategy == "redact":
            # Remover completamente
            operators = {}
            for entity in self.config.pii_entities_to_detect:
                operators[entity] = self.OperatorConfig("redact", {})
            return operators

        elif strategy == "hash":
            # Substituir por hash
            operators = {}
            for entity in self.config.pii_entities_to_detect:
                operators[entity] = self.OperatorConfig("hash", {"hash_type": "sha256"})
            return operators

        else:
            logger.warning(
                "Estratégia de anonimização desconhecida - usando replace",
                strategy=strategy,
            )
            return None

    @staticmethod
    def _get_nested_value(data: Dict, path: str) -> Any:
        """Obtém valor de path aninhado (ex: 'opinion.reasoning')."""
        keys = path.split(".")
        value = data
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return None
        return value

    @staticmethod
    def _set_nested_value(data: Dict, path: str, value: Any) -> None:
        """Define valor de path aninhado."""
        keys = path.split(".")
        current = data
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        current[keys[-1]] = value
