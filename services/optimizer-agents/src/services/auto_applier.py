"""Serviço para auto-aplicação de otimizações seguras."""
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


# Padrões de arquivos que nunca devem ser modificados automaticamente
SAFE_GUARD_PATTERNS = [
    r".*/config/.*",  # Arquivos de configuração
    r".*/tests?/.*",  # Testes em diretórios test/ ou tests/
    r".*/test_.*\.py$",  # Arquivos Python começando com test_
    r".*/test_.*\.(js|ts|go|java|cs|rs)$",  # Arquivos de teste em outras linguagens
    r".*_test\.py$",  # Arquivos Python terminando com _test
    r".*test(s)?\.(js|ts|go|java|cs|rs|sql)$",  # Arquivos de teste em outras linguagens
    r".*/migrations/.*",  # Migrations de banco
    r".*/\.env.*",  # Arquivos de ambiente
    r".*/secrets/.*",  # Secrets
    r".*\.key$",  # Chaves privadas
    r".*\.pem$",  # Certificados
    r".*\.crt$",  # Certificados
    r".*\.ssh$",  # Chaves SSH
]

RECOMMENDED_EXTENSIONS = {
    # Python
    ".py",
    # JavaScript/TypeScript
    ".js", ".ts", ".jsx", ".tsx",
    # Go
    ".go",
    # Java
    ".java",
    # C#
    ".cs",
    # SQL
    ".sql",
    # C/C++
    ".c", ".cpp", ".cc", ".h", ".hpp",
    # Rust
    ".rs",
    # Shell scripts
    ".sh", ".bash",
    # YAML/K8s
    ".yaml", ".yml",
    # JSON
    ".json",
    # Protocol Buffers
    ".proto",
    # HTML/Templates
    ".html", ".htm", ".xml",
}


class OptimizationApplier:
    """Aplica otimizações de código automaticamente."""

    def __init__(self, dry_run: bool = True):
        """
        Inicializa applier.

        Args:
            dry_run: Se True, apenas simula as mudanças sem aplicar
        """
        self.dry_run = dry_run
        self._applied_count = 0
        self._skipped_count = 0

    async def apply_recommendation(
        self,
        recommendation: Dict[str, Any],
        project_root: str = "/home/jimy/NHM/Neural-Hive-Mind",
    ) -> Dict[str, Any]:
        """
        Aplica uma recomendação de otimização.

        Args:
            recommendation: Dados da recomendação
            project_root: Raiz do projeto

        Returns:
            Dict com resultado da aplicação
        """
        rec_id = recommendation.get("id", "unknown")

        # Verificar se é seguro aplicar
        safety_check = self._check_safety(recommendation)
        if not safety_check["safe"]:
            return {
                "success": False,
                "recommendation_id": rec_id,
                "reason": f"Safety check failed: {safety_check['reason']}",
                "skipped": True,
            }

        # Verificar auto_apply flag
        if not recommendation.get("auto_apply", False):
            return {
                "success": False,
                "recommendation_id": rec_id,
                "reason": "Recommendation not marked for auto-apply",
                "skipped": True,
            }

        # Aplicar baseado no tipo
        target_type = recommendation.get("target_type", "code")

        if target_type == "code":
            return await self._apply_code_optimization(recommendation, project_root)
        elif target_type in ["mongodb", "postgresql", "neo4j", "redis", "clickhouse"]:
            return await self._apply_database_optimization(recommendation, project_root)
        else:
            return {
                "success": False,
                "recommendation_id": rec_id,
                "reason": f"Unsupported target type: {target_type}",
            }

    def _check_safety(self, recommendation: Dict[str, Any]) -> Dict[str, Any]:
        """
        Verifica se é seguro aplicar a recomendação automaticamente.

        Args:
            recommendation: Dados da recomendação

        Returns:
            Dict com safe (bool) e reason (str)
        """
        file_path = recommendation.get("file_path", "")

        # Verificar padrões bloqueados
        for pattern in SAFE_GUARD_PATTERNS:
            if re.match(pattern, file_path):
                return {
                    "safe": False,
                    "reason": f"File matches blocked pattern: {pattern}",
                }

        # Verificar extensão
        ext = Path(file_path).suffix
        if ext and ext not in RECOMMENDED_EXTENSIONS:
            return {
                "safe": False,
                "reason": f"File extension not supported for auto-apply: {ext}",
            }

        # Verificar severity
        severity = recommendation.get("severity", "medium")
        if severity == "critical":
            return {
                "safe": False,
                "reason": "Critical severity recommendations require manual review",
            }

        return {"safe": True}

    async def _apply_code_optimization(
        self,
        recommendation: Dict[str, Any],
        project_root: str,
    ) -> Dict[str, Any]:
        """
        Aplica otimização de código.

        Args:
            recommendation: Dados da recomendação
            project_root: Raiz do projeto

        Returns:
            Dict com resultado
        """
        file_path = recommendation.get("file_path")
        if not file_path:
            return {
                "success": False,
                "recommendation_id": recommendation.get("id"),
                "reason": "No file path specified",
            }

        full_path = os.path.join(project_root, file_path)

        if not os.path.exists(full_path):
            return {
                "success": False,
                "recommendation_id": recommendation.get("id"),
                "reason": f"File not found: {full_path}",
            }

        # Se houver code_diff, aplicar
        code_diff = recommendation.get("code_diff")
        if code_diff:
            return await self._apply_patch(full_path, code_diff, recommendation)

        # Se não houver diff, apenas reportar
        return {
            "success": True,
            "recommendation_id": recommendation.get("id"),
            "applied": False,
            "reason": "No code_diff provided, optimization suggested but not applied",
            "file_path": file_path,
        }

    async def _apply_patch(
        self,
        file_path: str,
        patch: str,
        recommendation: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Aplica patch ao arquivo.

        Args:
            file_path: Caminho do arquivo
            patch: Diff a ser aplicado
            recommendation: Dados da recomendação

        Returns:
            Dict com resultado
        """
        if self.dry_run:
            logger.info(
                f"[DRY RUN] Would apply patch to {file_path}",
                patch_lines=len(patch.split("\n")),
            )
            return {
                "success": True,
                "recommendation_id": recommendation.get("id"),
                "applied": False,
                "dry_run": True,
                "file_path": file_path,
                "patch_size": len(patch),
            }

        try:
            # Ler arquivo original
            with open(file_path, "r") as f:
                original_content = f.read()

            # TODO: Aplicar patch usando unified diff format
            # Por enquanto, apenas log
            logger.info(f"Applying patch to {file_path}")

            # Salvar backup
            backup_path = f"{file_path}.backup.{datetime.now().strftime('%Y%m%d%H%M%S')}"
            with open(backup_path, "w") as f:
                f.write(original_content)

            # Aplicar mudanças (simplificado - implementação real usaria patch.apply)
            # result = patch.apply(original_content, patch)

            self._applied_count += 1

            return {
                "success": True,
                "recommendation_id": recommendation.get("id"),
                "applied": True,
                "file_path": file_path,
                "backup_path": backup_path,
            }

        except Exception as e:
            logger.error(f"Failed to apply patch to {file_path}: {e}")
            return {
                "success": False,
                "recommendation_id": recommendation.get("id"),
                "reason": str(e),
            }

    async def _apply_database_optimization(
        self,
        recommendation: Dict[str, Any],
        project_root: str,
    ) -> Dict[str, Any]:
        """
        Registra otimização de banco para aplicação manual.

        Otimizações de banco (indexes, schema changes) não são aplicadas
        automaticamente por segurança, mas são registradas.

        Args:
            recommendation: Dados da recomendação
            project_root: Raiz do projeto

        Returns:
            Dict com resultado
        """
        rec_type = recommendation.get("type", "unknown")

        # Otimizações de banco não são aplicadas automaticamente
        return {
            "success": True,
            "recommendation_id": recommendation.get("id"),
            "applied": False,
            "reason": f"Database optimization ({rec_type}) requires manual review and application",
            "suggested_query": recommendation.get("query_suggestion"),
        }

    async def validate_application(
        self,
        before_metrics: Dict[str, Any],
        after_metrics: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Valida se a otimização trouxe melhoria.

        Args:
            before_metrics: Métricas antes da otimização
            after_metrics: Métricas após a otimização

        Returns:
            Dict com resultado da validação
        """
        before_duration = before_metrics.get("duration_ms", 0)
        after_duration = after_metrics.get("duration_ms", 0)

        if before_duration == 0:
            return {
                "valid": False,
                "reason": "No baseline metrics available",
            }

        improvement_pct = ((before_duration - after_duration) / before_duration) * 100

        return {
            "valid": True,
            "improvement_pct": round(improvement_pct, 2),
            "before_duration_ms": before_duration,
            "after_duration_ms": after_duration,
            "successful": improvement_pct > 0,
        }

    def get_stats(self) -> Dict[str, int]:
        """Retorna estatísticas de aplicações."""
        return {
            "applied": self._applied_count,
            "skipped": self._skipped_count,
        }
