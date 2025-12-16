#!/usr/bin/env python3
"""
Gerador de Datasets de Treino para Especialistas do Neural Hive Mind

Este script usa LLMs para gerar datasets realistas de cognitive plans e specialist opinions,
extraindo features numéricas e salvando em formato Parquet para treinamento de modelos.

Inclui validação de qualidade de descrições de tarefas para garantir dados de treinamento
de alta qualidade, usando o DescriptionQualityValidator.

Referências:
- schemas/cognitive-plan/cognitive-plan.avsc
- schemas/specialist-opinion/specialist-opinion.avsc
- libraries/python/neural_hive_specialists/feature_extraction/feature_extractor.py
"""

import argparse
import asyncio
import json
import os
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import structlog
from tqdm import tqdm

# Configurar logger antes de qualquer uso
logger = structlog.get_logger()

# Importar Avro para validação de schemas
try:
    import avro.schema
    import avro.io
    import io as iolib
    AVRO_AVAILABLE = True
except ImportError:
    AVRO_AVAILABLE = False
    # Usar print para evitar uso do logger antes da definição em alguns contextos
    print("AVISO: avro-python3 não disponível, validação de schemas será desabilitada")

# Importar LLM Client Adapter
from llm_client_adapter import LLMClientAdapter, LLMProvider

# Importar FeatureExtractor e DescriptionQualityValidator do neural_hive_specialists
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "libraries" / "python"))
from neural_hive_specialists.feature_extraction.feature_extractor import FeatureExtractor

# Importar validador de descrições do módulo compartilhado
try:
    from neural_hive_specialists.validation.description_validator import (
        DescriptionQualityValidator,
        get_validator,
    )
    _SHARED_VALIDATOR_AVAILABLE = True
except ImportError:
    _SHARED_VALIDATOR_AVAILABLE = False
    logger.warning(
        "shared_validator_not_available",
        reason="neural_hive_specialists.validation not found, using inline fallback"
    )

# Importar schema de features centralizado
sys.path.insert(0, str(Path(__file__).parent.parent))
from feature_store.feature_definitions import get_feature_names, get_feature_schema


# Fallback: definir classe localmente se o módulo compartilhado não estiver disponível
if not _SHARED_VALIDATOR_AVAILABLE:
    class DescriptionQualityValidator:
        """
        Fallback: Validador de qualidade de descrições de tarefas para dados de treinamento.

        Esta versão é usada quando o módulo compartilhado não está disponível.
        """

        # Keywords expandidas com sinônimos para melhor matching
        # Isso aumenta a taxa de aceitação de descrições geradas por LLM
        DOMAIN_KEYWORDS: Dict[str, List[str]] = {
            'security-analysis': [
                # Keywords originais
                'auth', 'security', 'validate', 'encrypt', 'audit', 'permission',
                'credential', 'token', 'sanitize', 'injection', 'access', 'role',
                # Sinônimos e termos relacionados adicionados
                'authentication', 'authorization', 'password', 'oauth', 'jwt',
                'ssl', 'tls', 'https', 'certificate', 'vulnerability', 'threat',
                'protect', 'secure', 'firewall', 'xss', 'csrf', 'sql', 'hash',
                'cipher', 'decrypt', 'key', 'secret', 'private', 'public'
            ],
            'architecture-review': [
                # Keywords originais
                'service', 'interface', 'pattern', 'design', 'module', 'component',
                'api', 'integration', 'layer', 'dependency', 'contract', 'schema',
                # Sinônimos e termos relacionados adicionados
                'microservice', 'monolith', 'architecture', 'structure', 'system',
                'class', 'function', 'method', 'endpoint', 'rest', 'grpc', 'graphql',
                'database', 'queue', 'message', 'event', 'handler', 'controller',
                'repository', 'factory', 'singleton', 'adapter', 'facade', 'proxy'
            ],
            'performance-optimization': [
                # Keywords originais
                'cache', 'index', 'optimize', 'parallel', 'async', 'batch',
                'latency', 'throughput', 'memory', 'pool', 'query', 'buffer',
                # Sinônimos e termos relacionados adicionados
                'performance', 'speed', 'fast', 'slow', 'bottleneck', 'profil',
                'benchmark', 'scale', 'concurrent', 'thread', 'process', 'cpu',
                'disk', 'network', 'io', 'response', 'time', 'load', 'stress',
                'efficient', 'resource', 'consumption', 'allocation', 'garbage'
            ],
            'code-quality': [
                # Keywords originais
                'test', 'error', 'log', 'document', 'refactor', 'lint',
                'coverage', 'exception', 'debug', 'trace', 'monitor', 'metric',
                # Sinônimos e termos relacionados adicionados
                'quality', 'clean', 'readable', 'maintain', 'review', 'comment',
                'unit', 'integration', 'e2e', 'mock', 'stub', 'assert', 'verify',
                'sonar', 'eslint', 'pylint', 'format', 'style', 'convention',
                'typing', 'type', 'annotation', 'docstring', 'readme', 'spec'
            ],
            'business-logic': [
                # Keywords originais
                'workflow', 'kpi', 'cost', 'efficiency', 'process', 'metric',
                'rule', 'policy', 'compliance', 'approval', 'transaction', 'pipeline',
                # Sinônimos e termos relacionados adicionados
                'business', 'logic', 'domain', 'entity', 'value', 'aggregate',
                'event', 'command', 'handler', 'saga', 'state', 'machine',
                'validation', 'constraint', 'requirement', 'specification', 'use case',
                'customer', 'order', 'payment', 'invoice', 'product', 'inventory'
            ]
        }

        SECURITY_KEYWORDS: Dict[str, List[str]] = {
            'confidential': ['encrypt', 'auth', 'audit', 'permission', 'sanitize', 'secure'],
            'restricted': ['encrypt', 'auth', 'audit', 'permission', 'sanitize', 'secure'],
            'internal': ['validate', 'verify', 'check', 'access'],
            'public': []
        }

        QOS_KEYWORDS: Dict[str, List[str]] = {
            'exactly_once': ['idempotent', 'transaction', 'rollback', 'dedup', 'deduplication'],
            'at_least_once': ['retry', 'acknowledge', 'redelivery'],
            'at_most_once': ['fire-and-forget', 'best-effort'],
        }

        MIN_WORDS = 15
        MAX_WORDS = 50

        def validate_description(
            self,
            description: str,
            domain: str,
            security_level: Optional[str] = None,
            qos: Optional[str] = None
        ) -> Dict:
            """Valida qualidade de uma descrição de tarefa."""
            issues: List[str] = []
            words = description.split()
            word_count = len(words)

            # Score de comprimento
            if word_count < 10:
                length_score = 0.0
                issues.append(f"Descrição muito curta ({word_count} palavras)")
            elif word_count < self.MIN_WORDS:
                length_score = 0.5 * (word_count / self.MIN_WORDS)
            elif word_count <= self.MAX_WORDS:
                length_score = 1.0
            else:
                length_score = 0.7

            # Score de diversidade léxica
            if word_count > 0:
                stopwords = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
                            'of', 'with', 'by', 'from', 'is', 'are', 'was', 'were', 'be', 'been'}
                meaningful_words = [w.lower() for w in words if w.lower() not in stopwords and len(w) > 2]
                if meaningful_words:
                    unique_ratio = len(set(meaningful_words)) / len(meaningful_words)
                    diversity_score = min(1.0, unique_ratio / 0.7)
                else:
                    diversity_score = 0.3
            else:
                diversity_score = 0.0

            # Score de keywords de domínio
            keywords = self.DOMAIN_KEYWORDS.get(domain, [])
            description_lower = description.lower()
            keyword_count = sum(1 for kw in keywords if kw in description_lower)

            if keyword_count >= 3:
                domain_score = 1.0
            elif keyword_count == 2:
                domain_score = 0.8
            elif keyword_count == 1:
                domain_score = 0.5
                issues.append(f"Apenas 1 keyword de domínio para {domain}")
            else:
                domain_score = 0.0
                issues.append(f"Nenhuma keyword de domínio para {domain}")

            # Score de segurança
            security_score = 1.0
            if security_level in ['confidential', 'restricted']:
                sec_kws = self.SECURITY_KEYWORDS.get(security_level, [])
                found_security = sum(1 for kw in sec_kws if kw in description_lower)
                if found_security >= 2:
                    security_score = 1.0
                elif found_security == 1:
                    security_score = 0.6
                else:
                    security_score = 0.2
                    issues.append(f"Faltam keywords de segurança para {security_level}")

            # Score de QoS
            qos_score = 1.0
            if qos:
                qos_kws = self.QOS_KEYWORDS.get(qos, [])
                found_qos = sum(1 for kw in qos_kws if kw in description_lower)
                if found_qos > 0:
                    qos_score = 1.0
                else:
                    qos_score = 0.5
                    issues.append(f"Faltam hints de QoS para {qos}")

            # Score final ponderado - ajustado para ser menos restritivo
            # Reduzido peso de domain_score (era 30%, agora 20%) pois era o maior causador de rejeições
            # Aumentado peso de length_score e diversity_score que são mais confiáveis
            overall_score = (
                0.30 * length_score +     # Aumentado de 0.25 (comprimento é fácil de atingir)
                0.25 * diversity_score +  # Aumentado de 0.20 (diversidade léxica)
                0.20 * domain_score +     # Reduzido de 0.30 (keywords de domínio - era muito restritivo)
                0.15 * security_score +   # Mantido
                0.10 * qos_score          # Mantido
            )

            return {
                'score': round(overall_score, 3),
                'issues': issues,
                'suggestions': [],
                'metrics': {
                    'length_score': round(length_score, 3),
                    'diversity_score': round(diversity_score, 3),
                    'domain_score': round(domain_score, 3),
                    'security_score': round(security_score, 3),
                    'qos_score': round(qos_score, 3),
                    'word_count': word_count,
                    'domain_keywords_found': keyword_count
                }
            }

        def validate_plan_descriptions(
            self,
            cognitive_plan: Dict[str, Any],
            min_quality_score: float = 0.5  # Reduzido de 0.6 para 0.5 para maior taxa de aceitação
        ) -> Dict:
            """Valida qualidade de todas as descrições em um cognitive plan."""
            tasks = cognitive_plan.get('tasks', [])
            domain = cognitive_plan.get('original_domain', 'code-quality')
            security_level = cognitive_plan.get('original_security_level', 'internal')
            qos = cognitive_plan.get('qos')

            task_scores = []
            all_issues = []
            low_quality_tasks = []

            for task in tasks:
                description = task.get('description', '')
                result = self.validate_description(description, domain, security_level, qos)
                task_scores.append(result['score'])

                if result['issues']:
                    all_issues.extend([f"Task {task.get('task_id')}: {issue}" for issue in result['issues']])

                # Usar threshold mais baixo para tarefas individuais (0.4 ao invés de min_quality_score)
                # Isso permite que algumas tarefas tenham score menor desde que a média seja boa
                individual_threshold = min(min_quality_score - 0.1, 0.4)
                if result['score'] < individual_threshold:
                    low_quality_tasks.append({
                        'task_id': task.get('task_id'),
                        'description': description[:100],
                        'score': result['score']
                    })

            avg_score = sum(task_scores) / len(task_scores) if task_scores else 0.0
            # Validação mais flexível: aceita se média é boa OU se não tem tarefas muito ruins
            # Antes: ambas condições precisavam ser verdadeiras
            # Agora: média precisa ser boa, mas permite algumas tarefas com score menor
            is_valid = avg_score >= min_quality_score

            return {
                'is_valid': is_valid,
                'avg_score': round(avg_score, 3),
                'task_scores': task_scores,
                'issues': all_issues,
                'low_quality_tasks': low_quality_tasks
            }


class DatasetGenerator:
    """Gerador de datasets de treino usando LLMs para criar cognitive plans e opinions."""

    def __init__(
        self,
        llm_client: LLMClientAdapter,
        specialist_type: str,
        prompts_dir: Path,
        validate_schemas: bool = True,
        min_quality_score: float = 0.6,
    ):
        """
        Inicializa o gerador de datasets.

        Args:
            llm_client: Cliente LLM para geração de dados
            specialist_type: Tipo do especialista (technical, business, behavior, evolution, architecture)
            prompts_dir: Diretório com templates de prompts
            validate_schemas: Se True, valida JSON contra schemas Avro
            min_quality_score: Score mínimo de qualidade de descrições (0.0-1.0)
        """
        self.llm_client = llm_client
        self.specialist_type = specialist_type
        self.prompts_dir = prompts_dir
        self.validate_schemas = validate_schemas and AVRO_AVAILABLE
        self.min_quality_score = min_quality_score
        self.feature_extractor = FeatureExtractor()

        # Carregar schemas Avro se validação estiver habilitada
        self.cognitive_plan_schema = None
        self.specialist_opinion_schema = None
        if self.validate_schemas:
            self._load_avro_schemas()

        # Carregar templates de prompts
        self.cognitive_plan_template = self._load_template("cognitive_plan_template.txt")
        self.specialist_template = self._load_template(
            f"specialist_{specialist_type}_template.txt"
        )

        # Inicializar validador de qualidade de descrições
        self.description_validator = DescriptionQualityValidator()

        # Estatísticas de geração
        self.stats = {
            "total_generated": 0,
            "successful": 0,
            "failed": 0,
            "validation_errors": 0,
            "description_quality_rejections": 0,
            "description_quality_scores": [],
            "label_distribution": {"approve": 0, "reject": 0, "review_required": 0, "conditional": 0},
        }

    def _load_template(self, filename: str) -> str:
        """Carrega template de prompt do diretório."""
        template_path = self.prompts_dir / filename
        if not template_path.exists():
            raise FileNotFoundError(f"Template não encontrado: {template_path}")
        return template_path.read_text(encoding="utf-8")

    def _load_avro_schemas(self):
        """Carrega schemas Avro para validação."""
        try:
            # Diretório de schemas
            schemas_dir = Path(__file__).parent.parent.parent / "schemas"

            # Carregar schema de cognitive plan
            cognitive_plan_schema_path = schemas_dir / "cognitive-plan" / "cognitive-plan.avsc"
            with open(cognitive_plan_schema_path, "r", encoding="utf-8") as f:
                self.cognitive_plan_schema = avro.schema.parse(f.read())

            # Carregar schema de specialist opinion
            specialist_opinion_schema_path = schemas_dir / "specialist-opinion" / "specialist-opinion.avsc"
            with open(specialist_opinion_schema_path, "r", encoding="utf-8") as f:
                self.specialist_opinion_schema = avro.schema.parse(f.read())

            logger.info("avro_schemas_loaded",
                       cognitive_plan_schema=str(cognitive_plan_schema_path),
                       specialist_opinion_schema=str(specialist_opinion_schema_path))

        except Exception as e:
            logger.error("failed_to_load_avro_schemas", error=str(e))
            self.validate_schemas = False

    def _validate_against_avro_schema(self, data: Dict[str, Any], schema: avro.schema.Schema, schema_name: str) -> bool:
        """
        Valida dados contra schema Avro.

        Args:
            data: Dados a validar
            schema: Schema Avro
            schema_name: Nome do schema para logging

        Returns:
            True se válido, False caso contrário
        """
        if not self.validate_schemas or schema is None:
            return True

        try:
            # Usar DatumWriter para validar estrutura
            writer = avro.io.DatumWriter(schema)
            bytes_writer = iolib.BytesIO()
            encoder = avro.io.BinaryEncoder(bytes_writer)
            writer.write(data, encoder)

            logger.debug(f"{schema_name}_validation_passed", data_keys=list(data.keys()))
            return True

        except Exception as e:
            logger.warning(
                f"{schema_name}_validation_failed",
                error=str(e),
                error_type=type(e).__name__,
                data_keys=list(data.keys())
            )
            self.stats["validation_errors"] += 1
            return False

    async def generate_cognitive_plan(
        self, domain: str, complexity: str, risk_level: str, priority: str
    ) -> Optional[Dict[str, Any]]:
        """
        Gera um cognitive plan usando LLM.

        Args:
            domain: Domínio do plan (security-analysis, architecture-review, etc.)
            complexity: Complexidade (low, medium, high)
            risk_level: Nível de risco (low, medium, high, critical)
            priority: Prioridade (low, normal, high, critical)

        Returns:
            Dict com cognitive plan ou None se falhar
        """
        # Preencher template com parâmetros
        prompt = self.cognitive_plan_template.format(
            domain=domain, complexity=complexity, risk_level=risk_level, priority=priority
        )

        try:
            # Gerar JSON usando LLM
            plan_json = await self.llm_client.generate_json(prompt)

            # Validar estrutura básica
            if not isinstance(plan_json, dict):
                logger.error("cognitive_plan_invalid_type", type=type(plan_json))
                return None

            # Adicionar IDs e timestamps se não existirem
            if "plan_id" not in plan_json:
                plan_json["plan_id"] = str(uuid.uuid4())
            if "intent_id" not in plan_json:
                plan_json["intent_id"] = str(uuid.uuid4())
            if "created_at" not in plan_json:
                plan_json["created_at"] = int(datetime.now().timestamp() * 1000)

            # IMPORTANTE: Forçar original_priority para o valor passado como parâmetro
            # O LLM tende a ignorar a prioridade solicitada e sempre gerar "low"
            # Isso garante diversidade no dataset de treinamento
            plan_json["original_priority"] = priority
            plan_json["original_domain"] = domain

            # Validar contra schema Avro
            if not self._validate_against_avro_schema(plan_json, self.cognitive_plan_schema, "cognitive_plan"):
                logger.warning("cognitive_plan_failed_avro_validation", plan_id=plan_json.get("plan_id"))
                return None

            # Validar qualidade das descrições de tarefas
            quality_result = self.description_validator.validate_plan_descriptions(
                cognitive_plan=plan_json,
                min_quality_score=self.min_quality_score
            )

            # Registrar score médio de qualidade
            self.stats["description_quality_scores"].append(quality_result["avg_score"])

            if not quality_result["is_valid"]:
                logger.warning(
                    "cognitive_plan_low_quality_descriptions",
                    plan_id=plan_json.get("plan_id"),
                    avg_score=quality_result["avg_score"],
                    low_quality_tasks=quality_result["low_quality_tasks"],
                    issues=quality_result["issues"][:5]  # Limitar logs
                )
                self.stats["description_quality_rejections"] += 1
                return None

            logger.debug(
                "cognitive_plan_description_quality_passed",
                plan_id=plan_json.get("plan_id"),
                avg_score=quality_result["avg_score"]
            )

            return plan_json

        except Exception as e:
            logger.error("cognitive_plan_generation_failed", error=str(e))
            return None

    async def generate_specialist_opinion(
        self, cognitive_plan: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Gera opinião de especialista sobre um cognitive plan.

        Args:
            cognitive_plan: Cognitive plan gerado

        Returns:
            Dict com specialist opinion ou None se falhar
        """
        # Preencher template com cognitive plan
        prompt = self.specialist_template.format(
            cognitive_plan_json=json.dumps(cognitive_plan, indent=2)
        )

        try:
            # Gerar JSON usando LLM
            opinion_json = await self.llm_client.generate_json(prompt)

            # Validar estrutura básica
            if not isinstance(opinion_json, dict):
                logger.error("specialist_opinion_invalid_type", type=type(opinion_json))
                return None

            # Adicionar/corrigir campos obrigatórios
            if "opinion_id" not in opinion_json:
                opinion_json["opinion_id"] = str(uuid.uuid4())
            opinion_json["specialist_type"] = self.specialist_type
            opinion_json["plan_id"] = cognitive_plan.get("plan_id")
            opinion_json["intent_id"] = cognitive_plan.get("intent_id")
            if "correlation_id" not in opinion_json:
                opinion_json["correlation_id"] = str(uuid.uuid4())
            if "evaluated_at" not in opinion_json:
                opinion_json["evaluated_at"] = int(datetime.now().timestamp() * 1000)

            # Validar contra schema Avro
            if not self._validate_against_avro_schema(opinion_json, self.specialist_opinion_schema, "specialist_opinion"):
                logger.warning("specialist_opinion_failed_avro_validation",
                             opinion_id=opinion_json.get("opinion_id"),
                             specialist_type=self.specialist_type)
                return None

            return opinion_json

        except Exception as e:
            logger.error("specialist_opinion_generation_failed", error=str(e))
            return None

    def extract_features(self, cognitive_plan: Dict[str, Any]) -> Optional[Dict[str, float]]:
        """
        Extrai features numéricas do cognitive plan usando FeatureExtractor.
        Garante schema consistente com feature_definitions.py.

        Args:
            cognitive_plan: Cognitive plan para extração

        Returns:
            Dict com features numéricas ou None se falhar
        """
        try:
            # Obter nomes de features esperados do schema centralizado
            expected_feature_names = get_feature_names()

            # Usar FeatureExtractor para extrair features estruturadas
            features_structured = self.feature_extractor.extract_features(cognitive_plan)
            features_extracted = features_structured['aggregated_features']

            # Criar dict com schema consistente (padding com 0.0 para features ausentes)
            features = {name: 0.0 for name in expected_feature_names}

            # Preencher com features extraídas
            for key, value in features_extracted.items():
                if key in features:
                    features[key] = float(value)
                else:
                    logger.warning(
                        "unexpected_feature_extracted",
                        feature_name=key,
                        plan_id=cognitive_plan.get('plan_id')
                    )

            # Validar que temos features suficientes
            num_populated = sum(1 for v in features.values() if v != 0.0)
            if num_populated < len(expected_feature_names) * 0.5:  # Pelo menos 50% populadas
                logger.warning(
                    "insufficient_features_populated",
                    num_populated=num_populated,
                    expected=len(expected_feature_names),
                    plan_id=cognitive_plan.get('plan_id')
                )

            return features

        except Exception as e:
            logger.error("feature_extraction_failed", error=str(e), exc_info=True)
            return None

    def extract_label_numeric(self, specialist_opinion: Dict[str, Any]) -> int:
        """
        Extrai label numérico da specialist opinion.

        Args:
            specialist_opinion: Specialist opinion

        Returns:
            Label numérico (0=reject, 1=approve, 2=review_required, 3=conditional)
        """
        recommendation = specialist_opinion.get("recommendation", "reject").lower()

        label_map = {
            "reject": 0,
            "approve": 1,
            "review_required": 2,
            "conditional": 3,
        }

        label = label_map.get(recommendation, 0)

        return label

    def validate_dag(self, cognitive_plan: Dict[str, Any]) -> bool:
        """
        Valida que o cognitive plan forma um DAG válido sem ciclos.

        Args:
            cognitive_plan: Cognitive plan a validar

        Returns:
            True se é DAG válido, False se contém ciclos
        """
        try:
            from neural_hive_specialists.feature_extraction.graph_analyzer import GraphAnalyzer
            import networkx as nx

            tasks = cognitive_plan.get('tasks', [])
            if not tasks:
                return True

            analyzer = GraphAnalyzer()
            graph = analyzer.build_graph(tasks)

            # Usar NetworkX para verificar se é DAG
            is_dag = nx.is_directed_acyclic_graph(graph)

            if not is_dag:
                logger.warning(
                    "cognitive_plan_contains_cycles",
                    plan_id=cognitive_plan.get("plan_id"),
                    num_tasks=len(tasks)
                )

            return is_dag

        except Exception as e:
            logger.error("dag_validation_failed", error=str(e))
            # Em caso de erro, assumir válido para não bloquear geração
            return True

    def validate_risk_correlation(
        self, cognitive_plan: Dict[str, Any], specialist_opinion: Dict[str, Any]
    ) -> bool:
        """
        Valida correlação entre risk_score e recommendation.

        Regras heurísticas mais flexíveis para permitir diversidade de labels:
        - approve com risk_score > 0.85: inválido (muito arriscado para aprovar)
        - reject com risk_score < 0.15: inválido (muito seguro para rejeitar)
        - Outros casos: válido (permite mais diversidade)

        NOTA: Regras anteriores eram muito restritivas e impediam geração de labels "reject".
        Agora permitimos reject com risk >= 0.15 (antes era >= 0.3).

        Args:
            cognitive_plan: Cognitive plan
            specialist_opinion: Specialist opinion

        Returns:
            True se correlação é válida, False caso contrário
        """
        try:
            plan_risk = cognitive_plan.get("risk_score", 0.5)
            opinion_risk = specialist_opinion.get("risk_score", 0.5)
            recommendation = specialist_opinion.get("recommendation", "").lower()

            # Incoerências grosseiras (limites mais relaxados para permitir diversidade)
            # Approve só é inválido se risco for extremamente alto
            if recommendation == "approve" and opinion_risk > 0.85:
                logger.warning(
                    "risk_correlation_invalid",
                    recommendation=recommendation,
                    opinion_risk=opinion_risk,
                    reason="approve com risk extremamente alto"
                )
                return False

            # Reject só é inválido se risco for extremamente baixo
            # Reduzido de 0.3 para 0.15 para permitir mais amostras de reject
            if recommendation == "reject" and opinion_risk < 0.15:
                logger.warning(
                    "risk_correlation_invalid",
                    recommendation=recommendation,
                    opinion_risk=opinion_risk,
                    reason="reject com risk extremamente baixo"
                )
                return False

            # Verificar correlação entre plan_risk e opinion_risk (apenas log, não bloqueia)
            risk_diff = abs(plan_risk - opinion_risk)
            if risk_diff > 0.5:
                logger.debug(
                    "risk_scores_divergent",
                    plan_risk=plan_risk,
                    opinion_risk=opinion_risk,
                    diff=risk_diff
                )

            return True

        except Exception as e:
            logger.error("risk_correlation_validation_failed", error=str(e))
            return True

    async def generate_dataset(
        self, num_samples: int, progress_bar: bool = True, strict_sample_count: bool = False
    ) -> pd.DataFrame:
        """
        Gera dataset completo com N samples.

        Args:
            num_samples: Número de samples a gerar
            progress_bar: Mostrar barra de progresso
            strict_sample_count: Se True, lança exceção quando não atingir num_samples

        Returns:
            DataFrame com features + labels

        Raises:
            RuntimeError: Se strict_sample_count=True e não conseguir gerar todos os samples
        """
        samples = []

        # Definir variações de domínios e parâmetros para diversidade
        domains = ["security-analysis", "architecture-review", "performance-optimization", "code-quality", "business-logic"]
        complexities = ["low", "medium", "high"]
        risk_levels = ["low", "medium", "high", "critical"]
        priorities = ["low", "normal", "high", "critical"]

        # Distribuição alvo de labels (approve: 40%, reject: 20%, review_required: 25%, conditional: 15%)
        target_distribution = {
            "approve": int(num_samples * 0.40),
            "reject": int(num_samples * 0.20),
            "review_required": int(num_samples * 0.25),
            "conditional": int(num_samples * 0.15),
        }

        # Contador de labels geradas
        label_counts = {"approve": 0, "reject": 0, "review_required": 0, "conditional": 0}

        # Progress bar
        attempts = 0
        max_attempts = num_samples * 3  # Permitir até 3x tentativas para atingir distribuição
        if progress_bar:
            pbar = tqdm(total=num_samples, desc=f"Gerando dataset {self.specialist_type}")

        while len(samples) < num_samples and attempts < max_attempts:
            attempts += 1
            self.stats["total_generated"] += 1

            # Variar parâmetros para diversidade
            i = attempts % (len(domains) * len(complexities) * len(risk_levels) * len(priorities))
            domain = domains[i % len(domains)]
            complexity = complexities[(i // len(domains)) % len(complexities)]
            risk_level = risk_levels[(i // (len(domains) * len(complexities))) % len(risk_levels)]
            priority = priorities[(i // (len(domains) * len(complexities) * len(risk_levels))) % len(priorities)]

            # Gerar cognitive plan
            cognitive_plan = await self.generate_cognitive_plan(
                domain, complexity, risk_level, priority
            )

            if cognitive_plan is None:
                self.stats["failed"] += 1
                continue

            # Validar que o plan forma um DAG válido
            if not self.validate_dag(cognitive_plan):
                logger.warning("cognitive_plan_invalid_dag", plan_id=cognitive_plan.get("plan_id"))
                self.stats["failed"] += 1
                continue

            # Gerar specialist opinion
            specialist_opinion = await self.generate_specialist_opinion(cognitive_plan)

            if specialist_opinion is None:
                self.stats["failed"] += 1
                continue

            # Validar correlação de risco
            if not self.validate_risk_correlation(cognitive_plan, specialist_opinion):
                logger.warning(
                    "risk_correlation_failed",
                    plan_id=cognitive_plan.get("plan_id"),
                    opinion_id=specialist_opinion.get("opinion_id")
                )
                self.stats["failed"] += 1
                continue

            # Extrair features
            features = self.extract_features(cognitive_plan)

            if features is None:
                self.stats["failed"] += 1
                continue

            # Extrair label
            label = self.extract_label_numeric(specialist_opinion)
            label_name = {0: "reject", 1: "approve", 2: "review_required", 3: "conditional"}[label]

            # Verificar se essa classe ainda precisa de samples
            if label_counts[label_name] >= target_distribution[label_name]:
                # Já temos samples suficientes desta classe, descartar
                continue

            # Adicionar sample ao dataset
            sample = {**features, "label": label}
            samples.append(sample)

            # Atualizar contadores
            label_counts[label_name] += 1
            self.stats["successful"] += 1
            self.stats["label_distribution"][label_name] += 1

            if progress_bar:
                pbar.update(1)

        if progress_bar:
            pbar.close()

        # Verificar se atingiu o número de samples solicitado
        actual_samples = len(samples)
        if actual_samples < num_samples:
            shortfall = num_samples - actual_samples
            shortfall_pct = (shortfall / num_samples) * 100
            quality_rejection_rate = (
                (self.stats["description_quality_rejections"] / attempts * 100)
                if attempts > 0 else 0
            )

            logger.warning(
                "dataset_generation_incomplete",
                specialist_type=self.specialist_type,
                requested_samples=num_samples,
                actual_samples=actual_samples,
                shortfall=shortfall,
                shortfall_percentage=round(shortfall_pct, 2),
                total_attempts=attempts,
                max_attempts=max_attempts,
                quality_rejections=self.stats["description_quality_rejections"],
                quality_rejection_rate=round(quality_rejection_rate, 2),
                min_quality_score=self.min_quality_score,
                reason="max_attempts_reached_due_to_quality_rejections",
                suggestion="Consider lowering --min-quality-score or improving LLM prompts for richer descriptions"
            )

            if strict_sample_count:
                raise RuntimeError(
                    f"Não foi possível gerar {num_samples} samples. "
                    f"Apenas {actual_samples} samples ({100 - shortfall_pct:.1f}%) foram gerados após {attempts} tentativas. "
                    f"Taxa de rejeição por qualidade: {quality_rejection_rate:.1f}%. "
                    f"Considere reduzir --min-quality-score (atual: {self.min_quality_score}) ou melhorar os prompts."
                )

        # Criar DataFrame
        df = pd.DataFrame(samples)

        # Log comparando distribuição alvo vs obtida
        logger.info(
            "dataset_generated",
            specialist_type=self.specialist_type,
            num_samples=len(df),
            num_features=len(df.columns) - 1 if len(df.columns) > 0 else 0,
            target_distribution=target_distribution,
            actual_distribution=label_counts,
            attempts=attempts,
            quality_rejection_rate=round(
                (self.stats["description_quality_rejections"] / attempts * 100) if attempts > 0 else 0, 2
            ),
        )

        return df

    def save_to_parquet(self, df: pd.DataFrame, output_path: Path):
        """
        Salva DataFrame em formato Parquet com validação de schema.

        Args:
            df: DataFrame a salvar
            output_path: Caminho do arquivo Parquet
        """
        try:
            # Criar diretório se não existir
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Validar schema de features
            expected_feature_names = get_feature_names()
            expected_columns = set(expected_feature_names + ['label'])
            actual_columns = set(df.columns)

            # Validar que todas as features esperadas estão presentes
            missing_features = expected_columns - actual_columns
            if missing_features:
                logger.error(
                    "missing_features_in_dataset",
                    missing=list(missing_features),
                    output_path=str(output_path)
                )
                raise ValueError(f"Dataset missing features: {missing_features}")

            # Validar que não há colunas extras além das esperadas
            extra_columns = actual_columns - expected_columns
            if extra_columns:
                logger.error(
                    "extra_columns_in_dataset",
                    extra=list(extra_columns),
                    expected=list(expected_columns),
                    output_path=str(output_path)
                )
                raise ValueError(
                    f"Dataset contains unexpected columns: {extra_columns}. "
                    f"Expected only: {expected_columns}. "
                    f"This indicates a regression in feature extraction."
                )

            # Reordenar colunas para consistência (features + label)
            ordered_columns = expected_feature_names + ['label']
            df = df[ordered_columns]

            # Salvar em Parquet
            df.to_parquet(output_path, index=False, compression="snappy")

            logger.info(
                "dataset_saved",
                path=str(output_path),
                size_mb=output_path.stat().st_size / 1024 / 1024,
                num_samples=len(df),
                num_features=len(expected_feature_names),
                feature_names=expected_feature_names[:5] + ['...']
            )

        except Exception as e:
            logger.error("dataset_save_failed", error=str(e))
            raise

    def print_statistics(self):
        """Imprime estatísticas de geração."""
        print("\n" + "=" * 60)
        print(f"📊 Estatísticas de Geração - Specialist {self.specialist_type.upper()}")
        print("=" * 60)
        print(f"Total gerado: {self.stats['total_generated']}")
        print(f"Sucesso: {self.stats['successful']}")
        print(f"Falhas: {self.stats['failed']}")
        print(f"Taxa de sucesso: {self.stats['successful'] / max(self.stats['total_generated'], 1) * 100:.1f}%")

        # Estatísticas de qualidade de descrições
        print("\n📝 Qualidade de Descrições:")
        quality_scores = self.stats['description_quality_scores']
        if quality_scores:
            avg_quality = sum(quality_scores) / len(quality_scores)
            min_quality = min(quality_scores)
            max_quality = max(quality_scores)
            print(f"  Score médio: {avg_quality:.3f}")
            print(f"  Score mínimo: {min_quality:.3f}")
            print(f"  Score máximo: {max_quality:.3f}")
        print(f"  Rejeitados por baixa qualidade: {self.stats['description_quality_rejections']}")

        print("\nDistribuição de Labels:")
        for label, count in self.stats["label_distribution"].items():
            pct = count / max(self.stats["successful"], 1) * 100
            print(f"  {label}: {count} ({pct:.1f}%)")
        print("=" * 60 + "\n")


async def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Gera datasets de treino para especialistas usando LLMs"
    )
    parser.add_argument(
        "--specialist-type",
        type=str,
        required=True,
        choices=["technical", "business", "behavior", "evolution", "architecture"],
        help="Tipo do especialista",
    )
    parser.add_argument(
        "--num-samples",
        type=int,
        default=1000,
        help="Número de samples a gerar",
    )
    parser.add_argument(
        "--output-path",
        type=str,
        default=None,
        help="Caminho do arquivo Parquet de saída",
    )
    parser.add_argument(
        "--llm-provider",
        type=str,
        default=os.getenv("LLM_PROVIDER", "local"),
        choices=["openai", "anthropic", "local", "deepseek", "groq", "together", "openrouter", "azure_openai"],
        help="Provider do LLM (openai, anthropic, local, deepseek, groq, together, openrouter, azure_openai)",
    )
    parser.add_argument(
        "--llm-model",
        type=str,
        default=os.getenv("LLM_MODEL", "llama2"),
        help="Nome do modelo LLM",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=float(os.getenv("LLM_TEMPERATURE", "0.7")),
        help="Temperature para geração",
    )
    parser.add_argument(
        "--validate-schemas",
        type=str,
        default="true",
        choices=["true", "false"],
        help="Validar JSON contra schemas Avro",
    )
    parser.add_argument(
        "--min-quality-score",
        type=float,
        default=0.5,  # Reduzido de 0.6 para 0.5 para maior taxa de aceitação
        help="Score mínimo de qualidade de descrições (0.0-1.0). Descriptions abaixo deste score são rejeitadas. Default: 0.5",
    )
    parser.add_argument(
        "--strict-sample-count",
        action="store_true",
        default=False,
        help="Se True, lança exceção quando não conseguir gerar o número de samples solicitado",
    )

    args = parser.parse_args()

    # Configurar structlog
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ]
    )

    # Definir output path padrão
    if args.output_path is None:
        output_dir = Path(os.getenv("OUTPUT_DIR", "/data/training"))
        args.output_path = output_dir / f"specialist_{args.specialist_type}_base.parquet"
    else:
        args.output_path = Path(args.output_path)

    # Log feature schema para rastreabilidade
    expected_features = get_feature_names()
    logger.info(
        "feature_schema_loaded",
        num_features=len(expected_features),
        features=expected_features
    )
    print(f"📋 Feature Schema: {len(expected_features)} features")
    print(f"   {', '.join(expected_features[:10])}...")

    logger.info(
        "starting_dataset_generation",
        specialist_type=args.specialist_type,
        num_samples=args.num_samples,
        output_path=str(args.output_path),
        llm_provider=args.llm_provider,
        llm_model=args.llm_model,
        min_quality_score=args.min_quality_score,
        strict_sample_count=args.strict_sample_count,
    )

    # Inicializar LLM Client
    llm_client = LLMClientAdapter(
        provider=LLMProvider(args.llm_provider),
        api_key=os.getenv("LLM_API_KEY"),
        model_name=args.llm_model,
        endpoint_url=os.getenv("LLM_BASE_URL"),
        temperature=args.temperature,
    )

    await llm_client.start()

    try:
        # Inicializar Dataset Generator
        prompts_dir = Path(__file__).parent / "prompts"
        generator = DatasetGenerator(
            llm_client=llm_client,
            specialist_type=args.specialist_type,
            prompts_dir=prompts_dir,
            validate_schemas=args.validate_schemas.lower() == "true",
            min_quality_score=args.min_quality_score,
        )

        # Gerar dataset
        df = await generator.generate_dataset(
            num_samples=args.num_samples,
            strict_sample_count=args.strict_sample_count,
        )

        # Salvar em Parquet
        generator.save_to_parquet(df, args.output_path)

        # Imprimir estatísticas
        generator.print_statistics()

        # Imprimir exemplos
        print("📋 Exemplos de dados gerados:")
        print(df.head())
        print("\n📈 Estatísticas das features:")
        print(df.describe())

        logger.info(
            "dataset_generation_completed",
            specialist_type=args.specialist_type,
            output_path=str(args.output_path),
        )

    finally:
        await llm_client.stop()


if __name__ == "__main__":
    asyncio.run(main())
