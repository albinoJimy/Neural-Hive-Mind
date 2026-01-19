"""
Destructive Operation Detector

Detects destructive operations in task lists through pattern matching
on task types and keyword detection in descriptions.
"""

import structlog
from typing import Dict, List, Any, Optional

from src.config.settings import Settings
from src.models.cognitive_plan import TaskNode
from src.observability.metrics import (
    destructive_operations_detected_total,
    destructive_tasks_per_plan
)

logger = structlog.get_logger()


class DestructiveDetector:
    """
    Detects destructive operations in cognitive plan tasks.

    Uses pattern matching on task types and keyword detection
    in descriptions to identify potentially dangerous operations.
    Supports multilingual detection (Portuguese and English).
    """

    # Destructive task types
    DESTRUCTIVE_TASK_TYPES = ['delete', 'drop', 'truncate', 'remove', 'purge']

    # Destructive keywords in Portuguese
    DESTRUCTIVE_KEYWORDS_PT = [
        'deletar', 'remover', 'apagar', 'limpar', 'excluir', 'destruir', 'eliminar'
    ]

    # Destructive keywords in English
    DESTRUCTIVE_KEYWORDS_EN = [
        'delete', 'remove', 'drop', 'truncate', 'purge', 'destroy', 'erase', 'wipe'
    ]

    # High impact indicators (trigger critical severity)
    HIGH_IMPACT_INDICATORS = [
        'all', 'todos', 'entire', 'complete', 'production', 'produção', 'prod'
    ]

    def __init__(self, settings: Settings):
        """
        Initialize the DestructiveDetector.

        Args:
            settings: Application settings
        """
        self.settings = settings
        self.logger = structlog.get_logger().bind(component='destructive_detector')

    def detect(self, tasks: List[TaskNode]) -> Dict[str, Any]:
        """
        Detecta operações destrutivas em lista de tasks.

        Analisa cada task verificando:
        1. Tipo de task (delete, drop, truncate, etc.)
        2. Keywords destrutivas na descrição (multilíngue)
        3. Indicadores de alto impacto (all, production, etc.)

        Args:
            tasks: Lista de TaskNode a analisar

        Returns:
            Dicionário com:
            - is_destructive (bool): Se alguma operação destrutiva foi detectada
            - destructive_tasks (List[str]): IDs das tasks destrutivas
            - severity (str): Nível de severidade (low/medium/high/critical)
            - total_destructive_count (int): Contagem total
            - details (List[Dict]): Detalhes de cada detecção

        Example:
            >>> detector = DestructiveDetector(settings)
            >>> result = detector.detect(tasks)
            >>> if result['is_destructive']:
            ...     print(f"Severidade: {result['severity']}")
        """
        # Early return when detection is disabled - no metrics recorded
        if not self.settings.destructive_detection_enabled:
            self.logger.debug(
                'Detecção de operações destrutivas desabilitada',
                num_tasks=len(tasks)
            )
            return {
                'is_destructive': False,
                'destructive_tasks': [],
                'severity': 'low',
                'total_destructive_count': 0,
                'details': []
            }

        self.logger.info('Iniciando detecção de operações destrutivas', num_tasks=len(tasks))

        details: List[Dict[str, Any]] = []
        destructive_task_ids: List[str] = []

        for task in tasks:
            analysis = self._analyze_task(task)
            if analysis:
                details.append(analysis)
                destructive_task_ids.append(analysis['task_id'])
                self.logger.warning(
                    'Operação destrutiva detectada',
                    task_id=analysis['task_id'],
                    task_type=analysis['task_type'],
                    reason=analysis['reason'],
                    matched_keywords=analysis['matched_keywords']
                )

        is_destructive = len(details) > 0
        severity = self._calculate_severity(details) if is_destructive else 'low'

        result = {
            'is_destructive': is_destructive,
            'destructive_tasks': destructive_task_ids,
            'severity': severity,
            'total_destructive_count': len(details),
            'details': details
        }

        # Record metrics
        if is_destructive:
            for detail in details:
                destructive_operations_detected_total.labels(
                    severity=severity,
                    detection_type=detail['reason']
                ).inc()

        destructive_tasks_per_plan.observe(len(details))

        self.logger.info(
            'Detecção concluída',
            is_destructive=is_destructive,
            total_count=len(details),
            severity=severity
        )

        return result

    def _analyze_task(self, task: TaskNode) -> Optional[Dict[str, Any]]:
        """
        Analyze a single task for destructive patterns.

        In strict mode (destructive_detection_strict_mode=True), tasks with
        HIGH_IMPACT_INDICATORS are flagged as destructive even without
        explicit destructive keywords or task types.

        Args:
            task: TaskNode to analyze

        Returns:
            Dict with analysis results if destructive, None otherwise
        """
        task_type_lower = task.task_type.lower() if task.task_type else ''
        description_lower = task.description.lower() if task.description else ''

        matched_keywords: List[str] = []
        reason: Optional[str] = None

        # Check task type
        if task_type_lower in self.DESTRUCTIVE_TASK_TYPES:
            reason = 'task_type_match'
            matched_keywords.append(task_type_lower)

        # Check keywords in description (Portuguese)
        for keyword in self.DESTRUCTIVE_KEYWORDS_PT:
            if keyword in description_lower:
                if not reason:
                    reason = 'keyword_match'
                if keyword not in matched_keywords:
                    matched_keywords.append(keyword)

        # Check keywords in description (English)
        for keyword in self.DESTRUCTIVE_KEYWORDS_EN:
            if keyword in description_lower:
                if not reason:
                    reason = 'keyword_match'
                if keyword not in matched_keywords:
                    matched_keywords.append(keyword)

        # Check for high impact indicators
        matched_indicators: List[str] = []
        for indicator in self.HIGH_IMPACT_INDICATORS:
            if indicator in description_lower:
                matched_indicators.append(indicator)

        has_high_impact = len(matched_indicators) > 0

        # Strict mode: HIGH_IMPACT_INDICATORS alone trigger detection
        if self.settings.destructive_detection_strict_mode and has_high_impact and not reason:
            reason = 'high_impact_indicator_strict'
            matched_keywords.extend(matched_indicators)

        if not reason:
            return None

        return {
            'task_id': task.task_id,
            'task_type': task.task_type,
            'reason': reason,
            'matched_keywords': matched_keywords,
            'has_high_impact_indicators': has_high_impact
        }

    def _calculate_severity(self, destructive_tasks: List[Dict]) -> str:
        """
        Calculate aggregate severity based on destructive tasks.

        Severity levels:
        - critical: >= 5 tasks OR high impact indicators present
        - high: 3-4 tasks OR drop/truncate task type
        - medium: 2 tasks
        - low: 1 task

        Args:
            destructive_tasks: List of destructive task analysis dicts

        Returns:
            Severity level string: 'low', 'medium', 'high', or 'critical'
        """
        count = len(destructive_tasks)

        # Check for high impact indicators
        has_high_impact = any(
            task.get('has_high_impact_indicators', False)
            for task in destructive_tasks
        )

        # Check for drop/truncate operations
        has_drop_truncate = any(
            task.get('task_type', '').lower() in ['drop', 'truncate']
            for task in destructive_tasks
        )

        # Determine severity
        if count >= 5 or has_high_impact:
            severity = 'critical'
        elif count >= 3 or has_drop_truncate:
            severity = 'high'
        elif count == 2:
            severity = 'medium'
        else:
            severity = 'low'

        self.logger.info(
            'Severidade calculada',
            severity=severity,
            count=count,
            has_high_impact=has_high_impact,
            has_drop_truncate=has_drop_truncate
        )

        return severity
