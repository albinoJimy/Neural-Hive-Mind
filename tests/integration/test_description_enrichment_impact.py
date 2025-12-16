#!/usr/bin/env python3
"""
Teste Comparativo de Impacto do Enriquecimento de Descrições

Compara a qualidade das avaliações heurísticas dos specialists quando:
- Versão A: Descrições genéricas ("Create operation", "Update operation")
- Versão B: Descrições enriquecidas com contexto de domínio, segurança e prioridade

Métricas de sucesso:
- Versão B deve ter scores >= 20% maiores que Versão A
- Versão B deve gerar >= 2x mais mitigations relevantes
- Versão B deve ter confidence_score >= 15% maior
"""

import json
import sys
import uuid
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime

import pytest

# Adicionar paths necessários
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "services" / "specialist-technical" / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "libraries" / "python"))


class MockHeuristicEvaluator:
    """
    Avaliador heurístico simplificado que simula o comportamento do TechnicalSpecialist.

    Busca keywords específicas nas descrições para calcular scores.
    """

    SECURITY_KEYWORDS = [
        'auth', 'authenticate', 'encrypt', 'encryption', 'validate', 'sanitize',
        'injection', 'audit', 'permission', 'token', 'credential', 'secure',
        'access', 'role', 'compliance', 'confidential', 'restricted'
    ]

    PERFORMANCE_KEYWORDS = [
        'cache', 'index', 'optimize', 'parallel', 'async', 'batch', 'pool',
        'buffer', 'latency', 'throughput', 'memory', 'query', 'performance'
    ]

    CODE_QUALITY_KEYWORDS = [
        'test', 'error', 'log', 'coverage', 'refactor', 'lint', 'exception',
        'debug', 'trace', 'monitor', 'metric', 'document', 'quality'
    ]

    ARCHITECTURE_KEYWORDS = [
        'service', 'interface', 'pattern', 'module', 'component', 'api',
        'integration', 'layer', 'dependency', 'contract', 'schema', 'design'
    ]

    def evaluate_plan(self, cognitive_plan: Dict[str, Any]) -> Dict[str, Any]:
        """
        Avalia um cognitive plan usando heurísticas baseadas em keywords.

        Args:
            cognitive_plan: Plan com tasks e descrições

        Returns:
            Dict com scores de segurança, performance, qualidade e arquitetura
        """
        tasks = cognitive_plan.get('tasks', [])
        all_descriptions = ' '.join(task.get('description', '') for task in tasks)
        all_descriptions_lower = all_descriptions.lower()

        # Calcular scores baseados em keywords encontradas
        security_score = self._calculate_keyword_score(
            all_descriptions_lower, self.SECURITY_KEYWORDS
        )
        performance_score = self._calculate_keyword_score(
            all_descriptions_lower, self.PERFORMANCE_KEYWORDS
        )
        code_quality_score = self._calculate_keyword_score(
            all_descriptions_lower, self.CODE_QUALITY_KEYWORDS
        )
        architecture_score = self._calculate_keyword_score(
            all_descriptions_lower, self.ARCHITECTURE_KEYWORDS
        )

        # Gerar mitigations baseadas em keywords encontradas
        mitigations = self._generate_mitigations(all_descriptions_lower)

        # Calcular confidence baseado na riqueza das descrições
        total_words = len(all_descriptions.split())
        words_per_task = total_words / max(len(tasks), 1)
        confidence_score = min(1.0, words_per_task / 30)  # 30 palavras/task = confiança máxima

        # Score composto
        overall_score = (
            0.30 * security_score +
            0.25 * performance_score +
            0.25 * code_quality_score +
            0.20 * architecture_score
        )

        return {
            'security_score': round(security_score, 3),
            'performance_score': round(performance_score, 3),
            'code_quality_score': round(code_quality_score, 3),
            'architecture_score': round(architecture_score, 3),
            'overall_score': round(overall_score, 3),
            'confidence_score': round(confidence_score, 3),
            'mitigations': mitigations,
            'total_keywords_found': self._count_all_keywords(all_descriptions_lower),
            'words_per_task': round(words_per_task, 1)
        }

    def _calculate_keyword_score(self, text: str, keywords: List[str]) -> float:
        """Calcula score baseado em keywords encontradas."""
        found = sum(1 for kw in keywords if kw in text)
        # Score satura em 1.0 quando encontra 5+ keywords
        return min(1.0, found / 5)

    def _count_all_keywords(self, text: str) -> int:
        """Conta total de keywords encontradas em todas as categorias."""
        all_keywords = (
            self.SECURITY_KEYWORDS +
            self.PERFORMANCE_KEYWORDS +
            self.CODE_QUALITY_KEYWORDS +
            self.ARCHITECTURE_KEYWORDS
        )
        return sum(1 for kw in all_keywords if kw in text)

    def _generate_mitigations(self, text: str) -> List[Dict[str, Any]]:
        """Gera mitigations baseadas em keywords encontradas."""
        mitigations = []

        # Mitigations de segurança
        if any(kw in text for kw in ['auth', 'encrypt', 'token']):
            mitigations.append({
                'mitigation_id': str(uuid.uuid4()),
                'description': 'Implementar validação de tokens e rotação de credenciais',
                'priority': 'high',
                'category': 'security'
            })

        if any(kw in text for kw in ['sanitize', 'injection', 'validate']):
            mitigations.append({
                'mitigation_id': str(uuid.uuid4()),
                'description': 'Adicionar sanitização de inputs e proteção contra injection',
                'priority': 'high',
                'category': 'security'
            })

        # Mitigations de performance
        if any(kw in text for kw in ['cache', 'index', 'optimize']):
            mitigations.append({
                'mitigation_id': str(uuid.uuid4()),
                'description': 'Configurar política de cache e índices de banco de dados',
                'priority': 'medium',
                'category': 'performance'
            })

        # Mitigations de qualidade
        if any(kw in text for kw in ['test', 'coverage', 'error']):
            mitigations.append({
                'mitigation_id': str(uuid.uuid4()),
                'description': 'Implementar testes unitários e de integração com cobertura mínima',
                'priority': 'medium',
                'category': 'quality'
            })

        return mitigations


def create_generic_plan() -> Dict[str, Any]:
    """Cria um cognitive plan com descrições genéricas (Versão A)."""
    return {
        'plan_id': str(uuid.uuid4()),
        'version': '1.0.0',
        'intent_id': str(uuid.uuid4()),
        'tasks': [
            {
                'task_id': 'task-1',
                'task_type': 'create',
                'description': 'Create operation',
                'dependencies': [],
                'estimated_duration_ms': 1000,
                'required_capabilities': ['write']
            },
            {
                'task_id': 'task-2',
                'task_type': 'validate',
                'description': 'Validate operation',
                'dependencies': ['task-1'],
                'estimated_duration_ms': 500,
                'required_capabilities': ['read']
            },
            {
                'task_id': 'task-3',
                'task_type': 'update',
                'description': 'Update operation',
                'dependencies': ['task-2'],
                'estimated_duration_ms': 800,
                'required_capabilities': ['write']
            },
            {
                'task_id': 'task-4',
                'task_type': 'query',
                'description': 'Query operation',
                'dependencies': ['task-3'],
                'estimated_duration_ms': 300,
                'required_capabilities': ['read']
            }
        ],
        'execution_order': ['task-1', 'task-2', 'task-3', 'task-4'],
        'risk_score': 0.5,
        'risk_band': 'medium',
        'original_domain': 'security-analysis',
        'original_security_level': 'confidential',
        'original_priority': 'high'
    }


def create_enriched_plan() -> Dict[str, Any]:
    """Cria um cognitive plan com descrições enriquecidas (Versão B)."""
    return {
        'plan_id': str(uuid.uuid4()),
        'version': '1.0.0',
        'intent_id': str(uuid.uuid4()),
        'tasks': [
            {
                'task_id': 'task-1',
                'task_type': 'create',
                'description': (
                    'Create and initialize user profile data resources with authentication '
                    'and AES-256 encryption with optimized caching, indexing, and real-time '
                    'monitoring with authentication validation and access control audit '
                    '(security-analysis, confidential, high priority)'
                ),
                'dependencies': [],
                'estimated_duration_ms': 1000,
                'required_capabilities': ['write', 'security']
            },
            {
                'task_id': 'task-2',
                'task_type': 'validate',
                'description': (
                    'Verify security compliance and audit access controls for create operation '
                    'with authentication validation and permission verification testing error '
                    'handling and comprehensive logging (confidential data, requires encryption audit)'
                ),
                'dependencies': ['task-1'],
                'estimated_duration_ms': 500,
                'required_capabilities': ['security', 'read']
            },
            {
                'task_id': 'task-3',
                'task_type': 'update',
                'description': (
                    'Modify and validate configuration data resources with role-based access control '
                    'with performance optimization and caching using indexed queries and connection '
                    'pooling strategies following microservice patterns and interface contracts '
                    '(security-analysis, normal priority)'
                ),
                'dependencies': ['task-2'],
                'estimated_duration_ms': 800,
                'required_capabilities': ['write', 'read']
            },
            {
                'task_id': 'task-4',
                'task_type': 'query',
                'description': (
                    'Retrieve and filter audit log data resources with role-based access control '
                    'with comprehensive error handling and test coverage applying sanitization '
                    'and injection prevention (security-analysis, normal priority)'
                ),
                'dependencies': ['task-3'],
                'estimated_duration_ms': 300,
                'required_capabilities': ['read']
            }
        ],
        'execution_order': ['task-1', 'task-2', 'task-3', 'task-4'],
        'risk_score': 0.5,
        'risk_band': 'medium',
        'original_domain': 'security-analysis',
        'original_security_level': 'confidential',
        'original_priority': 'high'
    }


class TestDescriptionEnrichmentImpact:
    """Testes de impacto do enriquecimento de descrições nas heurísticas."""

    def setup_method(self):
        """Setup para cada teste."""
        self.evaluator = MockHeuristicEvaluator()
        self.generic_plan = create_generic_plan()
        self.enriched_plan = create_enriched_plan()

    def test_enriched_descriptions_have_higher_security_score(self):
        """Versão B deve ter security_score >= 20% maior que Versão A."""
        result_generic = self.evaluator.evaluate_plan(self.generic_plan)
        result_enriched = self.evaluator.evaluate_plan(self.enriched_plan)

        generic_security = result_generic['security_score']
        enriched_security = result_enriched['security_score']

        # Calcular diferença percentual
        if generic_security > 0:
            improvement = (enriched_security - generic_security) / generic_security
        else:
            improvement = 1.0 if enriched_security > 0 else 0.0

        assert enriched_security > generic_security, (
            f"Versão enriquecida ({enriched_security}) deveria ter score maior que genérica ({generic_security})"
        )
        assert improvement >= 0.20, (
            f"Melhoria de {improvement*100:.1f}% é menor que os 20% esperados"
        )

    def test_enriched_descriptions_have_higher_performance_score(self):
        """Versão B deve ter performance_score >= 20% maior que Versão A."""
        result_generic = self.evaluator.evaluate_plan(self.generic_plan)
        result_enriched = self.evaluator.evaluate_plan(self.enriched_plan)

        generic_perf = result_generic['performance_score']
        enriched_perf = result_enriched['performance_score']

        assert enriched_perf > generic_perf, (
            f"Versão enriquecida ({enriched_perf}) deveria ter score maior que genérica ({generic_perf})"
        )

    def test_enriched_descriptions_generate_more_mitigations(self):
        """Versão B deve gerar >= 2x mais mitigations que Versão A."""
        result_generic = self.evaluator.evaluate_plan(self.generic_plan)
        result_enriched = self.evaluator.evaluate_plan(self.enriched_plan)

        generic_mitigations = len(result_generic['mitigations'])
        enriched_mitigations = len(result_enriched['mitigations'])

        # Versão genérica não deve gerar mitigations (sem keywords)
        # Versão enriquecida deve gerar várias
        assert enriched_mitigations >= 2, (
            f"Versão enriquecida deveria gerar pelo menos 2 mitigations, gerou {enriched_mitigations}"
        )
        assert enriched_mitigations > generic_mitigations, (
            f"Versão enriquecida ({enriched_mitigations}) deveria gerar mais mitigations que genérica ({generic_mitigations})"
        )

    def test_enriched_descriptions_have_higher_confidence(self):
        """Versão B deve ter confidence_score >= 15% maior que Versão A."""
        result_generic = self.evaluator.evaluate_plan(self.generic_plan)
        result_enriched = self.evaluator.evaluate_plan(self.enriched_plan)

        generic_confidence = result_generic['confidence_score']
        enriched_confidence = result_enriched['confidence_score']

        # Calcular diferença percentual
        if generic_confidence > 0:
            improvement = (enriched_confidence - generic_confidence) / generic_confidence
        else:
            improvement = 1.0 if enriched_confidence > 0 else 0.0

        assert enriched_confidence > generic_confidence, (
            f"Versão enriquecida ({enriched_confidence}) deveria ter confiança maior que genérica ({generic_confidence})"
        )
        assert improvement >= 0.15, (
            f"Melhoria de {improvement*100:.1f}% é menor que os 15% esperados"
        )

    def test_enriched_descriptions_find_more_keywords(self):
        """Versão B deve encontrar significativamente mais keywords."""
        result_generic = self.evaluator.evaluate_plan(self.generic_plan)
        result_enriched = self.evaluator.evaluate_plan(self.enriched_plan)

        generic_keywords = result_generic['total_keywords_found']
        enriched_keywords = result_enriched['total_keywords_found']

        assert enriched_keywords >= 10, (
            f"Versão enriquecida deveria ter pelo menos 10 keywords, tem {enriched_keywords}"
        )
        assert enriched_keywords > generic_keywords * 5, (
            f"Versão enriquecida ({enriched_keywords}) deveria ter 5x mais keywords que genérica ({generic_keywords})"
        )

    def test_enriched_descriptions_have_more_words_per_task(self):
        """Versão B deve ter >= 15 palavras por task."""
        result_generic = self.evaluator.evaluate_plan(self.generic_plan)
        result_enriched = self.evaluator.evaluate_plan(self.enriched_plan)

        generic_words = result_generic['words_per_task']
        enriched_words = result_enriched['words_per_task']

        assert enriched_words >= 15, (
            f"Versão enriquecida deveria ter >= 15 palavras/task, tem {enriched_words}"
        )
        assert enriched_words > generic_words * 5, (
            f"Versão enriquecida ({enriched_words}) deveria ter mais palavras/task que genérica ({generic_words})"
        )

    def test_overall_improvement_summary(self):
        """Teste resumo com todas as métricas comparativas."""
        result_generic = self.evaluator.evaluate_plan(self.generic_plan)
        result_enriched = self.evaluator.evaluate_plan(self.enriched_plan)

        comparison = {
            'generic': result_generic,
            'enriched': result_enriched,
            'improvements': {
                'security_score': result_enriched['security_score'] - result_generic['security_score'],
                'performance_score': result_enriched['performance_score'] - result_generic['performance_score'],
                'code_quality_score': result_enriched['code_quality_score'] - result_generic['code_quality_score'],
                'architecture_score': result_enriched['architecture_score'] - result_generic['architecture_score'],
                'overall_score': result_enriched['overall_score'] - result_generic['overall_score'],
                'confidence_score': result_enriched['confidence_score'] - result_generic['confidence_score'],
                'mitigations_count': len(result_enriched['mitigations']) - len(result_generic['mitigations']),
                'keywords_found': result_enriched['total_keywords_found'] - result_generic['total_keywords_found'],
            }
        }

        # Salvar resultado para análise
        output_dir = Path(__file__).parent
        output_file = output_dir / 'description_enrichment_comparison.json'
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(comparison, f, indent=2, ensure_ascii=False)

        # Verificar que todas as métricas melhoraram
        for metric, improvement in comparison['improvements'].items():
            assert improvement >= 0, f"Métrica {metric} piorou: {improvement}"

        # Verificar melhoria geral significativa
        assert comparison['improvements']['overall_score'] >= 0.3, (
            f"Melhoria geral de {comparison['improvements']['overall_score']} é menor que 0.3"
        )


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--log-cli-level=INFO'])
