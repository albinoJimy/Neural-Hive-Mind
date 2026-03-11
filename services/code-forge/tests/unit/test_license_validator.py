"""
Testes unitarios para LicenseValidator.

Cobertura:
- Validacao de licencas em SBOM SPDX
- Validacao de licencas em SBOM CycloneDX
- Classificacao de licencas por risco
- Score calculation
- Tratamento de SBOM ausente
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock

from src.services.license_validator import (
    LicenseValidator,
    LicenseRisk,
    PERMISSIVE_LICENSES,
    WEAK_COPYLEFT_LICENSES,
    STRONG_COPYLEFT_LICENSES,
    PROHIBITED_LICENSES
)
from src.models.artifact import ValidationType, ValidationStatus


class TestLicenseValidatorSPDX:
    """Testes de validacao de licencas em formato SPDX."""

    @pytest.mark.asyncio
    async def test_validate_spdx_permissive_licenses(self):
        """Deve aceitar licencas permissivas em SPDX."""
        validator = LicenseValidator(require_sbom=False)

        sbom_data = {
            'spdxVersion': 'SPDX-2.3',
            'packages': [
                {
                    'SPDXID': 'pkg-1',
                    'licenseDeclared': {
                        'licenseId': 'MIT'
                    }
                },
                {
                    'SPDXID': 'pkg-2',
                    'licenseDeclared': {
                        'licenseId': 'Apache-2.0'
                    }
                }
            ]
        }

        result = await validator.validate_licenses(
            sbom_data=sbom_data,
            artifact_id='test-artifact-1',
            ticket_id='test-ticket-1'
        )

        assert result.validation_type == ValidationType.LICENSE_CHECK
        assert result.status == ValidationStatus.PASSED
        assert result.score == 1.0
        assert result.critical_issues == 0
        assert result.high_issues == 0

    @pytest.mark.asyncio
    async def test_validate_spdx_gpl_license(self):
        """Deve falhar para licencas GPL (strong copyleft)."""
        validator = LicenseValidator(require_sbom=False)

        sbom_data = {
            'spdxVersion': 'SPDX-2.3',
            'packages': [
                {
                    'SPDXID': 'pkg-1',
                    'licenseDeclared': {
                        'licenseId': 'GPL-3.0-only'
                    }
                }
            ]
        }

        result = await validator.validate_licenses(
            sbom_data=sbom_data,
            artifact_id='test-artifact-1',
            ticket_id='test-ticket-1'
        )

        assert result.status == ValidationStatus.FAILED
        assert result.score <= 0.8  # Reduzido por strong copyleft
        assert result.high_issues >= 1  # Classificado como high issue
        assert result.metadata['license_analysis']['strong_copyleft']

    @pytest.mark.asyncio
    async def test_validate_spdx_mixed_licenses(self):
        """Deve classificar corretamente licencas mistas."""
        validator = LicenseValidator(require_sbom=False)

        sbom_data = {
            'spdxVersion': 'SPDX-2.3',
            'packages': [
                {'SPDXID': 'pkg-1', 'licenseDeclared': {'licenseId': 'MIT'}},
                {'SPDXID': 'pkg-2', 'licenseDeclared': {'licenseId': 'LGPL-3.0-only'}},
                {'SPDXID': 'pkg-3', 'licenseDeclared': {'licenseId': 'BSD-3-Clause'}}
            ]
        }

        result = await validator.validate_licenses(
            sbom_data=sbom_data,
            artifact_id='test-artifact-1',
            ticket_id='test-ticket-1'
        )

        assert result.status == ValidationStatus.WARNING  # Weak copyleft
        assert result.medium_issues >= 1  # Weak copyleft vira medium issue
        assert len(result.metadata['license_analysis']['permissive']) >= 1
        assert len(result.metadata['license_analysis']['weak_copyleft']) >= 1


class TestLicenseValidatorCycloneDX:
    """Testes de validacao de licencas em formato CycloneDX."""

    @pytest.mark.asyncio
    async def test_validate_cyclonedx_permissive(self):
        """Deve aceitar licencas permissivas em CycloneDX."""
        validator = LicenseValidator(require_sbom=False)

        sbom_data = {
            'bomFormat': 'CycloneDX',
            'components': [
                {
                    'name': 'library1',
                    'licenses': [{'id': 'Apache-2.0'}]
                },
                {
                    'name': 'library2',
                    'licenses': [{'id': 'ISC'}]
                }
            ]
        }

        result = await validator.validate_licenses(
            sbom_data=sbom_data,
            artifact_id='test-artifact-1',
            ticket_id='test-ticket-1'
        )

        assert result.status == ValidationStatus.PASSED
        assert result.score == 1.0

    @pytest.mark.asyncio
    async def test_validate_cyclonedx_agpl(self):
        """Deve falhar para licenca AGPL."""
        validator = LicenseValidator(require_sbom=False)

        sbom_data = {
            'bomFormat': 'CycloneDX',
            'components': [
                {
                    'name': 'agpl-lib',
                    'licenses': [{'id': 'AGPL-3.0-only'}]
                }
            ]
        }

        result = await validator.validate_licenses(
            sbom_data=sbom_data,
            artifact_id='test-artifact-1',
            ticket_id='test-ticket-1'
        )

        assert result.status == ValidationStatus.FAILED
        assert result.high_issues >= 1  # AGPL é strong copyleft (classificado como high)


class TestLicenseValidatorMissingSBOM:
    """Testes de tratamento de SBOM ausente."""

    @pytest.mark.asyncio
    async def test_no_sbom_require_true(self):
        """Deve retornar WARNING quando SBOM obrigatorio ausente."""
        validator = LicenseValidator(require_sbom=True)

        result = await validator.validate_licenses(
            sbom_data=None,
            artifact_id='test-artifact-1',
            ticket_id='test-ticket-1'
        )

        assert result.status == ValidationStatus.WARNING
        assert result.high_issues >= 1  # Issue alto quando SBOM obrigatorio falta
        assert 'SBOM não disponível' in result.metadata.get('message', '')

    @pytest.mark.asyncio
    async def test_no_sbom_require_false(self):
        """Deve retornar WARNING quando SBOM opcional ausente."""
        validator = LicenseValidator(require_sbom=False)

        result = await validator.validate_licenses(
            sbom_data=None,
            artifact_id='test-artifact-1',
            ticket_id='test-ticket-1'
        )

        assert result.status == ValidationStatus.WARNING
        assert result.high_issues == 0  # Não é issue alto quando opcional
        assert result.medium_issues >= 1  # Issue médio quando opcional
        assert 'opcional' in result.metadata.get('message', '')


class TestLicenseValidatorRiskClassification:
    """Testes de classificacao de risco de licencas."""

    @pytest.mark.asyncio
    async def test_classify_permissive_licenses(self):
        """Deve classificar licencas permissivas corretamente."""
        validator = LicenseValidator()

        for lic in PERMISSIVE_LICENSES:
            analysis = validator._classify_licenses({lic})
            assert lic in analysis['permissive'] or lic.lower() in [l.lower() for l in analysis['permissive']]
            assert not analysis['prohibited']
            assert not analysis['strong_copyleft']

    @pytest.mark.asyncio
    async def test_classify_weak_copyleft(self):
        """Deve classificar weak copyleft corretamente."""
        validator = LicenseValidator()

        for lic in ['LGPL-3.0', 'MPL-2.0', 'EPL-2.0']:
            analysis = validator._classify_licenses({lic})
            assert lic in analysis['weak_copyleft'] or any(lic in l for l in analysis['weak_copyleft'])

    @pytest.mark.asyncio
    async def test_classify_strong_copyleft(self):
        """Deve classificar strong copyleft corretamente."""
        validator = LicenseValidator()

        for lic in ['GPL-3.0', 'AGPL-3.0', 'SSPL']:
            analysis = validator._classify_licenses({lic})
            assert lic in analysis['strong_copyleft'] or any(lic in l for l in analysis['strong_copyleft'])

    @pytest.mark.asyncio
    async def test_classify_unknown_license(self):
        """Deve classificar licencas desconhecidas."""
        validator = LicenseValidator()

        analysis = validator._classify_licenses({'CustomLicense-1.0'})
        assert 'CustomLicense-1.0' in analysis['unknown']


class TestLicenseValidatorScoreCalculation:
    """Testes de calculo de score."""

    @pytest.mark.asyncio
    async def test_score_all_permissive(self):
        """Score maximo para todas permissivas."""
        validator = LicenseValidator()

        score, issues = validator._calculate_score({
            'permissive': ['MIT', 'Apache-2.0'],
            'weak_copyleft': [],
            'strong_copyleft': [],
            'prohibited': [],
            'unknown': []
        })

        assert score == 1.0
        assert issues == 0

    @pytest.mark.asyncio
    async def test_score_with_gpl(self):
        """Score reduzido com GPL."""
        validator = LicenseValidator()

        score, issues = validator._calculate_score({
            'permissive': ['MIT'],
            'weak_copyleft': [],
            'strong_copyleft': ['GPL-3.0-only'],
            'prohibited': [],
            'unknown': []
        })

        assert score <= 0.8  # 1.0 - 0.2 = 0.8
        assert issues >= 1

    @pytest.mark.asyncio
    async def test_score_with_prohibited(self):
        """Score muito baixo com licencas proibidas."""
        validator = LicenseValidator()

        score, issues = validator._calculate_score({
            'permissive': [],
            'weak_copyleft': [],
            'strong_copyleft': [],
            'prohibited': ['JSON'],
            'unknown': []
        })

        assert score < 0.4  # 1.0 - 0.7 = 0.3
        assert issues > 0

    @pytest.mark.asyncio
    async def test_score_minimum_zero(self):
        """Score nunca deve ser negativo."""
        validator = LicenseValidator()

        score, issues = validator._calculate_score({
            'permissive': [],
            'weak_copyleft': [],
            'strong_copyleft': ['GPL-3.0', 'AGPL-3.0', 'SSPL'],
            'prohibited': ['JSON', 'GPL-1.0'],
            'unknown': ['Unknown-1', 'Unknown-2']
        })

        assert score >= 0.0


class TestLicenseValidatorLicenseNormalization:
    """Testes de normalizacao de nomes de licenca."""

    @pytest.mark.asyncio
    async def test_normalize_apache_variations(self):
        """Deve normalizar variacoes de Apache."""
        validator = LicenseValidator()

        normalized1 = validator._normalize_license_name('Apache License 2.0')
        assert 'APACHE-2.0' in normalized1 or normalized1 == 'APACHE-2.0'

        normalized2 = validator._normalize_license_name('Apache 2.0')
        assert 'APACHE-2.0' in normalized2 or normalized2 == 'APACHE-2.0'

        normalized3 = validator._normalize_license_name('Apache-2.0')
        assert normalized3 == 'APACHE-2.0' or 'APACHE-2.0' in normalized3

    @pytest.mark.asyncio
    async def test_normalize_gpl_variations(self):
        """Deve normalizar variacoes de GPL."""
        validator = LicenseValidator()

        normalized1 = validator._normalize_license_name('GPL v3')
        # Deve retornar algo que contenha 'GPL' e '3'
        assert 'GPL' in normalized1 and '3' in normalized1

        normalized2 = validator._normalize_license_name('GNU GPL v3.0')
        # Deve retornar algo que contenha 'GPL' e '3'
        assert 'GPL' in normalized2 and '3' in normalized2


class TestLicenseValidatorPolicy:
    """Testes de politica de licencas configuravel."""

    @pytest.mark.asyncio
    async def test_custom_allowed_licenses(self):
        """Deve aceitar licencas customizadas permitidas."""
        custom_allowed = {'MIT', 'Apache-2.0', 'Custom-Permissive'}

        validator = LicenseValidator(allowed_licenses=custom_allowed)

        sbom_data = {
            'spdxVersion': 'SPDX-2.3',
            'packages': [
                {'SPDXID': 'pkg-1', 'licenseDeclared': {'licenseId': 'Custom-Permissive'}},
                {'SPDXID': 'pkg-2', 'licenseDeclared': {'licenseId': 'MIT'}}
            ]
        }

        result = await validator.validate_licenses(
            sbom_data=sbom_data,
            artifact_id='test-1',
            ticket_id='ticket-1'
        )

        assert result.status == ValidationStatus.PASSED

    @pytest.mark.asyncio
    async def test_custom_prohibited_licenses(self):
        """Deve bloquear licencas customizadas proibidas."""
        # Usar formato exato que aparece no SBOM (case-sensitive)
        custom_prohibited = {'CUSTOM-BAD-LICENSE'}

        validator = LicenseValidator(prohibited_licenses=custom_prohibited)

        # Usar formato SPDX correto com spdxVersion
        sbom_data = {
            'spdxVersion': 'SPDX-2.3',
            'packages': [
                {'SPDXID': 'pkg-1', 'licenseDeclared': {'licenseId': 'CUSTOM-BAD-LICENSE'}}
            ]
        }

        result = await validator.validate_licenses(
            sbom_data=sbom_data,
            artifact_id='test-1',
            ticket_id='ticket-1'
        )

        # A licença customizada está na lista de proibidas
        # Vai ser classificada como prohibited → critical_issues
        assert result.critical_issues > 0
        # Status deve ser FAILED
        assert result.status == ValidationStatus.FAILED

    @pytest.mark.asyncio
    async def test_get_license_policy(self):
        """Deve retornar politica configurada."""
        custom_allowed = {'MIT', 'Apache-2.0'}
        custom_prohibited = {'GPL-3.0-only'}

        validator = LicenseValidator(
            allowed_licenses=custom_allowed,
            prohibited_licenses=custom_prohibited,
            require_sbom=True
        )

        policy = validator.get_license_policy()

        assert 'MIT' in policy['allowed_licenses']
        assert 'Apache-2.0' in policy['allowed_licenses']
        assert 'GPL-3.0-only' in policy['prohibited_licenses']
        assert policy['require_sbom'] is True
