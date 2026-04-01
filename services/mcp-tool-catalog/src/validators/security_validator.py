"""
Validador de segurança para ferramentas MCP.

Detecta riscos de segurança em schemas e metadados de ferramentas.
"""

import re
from enum import Enum
from typing import Any, Dict, List, Optional, Set

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)


class RiskLevel(str, Enum):
    """Níveis de risco de segurança."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class SecurityRisk(BaseModel):
    """Risco de segurança detectado."""

    risk_type: str = Field(..., description="Tipo de risco")
    level: RiskLevel = Field(..., description="Nível de severidade")
    message: str = Field(..., description="Mensagem descritiva")
    affected_field: Optional[str] = Field(default=None, description="Campo afetado")
    recommendation: Optional[str] = Field(default=None, description="Recomendação de mitigação")
    cwe_ref: Optional[str] = Field(default=None, description="Referência CWE se aplicável")


class SecurityValidationResult(BaseModel):
    """Resultado da validação de segurança."""

    is_safe: bool = Field(..., description="Se a ferramenta é considerada segura")
    risk_count: int = Field(..., description="Total de riscos encontrados")
    risks_by_level: Dict[str, int] = Field(default_factory=dict, description="Contagem por nível")
    risks: List[SecurityRisk] = Field(default_factory=list, description="Lista de riscos")
    requires_approval: bool = Field(default=False, description="Se requer aprovação humana")
    allowed_contexts: List[str] = Field(
        default_factory=list, description="Contextos onde a ferramenta pode ser usada"
    )


class SecurityValidator:
    """
    Validador de segurança para ferramentas MCP.

    Detecta riscos como:
    - Injection (SQL, Command, LDAP, XPath)
    - Path Traversal
    - SSRF
    - XSS
    - Divulgação de dados sensíveis
    - Operações destrutivas
    """

    # Padrões de risco para detecção
    INJECTION_PATTERNS = {
        "sql": re.compile(
            r"(?i)(select|insert|update|delete|drop|create|alter|exec|execute)\s+.+(from|into|table)",
            re.IGNORECASE,
        ),
        "command": re.compile(r"[;&|`$()]", re.IGNORECASE),
        "ldap": re.compile(r"[\(\)&\|=!\*<>]", re.IGNORECASE),
        "xpath": re.compile(r"[\'\"\(\)\@]", re.IGNORECASE),
    }

    # Palavras-chave que indicam operações perigosas
    DANGEROUS_KEYWORDS: Set[str] = {
        "delete",
        "remove",
        "destroy",
        "drop",
        "truncate",
        "format",
        "fdisk",
        "mkfs",
        "rm",
        "rmdir",
        "exec",
        "eval",
        "system",
        "spawn",
        "shell",
        "su",
        "sudo",
        "chmod",
        "chown",
        "wget",
        "curl",
        "nc",
        "netcat",
        "telnet",
        "password",
        "secret",
        "token",
        "key",
        "credential",
        "ssn",
        "credit_card",
        "pin",
        "private_key",
    }

    # Nomes de parâmetros suspeitos
    SUSPICIOUS_PARAMS: Set[str] = {
        "url",
        "uri",
        "endpoint",
        "host",
        "ip",
        "address",
        "file",
        "path",
        "filename",
        "directory",
        "folder",
        "command",
        "cmd",
        "exec",
        "query",
        "sql",
        "redirect",
        "callback",
        "return_url",
        "next",
    }

    # Tipos MIME perigosos
    DANGEROUS_MIME_TYPES: Set[str] = {
        "application/x-executable",
        "application/x-sh",
        "application/x-bat",
        "application/vnd.microsoft.portable-executable",
    }

    def __init__(
        self, strict_mode: bool = False, allow_network: bool = False, allow_filesystem: bool = False
    ):
        """
        Inicializa validador de segurança.

        Args:
            strict_mode: Se True, trata MEDIUM como erro
            allow_network: Se True, permite operações de rede
            allow_filesystem: Se True, permite operações de filesystem
        """
        self.strict_mode = strict_mode
        self.allow_network = allow_network
        self.allow_filesystem = allow_filesystem

    def validate_tool(
        self,
        tool_name: str,
        description: str,
        input_schema: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SecurityValidationResult:
        """
        Valida segurança completa de ferramenta.

        Args:
            tool_name: Nome da ferramenta
            description: Descrição da ferramenta
            input_schema: Schema de entrada
            metadata: Metadados adicionais

        Returns:
            Resultado da validação
        """
        result = SecurityValidationResult(
            is_safe=True, risk_count=0, risks_by_level={level.value: 0 for level in RiskLevel}
        )

        # 1. Validar nome
        self._check_tool_name(tool_name, result)

        # 2. Validar descrição
        self._check_description(tool_name, description, result)

        # 3. Validar schema de entrada
        self._check_input_schema(input_schema, result)

        # 4. Validar metadados
        if metadata:
            self._check_metadata(metadata, result)

        # 5. Consolidar resultado
        result.risk_count = len(result.risks)
        for risk in result.risks:
            result.risks_by_level[risk.level.value] += 1

        # Determinar se é segura baseado nos riscos
        critical_or_high = (
            result.risks_by_level[RiskLevel.CRITICAL.value] > 0
            or result.risks_by_level[RiskLevel.HIGH.value] > 0
        )
        medium_risks = result.risks_by_level[RiskLevel.MEDIUM.value] > 0

        result.is_safe = not (critical_or_high or (self.strict_mode and medium_risks))

        # Determinar se requer aprovação
        result.requires_approval = critical_or_high or (medium_risks and not self.strict_mode)

        # Determinar contextos permitidos
        if result.is_safe:
            result.allowed_contexts = ["default", "interactive", "batch"]
        elif result.requires_approval:
            result.allowed_contexts = ["interactive"]
        else:
            result.allowed_contexts = []

        logger.info(
            "security_validation_completed",
            tool_name=tool_name,
            is_safe=result.is_safe,
            risk_count=result.risk_count,
            requires_approval=result.requires_approval,
        )

        return result

    def _check_tool_name(self, tool_name: str, result: SecurityValidationResult):
        """Verifica se nome da ferramenta contém palavras perigosas."""
        name_lower = tool_name.lower()

        for keyword in self.DANGEROUS_KEYWORDS:
            if keyword in name_lower:
                level = (
                    RiskLevel.HIGH
                    if keyword in {"delete", "destroy", "drop", "format"}
                    else RiskLevel.MEDIUM
                )
                result.risks.append(
                    SecurityRisk(
                        risk_type="dangerous_name",
                        level=level,
                        message=f"Nome contém palavra-chave perigosa: '{keyword}'",
                        affected_field="tool_name",
                        recommendation="Renomear ferramenta para ser mais descritivo e menos agressivo",
                        cwe_ref=self._get_cwe_for_keyword(keyword),
                    )
                )
                break

    def _check_description(
        self, tool_name: str, description: str, result: SecurityValidationResult
    ):
        """Verifica descrição buscando indicações de perigo."""
        desc_lower = description.lower()

        # Verificar menções a operações de rede
        if not self.allow_network:
            network_terms = [
                "http",
                "https",
                "fetch",
                "download",
                "upload",
                "api",
                "webhook",
                "request",
            ]
            if any(term in desc_lower for term in network_terms):
                result.risks.append(
                    SecurityRisk(
                        risk_type="network_operation",
                        level=RiskLevel.MEDIUM,
                        message="Ferramenta pode realizar operações de rede",
                        affected_field="description",
                        recommendation="Limitar a endpoints whitelist ou sandbox de rede",
                    )
                )

        # Verificar menções a sistema de arquivos
        if not self.allow_filesystem:
            fs_terms = ["file", "write", "save", "load", "read", "delete", "directory", "path"]
            if any(term in desc_lower for term in fs_terms):
                result.risks.append(
                    SecurityRisk(
                        risk_type="filesystem_operation",
                        level=RiskLevel.MEDIUM,
                        message="Ferramenta pode acessar sistema de arquivos",
                        affected_field="description",
                        recommendation="Sandbox de filesystem ou caminhos whitelist",
                    )
                )

        # Verificar execução de código
        if any(term in desc_lower for term in ["execute", "eval", "run", "spawn", "shell"]):
            result.risks.append(
                SecurityRisk(
                    risk_type="code_execution",
                    level=RiskLevel.CRITICAL,
                    message="Ferramenta pode executar código arbitrário",
                    affected_field="description",
                    recommendation="Implementar validação estrita e sandbox",
                    cwe_ref="CWE-94",
                )
            )

    def _check_input_schema(
        self, schema: Dict[str, Any], result: SecurityValidationResult, path: str = "$"
    ):
        """Verifica schema de entrada em busca de riscos."""
        if not isinstance(schema, dict):
            return

        # Verificar propriedades
        properties = schema.get("properties", {})

        for prop_name, prop_def in properties.items():
            prop_lower = prop_name.lower()

            # Parametro suspeito
            if prop_lower in self.SUSPICIOUS_PARAMS:
                risk_type = self._get_risk_type_for_param(prop_lower)
                result.risks.append(
                    SecurityRisk(
                        risk_type=risk_type,
                        level=RiskLevel.MEDIUM,
                        message=f"Parâmetro '{prop_name}' pode ser usado para {risk_type}",
                        affected_field=f"{path}.properties.{prop_name}",
                        recommendation="Validar e sanitizar entrada estritamente",
                    )
                )

            # Verificar se há enum para restringir valores (bom)
            if "enum" not in prop_def and prop_lower in {"url", "uri", "host", "ip"}:
                result.risks.append(
                    SecurityRisk(
                        risk_type="unrestricted_parameter",
                        level=RiskLevel.LOW,
                        message=f"Parâmetro '{prop_name}' sem enum para restringer valores",
                        affected_field=f"{path}.properties.{prop_name}",
                        recommendation="Adicionar enum ou validação de padrão",
                    )
                )

            # Recursão para objetos aninhados
            if prop_def.get("type") == "object" and "properties" in prop_def:
                self._check_input_schema(prop_def, result, f"{path}.properties.{prop_name}")

            # Recursão para arrays
            if prop_def.get("type") == "array" and "items" in prop_def:
                self._check_input_schema(
                    prop_def["items"], result, f"{path}.properties.{prop_name}.items"
                )

    def _check_metadata(self, metadata: Dict[str, Any], result: SecurityValidationResult):
        """Verifica metadados da ferramenta."""
        # Verificar se há flags de perigo
        if metadata.get("dangerous"):
            result.risks.append(
                SecurityRisk(
                    risk_type="self_declared_dangerous",
                    level=RiskLevel.HIGH,
                    message="Ferramenta marcada como perigosa nos metadados",
                    affected_field="metadata.dangerous",
                    recommendation="Revisar necessidade e implementar salvaguardas",
                )
            )

        # Verificar se requer aprovação
        if metadata.get("requires_approval"):
            result.risks.append(
                SecurityRisk(
                    risk_type="requires_approval",
                    level=RiskLevel.MEDIUM,
                    message="Ferramenta requer aprovação por configuração",
                    affected_field="metadata.requires_approval",
                )
            )

        # Verificar contexto restrito
        allowed_contexts = metadata.get("allowed_contexts", [])
        if allowed_contexts and "interactive" not in allowed_contexts:
            result.risks.append(
                SecurityRisk(
                    risk_type="restricted_context",
                    level=RiskLevel.LOW,
                    message="Ferramenta com contexto de uso restrito",
                    affected_field="metadata.allowed_contexts",
                )
            )

        # Verificar se há taxa limite
        if not metadata.get("rate_limit"):
            result.risks.append(
                SecurityRisk(
                    risk_type="no_rate_limit",
                    level=RiskLevel.LOW,
                    message="Ferramenta sem limite de taxa configurado",
                    affected_field="metadata.rate_limit",
                    recommendation="Configurar rate_limit para prevenir abuso",
                )
            )

    def _get_risk_type_for_param(self, param: str) -> str:
        """Retorna tipo de risco baseado no nome do parâmetro."""
        risk_mapping = {
            "url": "ssrf",
            "uri": "ssrf",
            "endpoint": "ssrf",
            "host": "ssrf",
            "ip": "ssrf",
            "file": "path_traversal",
            "path": "path_traversal",
            "filename": "path_traversal",
            "directory": "path_traversal",
            "command": "command_injection",
            "cmd": "command_injection",
            "exec": "code_injection",
            "query": "sql_injection",
            "sql": "sql_injection",
        }
        return risk_mapping.get(param, "unrestricted_input")

    def _get_cwe_for_keyword(self, keyword: str) -> Optional[str]:
        """Retorna referência CWE para palavra-chave."""
        cwe_mapping = {
            "delete": "CWE-89",
            "drop": "CWE-89",
            "exec": "CWE-78",
            "eval": "CWE-94",
            "format": "CWE-134",
            "password": "CWE-532",
            "secret": "CWE-532",
            "token": "CWE-532",
        }
        return cwe_mapping.get(keyword)

    def validate_data_sensitivity(self, data: Dict[str, Any]) -> List[SecurityRisk]:
        """
        Valida se dados contêm informações sensíveis.

        Args:
            data: Dados a validar

        Returns:
            Lista de riscos encontrados
        """
        risks = []

        # Padrões para dados sensíveis
        patterns = {
            "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
            "ssn": re.compile(r"\b\d{3}-?\d{2}-?\d{4}\b"),
            "credit_card": re.compile(r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b"),
            "api_key": re.compile(r"\b[A-Za-z0-9]{32,}\b"),
            "password": re.compile(r"password\s*[:=]\s*\S+", re.IGNORECASE),
        }

        data_str = str(data)

        for risk_type, pattern in patterns.items():
            if pattern.search(data_str):
                risks.append(
                    SecurityRisk(
                        risk_type=f"sensitive_data_{risk_type}",
                        level=RiskLevel.HIGH
                        if risk_type in {"ssn", "credit_card"}
                        else RiskLevel.MEDIUM,
                        message=f"Dados podem conter {risk_type} sensível",
                        recommendation="Remover ou mascarar dados sensíveis antes de logar",
                    )
                )

        return risks
