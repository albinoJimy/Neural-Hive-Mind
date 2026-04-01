"""Serviço para auto-aplicação de otimizações seguras."""
import hashlib
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

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
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    # Go
    ".go",
    # Java
    ".java",
    # C#
    ".cs",
    # SQL
    ".sql",
    # C/C++
    ".c",
    ".cpp",
    ".cc",
    ".h",
    ".hpp",
    # Rust
    ".rs",
    # Shell scripts
    ".sh",
    ".bash",
    # YAML/K8s
    ".yaml",
    ".yml",
    # JSON
    ".json",
    # Protocol Buffers
    ".proto",
    # HTML/Templates
    ".html",
    ".htm",
    ".xml",
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
        recommendation: dict[str, Any],
        project_root: str = "/home/jimy/NHM/Neural-Hive-Mind",
    ) -> dict[str, Any]:
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

    def _check_safety(self, recommendation: dict[str, Any]) -> dict[str, Any]:
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
        recommendation: dict[str, Any],
        project_root: str,
    ) -> dict[str, Any]:
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

    def _parse_unified_diff(self, patch: str) -> list[dict[str, Any]]:
        """
        Parse unified diff format em estruturas aplicáveis.

        Formato esperado (unified diff):
        --- a/file.py
        +++ b/file.py
        @@ -lineno,count +lineno,count @@
         -linha removida
         +linha adicionada
          linha de contexto

        Args:
            patch: String contendo o unified diff

        Returns:
            Lista de hunks com metadados e mudanças
        """
        hunks = []
        lines = patch.split("\n")

        i = 0
        current_hunk = None

        while i < len(lines):
            line = lines[i]

            # Detectar inicio de um hunk (@@ -x,y +a,b @@)
            if line.startswith("@@"):
                if current_hunk:
                    hunks.append(current_hunk)

                # Parse da linha do hunk: @@ -old_start,old_count +new_start,new_count @@
                match = re.search(r"@@\s*-(\d+),?(\d+)?\s*\+(\d+),?(\d+)?\s*@@", line)
                if match:
                    old_start = int(match.group(1)) - 1  # 0-indexed
                    old_count = int(match.group(2)) if match.group(2) else 1
                    new_start = int(match.group(3)) - 1  # 0-indexed
                    new_count = int(match.group(4)) if match.group(4) else 1

                    current_hunk = {
                        "old_start": old_start,
                        "old_count": old_count,
                        "new_start": new_start,
                        "new_count": new_count,
                        "changes": [],
                    }

            # Processar linhas dentro do hunk
            elif current_hunk is not None:
                if line.startswith("-"):
                    current_hunk["changes"].append(("delete", line[1:]))
                elif line.startswith("+"):
                    current_hunk["changes"].append(("insert", line[1:]))
                elif line.startswith(" "):
                    current_hunk["changes"].append(("context", line[1:]))

            i += 1

        if current_hunk:
            hunks.append(current_hunk)

        return hunks

    def _apply_hunk_to_lines(
        self,
        lines: list[str],
        hunk: dict[str, Any],
    ) -> tuple[list[str], bool]:
        """
        Aplica um hunk a uma lista de linhas.

        Args:
            lines: Lista de linhas do arquivo original
            hunk: Hunk parsed do unified diff

        Returns:
            Tuple de (novas linhas, sucesso)
        """
        old_start = hunk["old_start"]
        old_count = hunk["old_count"]
        changes = hunk["changes"]

        # Verificar se temos linhas suficientes
        if old_start + old_count > len(lines):
            return lines, False

        # Verificar contexto (linhas que devem existir)
        new_lines = lines[:old_start]
        old_idx = old_start
        change_idx = 0

        while change_idx < len(changes):
            change_type, content = changes[change_idx]

            if change_type == "context":
                # Verificar se a linha de contexto bate
                if old_idx >= len(lines) or lines[old_idx] != content:
                    return lines, False
                new_lines.append(content)
                old_idx += 1
                change_idx += 1

            elif change_type == "delete":
                # Remover linha (verificar se bate)
                if old_idx >= len(lines) or lines[old_idx] != content:
                    return lines, False
                old_idx += 1
                change_idx += 1

            elif change_type == "insert":
                # Inserir nova linha
                new_lines.append(content)
                change_idx += 1

        # Adicionar linhas restantes após o hunk
        if old_idx < len(lines):
            new_lines.extend(lines[old_idx:])

        return new_lines, True

    async def _apply_patch(
        self,
        file_path: str,
        patch: str,
        recommendation: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Aplica patch ao arquivo usando unified diff format.

        Args:
            file_path: Caminho do arquivo
            patch: Diff a ser aplicado (unified diff format)
            recommendation: Dados da recomendação

        Returns:
            Dict com resultado
        """
        if self.dry_run:
            logger.info(
                "[DRY_RUN] Would apply patch",
                file_path=file_path,
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
            with open(file_path, encoding="utf-8") as f:
                original_lines = f.readlines()

            # Salvar hash do conteúdo original para verificação
            original_hash = hashlib.md5("".join(original_lines).encode()).hexdigest()

            # Parse do unified diff
            hunks = self._parse_unified_diff(patch)

            if not hunks:
                return {
                    "success": False,
                    "recommendation_id": recommendation.get("id"),
                    "reason": "No valid hunks found in patch",
                }

            logger.info(
                "applying_patch",
                file_path=file_path,
                hunks_count=len(hunks),
            )

            # Aplicar hunks sequencialmente (de trás para frente para preservar line numbers)
            applied_hunks = 0
            current_lines = original_lines

            for hunk in reversed(hunks):
                new_lines, success = self._apply_hunk_to_lines(current_lines, hunk)
                if success:
                    current_lines = new_lines
                    applied_hunks += 1
                else:
                    logger.warning(
                        "hunk_application_failed",
                        old_start=hunk["old_start"],
                        old_count=hunk["old_count"],
                    )

            if applied_hunks == 0:
                return {
                    "success": False,
                    "recommendation_id": recommendation.get("id"),
                    "reason": "Failed to apply any hunks - patch may not match file content",
                }

            # Salvar backup antes de escrever
            backup_path = f"{file_path}.backup.{datetime.now().strftime('%Y%m%d%H%M%S')}"
            with open(backup_path, "w", encoding="utf-8") as f:
                f.writelines(original_lines)

            # Escrever novo conteúdo
            with open(file_path, "w", encoding="utf-8") as f:
                f.writelines(current_lines)

            # Verificar hash novo
            new_hash = hashlib.md5("".join(current_lines).encode()).hexdigest()

            self._applied_count += 1

            logger.info(
                "patch_applied_successfully",
                file_path=file_path,
                backup_path=backup_path,
                hunks_applied=applied_hunks,
                original_hash=original_hash,
                new_hash=new_hash,
            )

            return {
                "success": True,
                "recommendation_id": recommendation.get("id"),
                "applied": True,
                "file_path": file_path,
                "backup_path": backup_path,
                "hunks_applied": applied_hunks,
                "total_hunks": len(hunks),
                "original_hash": original_hash,
                "new_hash": new_hash,
            }

        except FileNotFoundError:
            logger.error("file_not_found", file_path=file_path)
            return {
                "success": False,
                "recommendation_id": recommendation.get("id"),
                "reason": f"File not found: {file_path}",
            }
        except PermissionError:
            logger.error("permission_denied", file_path=file_path)
            return {
                "success": False,
                "recommendation_id": recommendation.get("id"),
                "reason": f"Permission denied: {file_path}",
            }
        except Exception as e:
            logger.error("patch_application_failed", file_path=file_path, error=str(e))
            return {
                "success": False,
                "recommendation_id": recommendation.get("id"),
                "reason": str(e),
            }

    async def _apply_database_optimization(
        self,
        recommendation: dict[str, Any],
        project_root: str,
    ) -> dict[str, Any]:
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
        before_metrics: dict[str, Any],
        after_metrics: dict[str, Any],
    ) -> dict[str, Any]:
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

    def get_stats(self) -> dict[str, int]:
        """Retorna estatísticas de aplicações."""
        return {
            "applied": self._applied_count,
            "skipped": self._skipped_count,
        }
