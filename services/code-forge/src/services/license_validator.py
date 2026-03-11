"""
Validação de licenças de software em artefatos gerados.

Este módulo implementa análise de SBOM (Software Bill of Materials)
para detectar licenças problemáticas que possam violar políticas
de compliance da organização.
"""

import json
from datetime import datetime
from typing import Dict, List, Optional, Set
from enum import Enum
import structlog

from ..models.artifact import (
    ValidationResult,
    ValidationType,
    ValidationStatus
)

logger = structlog.get_logger()


class LicenseRisk(str, Enum):
    """Níveis de risco para licenças de software."""
    PERMISSIVE = "permissive"  # MIT, Apache, BSD - baixo risco
    WEAK_COPYLEFT = "weak_copyleft"  # LGPL, MPL - médio risco
    STRONG_COPYLEFT = "strong_copyleft"  # GPL, AGPL - alto risco
    PROHIBITED = "prohibited"  # Licenças explicitamente proibidas


# Lista de licenças por categoria de risco
PERMISSIVE_LICENSES: Set[str] = {
    "MIT",
    "Apache-2.0",
    "Apache License 2.0",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "ISC",
    "Unlicense",
    "0BSD",
    "CC0-1.0",
    "PostgreSQL",
    "Python-2.0",
}

WEAK_COPYLEFT_LICENSES: Set[str] = {
    "LGPL-2.1",
    "LGPL-2.1-ONLY",
    "LGPL-2.1-OR-LATER",
    "LGPL-2.1 ONLY",
    "LGPL-2.1 OR LATER",
    "LGPL-3.0",
    "LGPL-3.0-ONLY",
    "LGPL-3.0-OR-LATER",
    "LGPL-3.0 ONLY",
    "LGPL-3.0 OR LATER",
    "LGPLV2",
    "LGPLV3",
    "MPL-2.0",
    "MPL-2.0-NO-COPYLEFT-EXCEPTION",
    "MOZILLA PUBLIC LICENSE",
    "EPL-1.0",
    "EPL-2.0",
    "ECLIPSE PUBLIC LICENSE",
}

STRONG_COPYLEFT_LICENSES: Set[str] = {
    "GPL-2.0",
    "GPL-2.0-ONLY",
    "GPL-2.0-OR-LATER",
    "GPL-2.0 ONLY",
    "GPL-2.0 OR LATER",
    "GPL-3.0",
    "GPL-3.0-ONLY",
    "GPL-3.0-OR-LATER",
    "GPL-3.0 ONLY",
    "GPL-3.0 OR LATER",
    "GPLV3",
    "GPLV2",
    "AGPL-3.0",
    "AGPL-3.0-ONLY",
    "AGPL-3.0-OR-LATER",
    "AGPL-3.0 ONLY",
    "AGPL-3.0 OR LATER",
    "AGPLV3",
    "SSPL",
    "SERVER SIDE PUBLIC LICENSE",
    "CPAL-1.0",
}

# Licenças explicitamente proibidas (exemplo: licenças com patentes agressivas)
PROHIBITED_LICENSES: Set[str] = {
    "JSON",  # Licença JSON tem cláusula de "boa fé" problemática
    "GPL-1.0",  # Muito antiga, problemas de compatibilidade
}


class LicenseValidator:
    """
    Validador de licenças de software.

    Analisa SBOM (Software Bill of Materials) para identificar licenças
    de código aberto que podem violar políticas de compliance ou criar
    obrigações legais indesejadas.
    """

    def __init__(
        self,
        allowed_licenses: Optional[Set[str]] = None,
        prohibited_licenses: Optional[Set[str]] = None,
        require_sbom: bool = True
    ):
        """
        Inicializa o validador de licenças.

        Args:
            allowed_licenses: Conjunto de licenças explicitamente permitidas
            prohibited_licenses: Conjunto de licenças explicitamente proibidas
            require_sbom: Se True, falha quando SBOM não está disponível
        """
        self.allowed_licenses = allowed_licenses or PERMISSIVE_LICENSES.copy()
        self.prohibited_licenses = prohibited_licenses or PROHIBITED_LICENSES.copy()
        self.require_sbom = require_sbom

    async def validate_licenses(
        self,
        sbom_data: Optional[Dict],
        artifact_id: str,
        ticket_id: str
    ) -> ValidationResult:
        """
        Valida licenças no SBOM de um artefato.

        Args:
            sbom_data: Dados do SBOM (formato SPDX ou CycloneDX)
            artifact_id: ID do artefato sendo validado
            ticket_id: ID do ticket para tracing

        Returns:
            ValidationResult com detalhes das licenças encontradas
        """
        start_time = datetime.now()

        logger.info(
            'license_validation_started',
            artifact_id=artifact_id,
            ticket_id=ticket_id,
            has_sbom=sbom_data is not None
        )

        if not sbom_data:
            if self.require_sbom:
                logger.warning(
                    'sbom_not_required_but_missing',
                    artifact_id=artifact_id,
                    ticket_id=ticket_id
                )
                return ValidationResult(
                    validation_type=ValidationType.LICENSE_CHECK,
                    tool_name='license-validator',
                    tool_version='1.0.0',
                    status=ValidationStatus.WARNING,
                    score=0.5,
                    issues_count=1,
                    critical_issues=0,
                    high_issues=1,
                    medium_issues=0,
                    low_issues=0,
                    executed_at=start_time,
                    duration_ms=0,
                    report_uri=None,
                    metadata={
                        'message': 'SBOM não disponível para validação de licenças',
                        'licenses_found': []
                    }
                )
            else:
                # SBOM opcional não disponível - retorna WARNING
                return ValidationResult(
                    validation_type=ValidationType.LICENSE_CHECK,
                    tool_name='license-validator',
                    tool_version='1.0.0',
                    status=ValidationStatus.WARNING,
                    score=0.7,
                    issues_count=0,
                    critical_issues=0,
                    high_issues=0,
                    medium_issues=1,
                    low_issues=0,
                    executed_at=start_time,
                    duration_ms=0,
                    report_uri=None,
                    metadata={
                        'message': 'SBOM não disponível (validação opcional)',
                        'licenses_found': []
                    }
                )

        # Detectar formato do SBOM (SPDX ou CycloneDX)
        sbom_format = self._detect_sbom_format(sbom_data)
        logger.debug('sbom_format_detected', format=sbom_format)

        # Extrair licenças baseado no formato
        if sbom_format == 'spdx':
            licenses = self._extract_licenses_spdx(sbom_data)
        elif sbom_format == 'cyclonedx':
            licenses = self._extract_licenses_cyclonedx(sbom_data)
        else:
            licenses = self._extract_licenses_generic(sbom_data)

        logger.info(
            'licenses_extracted',
            artifact_id=artifact_id,
            count=len(licenses),
            licenses=list(licenses)[:10]  # Log primeiras 10
        )

        # Classificar licenças por risco
        license_analysis = self._classify_licenses(licenses)

        # Calcular score baseado na análise
        score, issues = self._calculate_score(license_analysis)

        duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)

        # Determinar status baseado nas licenças problemáticas
        if license_analysis['prohibited']:
            status = ValidationStatus.FAILED
        elif license_analysis['strong_copyleft']:
            status = ValidationStatus.FAILED
        elif license_analysis['weak_copyleft']:
            status = ValidationStatus.WARNING
        else:
            status = ValidationStatus.PASSED

        result = ValidationResult(
            validation_type=ValidationType.LICENSE_CHECK,
            tool_name='license-validator',
            tool_version='1.0.0',
            status=status,
            score=score,
            issues_count=issues,
            critical_issues=len(license_analysis['prohibited']),
            high_issues=len(license_analysis['strong_copyleft']),
            medium_issues=len(license_analysis['weak_copyleft']),
            low_issues=0,
            executed_at=start_time,
            duration_ms=duration_ms,
            report_uri=None,
            metadata={
                'sbom_format': sbom_format,
                'licenses_found': list(licenses),
                'license_analysis': license_analysis,
                'total_components': sbom_data.get('count', 0) if sbom_data else 0
            }
        )

        logger.info(
            'license_validation_completed',
            artifact_id=artifact_id,
            ticket_id=ticket_id,
            status=status,
            score=score,
            issues=issues
        )

        return result

    def _detect_sbom_format(self, sbom_data: Dict) -> str:
        """Detecta o formato do SBOM (SPDX, CycloneDX ou genérico)."""
        if not sbom_data:
            return 'unknown'

        # SPDX tem campos específicos
        if 'spdxVersion' in sbom_data or 'spdxVersion' in str(sbom_data.get('$schema', '')):
            return 'spdx'

        # CycloneDX tem campo bomFormat
        if 'bomFormat' in sbom_data or 'component' in sbom_data:
            return 'cyclonedx'

        return 'generic'

    def _extract_licenses_spdx(self, sbom_data: Dict) -> Set[str]:
        """Extrai licenças de um SBOM no formato SPDX."""
        licenses = set()

        # SPDX packages têm declaredLicense
        packages = sbom_data.get('packages', [])
        for package in packages:
            license_data = package.get('licenseDeclared', {})
            if isinstance(license_data, dict):
                license_id = license_data.get('licenseId')
                if license_id and license_id != 'NOASSERTION':
                    licenses.add(license_id)
            elif isinstance(license_data, str):
                if license_data != 'NOASSERTION':
                    licenses.add(license_data)

            # Verificar extractedTexts
            extracted_text = package.get('extractedText', '')
            if extracted_text and 'license' in extracted_text.lower():
                # Tentar extrair nome da licença do texto
                for lic in PERMISSIVE_LICENSES | WEAK_COPYLEFT_LICENSES | STRONG_COPYLEFT_LICENSES:
                    if lic.lower() in extracted_text.lower():
                        licenses.add(lic)

        return licenses

    def _extract_licenses_cyclonedx(self, sbom_data: Dict) -> Set[str]:
        """Extrai licenças de um SBOM no formato CycloneDX."""
        licenses = set()

        # CycloneDX components têm licenses
        components = sbom_data.get('components', [])
        for component in components:
            licenses_data = component.get('licenses', [])
            for lic in licenses_data:
                if isinstance(lic, dict):
                    # Pode ter id ou expression
                    license_id = lic.get('id') or lic.get('expression')
                    if license_id and license_id != 'NOASSERTION':
                        licenses.add(license_id)

        # Verificar metadata também
        metadata = sbom_data.get('metadata', {})
        component_metadata = metadata.get('component', {})
        if component_metadata:
            licenses_data = component_metadata.get('licenses', [])
            for lic in licenses_data:
                if isinstance(lic, dict):
                    license_id = lic.get('id') or lic.get('expression')
                    if license_id:
                        licenses.add(license_id)

        return licenses

    def _extract_licenses_generic(self, sbom_data: Dict) -> Set[str]:
        """Extrai licenças de formato genérico/unknown."""
        licenses = set()

        # Tentar encontrar campos comuns
        for key in ['licenses', 'license', 'licenseId', 'licenseID']:
            if key in sbom_data:
                value = sbom_data[key]
                if isinstance(value, list):
                    for lic in value:
                        if isinstance(lic, dict):
                            lic_id = lic.get('id', lic.get('name', ''))
                            if lic_id:
                                licenses.add(lic_id)
                        elif isinstance(lic, str):
                            licenses.add(lic)
                elif isinstance(value, str):
                    licenses.add(value)
                elif isinstance(value, dict):
                    lic_id = value.get('id', value.get('name', ''))
                    if lic_id:
                        licenses.add(lic_id)

        # Buscar recursivamente em components/packages
        for key in ['components', 'packages', 'dependencies']:
            if key in sbom_data:
                items = sbom_data[key]
                if isinstance(items, list):
                    for item in items:
                        licenses.update(self._extract_licenses_generic(item))

        return licenses

    def _classify_licenses(self, licenses: Set[str]) -> Dict[str, List[str]]:
        """Classifica licenças por categoria de risco."""
        analysis = {
            'permissive': [],
            'weak_copyleft': [],
            'strong_copyleft': [],
            'prohibited': [],
            'unknown': []
        }

        for lic in licenses:
            lic_normalized = self._normalize_license_name(lic)

            if lic_normalized in PROHIBITED_LICENSES or lic in self.prohibited_licenses:
                analysis['prohibited'].append(lic)
            elif lic_normalized in STRONG_COPYLEFT_LICENSES:
                analysis['strong_copyleft'].append(lic)
            elif lic_normalized in WEAK_COPYLEFT_LICENSES:
                analysis['weak_copyleft'].append(lic)
            elif lic_normalized in PERMISSIVE_LICENSES or lic in self.allowed_licenses:
                analysis['permissive'].append(lic)
            else:
                analysis['unknown'].append(lic)

        return analysis

    def _normalize_license_name(self, license_name: str) -> str:
        """Normaliza nome da licença para comparação."""
        # Remover espaços e converter para maiúsculas
        normalized = license_name.strip().upper()

        # Remover sufixos comuns
        for suffix in ['-ONLY', '-OR-LATER', '+', ' WITH EXCEPTIONS']:
            if normalized.endswith(suffix):
                normalized = normalized[:-len(suffix)]

        # Mapear variações comuns
        mappings = {
            'APACHE LICENSE 2.0': 'APACHE-2.0',
            'APACHE 2.0': 'APACHE-2.0',
            'BSD 2-CLAUSE': 'BSD-2-CLAUSE',
            'BSD 3-CLAUSE': 'BSD-3-CLAUSE',
            'LESSER GPL V2': 'LGPL-2.1',
            'LESSER GPL V3': 'LGPL-3.0',
            'LESSER GENERAL PUBLIC LICENSE V2': 'LGPL-2.1',
            'LESSER GENERAL PUBLIC LICENSE V3': 'LGPL-3.0',
            'GNU LESSER GENERAL PUBLIC LICENSE V2': 'LGPL-2.1',
            'GNU LESSER GENERAL PUBLIC LICENSE V3': 'LGPL-3.0',
            'GPL V2': 'GPL-2.0',
            'GPL V3': 'GPL-3.0',
            'GNU GENERAL PUBLIC LICENSE V2': 'GPL-2.0',
            'GNU GENERAL PUBLIC LICENSE V3': 'GPL-3.0',
            'AFFERO GPL': 'AGPL-3.0',
            'GNU AFFERO GENERAL PUBLIC LICENSE': 'AGPL-3.0',
        }

        return mappings.get(normalized, normalized)

    def _calculate_score(self, analysis: Dict[str, List[str]]) -> tuple[float, int]:
        """
        Calcula score baseado na análise de licenças.

        Returns:
            Tupla (score, issues_count)
        """
        prohibited_count = len(analysis['prohibited'])
        strong_copyleft_count = len(analysis['strong_copyleft'])
        weak_copyleft_count = len(analysis['weak_copyleft'])
        permissive_count = len(analysis['permissive'])
        unknown_count = len(analysis['unknown'])

        # Base score é 1.0 (todas permissivas)
        score = 1.0
        issues = 0

        # Licenças proibidas = falha crítica
        if prohibited_count > 0:
            score -= 0.7
            issues += prohibited_count

        # Strong copyleft = impacto significativo
        if strong_copyleft_count > 0:
            score -= 0.2 * strong_copyleft_count
            issues += strong_copyleft_count

        # Weak copyleft = impacto moderado
        if weak_copyleft_count > 0:
            score -= 0.1 * weak_copyleft_count
            issues += weak_copyleft_count

        # Unknown = reduz confiança
        if unknown_count > 0:
            score -= 0.05 * unknown_count
            issues += unknown_count

        # Garantir score mínimo de 0
        score = max(0.0, score)

        return score, issues

    def get_license_policy(self) -> Dict:
        """Retorna a política de licenças configurada."""
        return {
            'allowed_licenses': list(self.allowed_licenses),
            'prohibited_licenses': list(self.prohibited_licenses),
            'require_sbom': self.require_sbom
        }
