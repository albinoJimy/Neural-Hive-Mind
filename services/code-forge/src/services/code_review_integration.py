"""
Integração com workflows de Code Review (GitHub PRs, GitLab MRs).

Implementa:
- Criação de Pull Requests no GitHub
- Criação de Merge Requests no GitLab
- Comentários automáticos baseados em validações
- Integração com approval gate
"""

from typing import Optional, Dict, Any, List
from enum import Enum
import structlog
import httpx
from ..types.artifact_types import ValidationResult, ValidationStatus

logger = structlog.get_logger()


class GitProvider(str, Enum):
    """Providers Git suportados."""
    GITHUB = "github"
    GITLAB = "gitlab"
    BITBUCKET = "bitbucket"
    AZURE_DEVOPS = "azure_devops"


class ReviewStatus(str, Enum):
    """Status do review."""
    PENDING = "pending"
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"
    COMMENTED = "commented"


class CodeReviewClient:
    """
    Cliente unificado para integração com Code Review workflows.

    Suporta criação de PRs/MRs e comentários automáticos.
    """

    def __init__(
        self,
        provider: GitProvider,
        base_url: str,
        token: str,
        timeout: int = 30
    ):
        self.provider = provider
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.timeout = timeout

        # Configurar HTTP client
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers=self._get_headers(),
            timeout=timeout
        )

    def _get_headers(self) -> Dict[str, str]:
        """Retorna headers HTTP para autenticação."""
        headers = {
            "Accept": "application/vnd.github.v3+json" if self.provider == GitProvider.GITHUB else "application/json",
        }

        if self.provider == GitProvider.GITHUB:
            headers["Authorization"] = f"token {self.token}"
            headers["X-GitHub-Api-Version"] = "2022-11-28"
        elif self.provider == GitProvider.GITLAB:
            headers["PRIVATE-TOKEN"] = self.token
        elif self.provider == GitProvider.BITBUCKET:
            headers["Authorization"] = f"Bearer {self.token}"

        return headers

    async def create_pull_request(
        self,
        repo_owner: str,
        repo_name: str,
        title: str,
        description: str,
        source_branch: str,
        target_branch: str = "main",
        draft: bool = False,
        labels: Optional[List[str]] = None,
        reviewers: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Cria Pull Request no GitHub.

        Args:
            repo_owner: Dono do repositório
            repo_name: Nome do repositório
            title: Título do PR
            description: Descrição/corpo do PR
            source_branch: Branch de origem
            target_branch: Branch de destino
            draft: Se True, cria como draft
            labels: Labels a adicionar
            reviewers: Reviewers a solicitar

        Returns:
            Dict com dados do PR criado
        """
        if self.provider != GitProvider.GITHUB:
            raise ValueError(f"create_pull_request only supports GitHub, got {self.provider}")

        endpoint = f"/repos/{repo_owner}/{repo_name}/pulls"
        payload = {
            "title": title,
            "body": description,
            "head": source_branch,
            "base": target_branch,
            "draft": draft,
            "maintainer_can_modify": True
        }

        if labels:
            payload["labels"] = labels

        response = await self._client.post(endpoint, json=payload)
        response.raise_for_status()
        pr_data = response.json()

        logger.info(
            'github_pr_created',
            pr_number=pr_data.get('number'),
            repo=f"{repo_owner}/{repo_name}",
            draft=draft
        )

        # Solicitar reviewers se fornecido
        if reviewers:
            await self._request_github_reviewers(
                repo_owner, repo_name, pr_data.get('number'), reviewers
            )

        return {
            "provider": "github",
            "pr_number": pr_data.get('number'),
            "pr_id": pr_data.get('id'),
            "url": pr_data.get('html_url'),
            "state": pr_data.get('state'),
            "draft": pr_data.get('draft'),
            "created_at": pr_data.get('created_at')
        }

    async def _request_github_reviewers(
        self,
        repo_owner: str,
        repo_name: str,
        pr_number: int,
        reviewers: List[str]
    ):
        """Solicita reviewers no GitHub."""
        endpoint = f"/repos/{repo_owner}/{repo_name}/pulls/{pr_number}/requested_reviewers"

        for reviewer in reviewers:
            try:
                payload = {"reviewers": [reviewer]}
                response = await self._client.post(endpoint, json=payload)
                if response.status_code not in (200, 201, 404):
                    logger.warning(
                        'github_reviewer_request_failed',
                        reviewer=reviewer,
                        status=response.status_code
                    )
            except Exception as e:
                logger.warning('github_reviewer_request_error', reviewer=reviewer, error=str(e))

    async def create_merge_request(
        self,
        project_id: int,
        source_branch: str,
        target_branch: str = "main",
        title: Optional[str] = None,
        description: Optional[str] = None,
        draft: bool = False,
        labels: Optional[List[str]] = None,
        assignees: Optional[List[str]] = None,
        remove_source_branch: bool = False
    ) -> Dict[str, Any]:
        """
        Cria Merge Request no GitLab.

        Args:
            project_id: ID do projeto GitLab
            source_branch: Branch de origem
            target_branch: Branch de destino
            title: Título do MR
            description: Descrição do MR
            draft: Se True, cria como draft
            labels: Labels a adicionar
            assignees: Usuários a atribuir
            remove_source_branch: Remover branch após merge

        Returns:
            Dict com dados do MR criado
        """
        if self.provider != GitProvider.GITLAB:
            raise ValueError(f"create_merge_request only supports GitLab, got {self.provider}")

        endpoint = f"/projects/{project_id}/merge_requests"
        payload = {
            "source_branch": source_branch,
            "target_branch": target_branch,
            "draft": draft,
            "remove_source_branch": remove_source_branch
        }

        if title:
            payload["title"] = title
        if description:
            payload["description"] = description
        if labels:
            payload["labels"] = ",".join(labels)
        if assignees:
            payload["assignee_ids"] = assignees

        response = await self._client.post(endpoint, json=payload)
        response.raise_for_status()
        mr_data = response.json()

        logger.info(
            'gitlab_mr_created',
            mr_iid=mr_data.get('iid'),
            project_id=project_id,
            draft=draft
        )

        return {
            "provider": "gitlab",
            "mr_number": mr_data.get('iid'),
            "mr_id": mr_data.get('id'),
            "web_url": mr_data.get('web_url'),
            "state": mr_data.get('state'),
            "draft": mr_data.get('draft'),
            "created_at": mr_data.get('created_at')
        }

    async def add_validation_comment(
        self,
        repo_owner: str,
        repo_name: str,
        pr_number: int,
        validation_results: List[ValidationResult],
        overall_status: str
    ) -> Dict[str, Any]:
        """
        Adiciona comentário com resultados de validação no PR.

        Args:
            repo_owner: Dono do repositório
            repo_name: Nome do repositório
            pr_number: Número do PR
            validation_results: Resultados das validações
            overall_status: Status geral (approve/comment/changes_requested)

        Returns:
            Dict com dados do comentário criado
        """
        comment_body = self._format_validation_comment(validation_results, overall_status)

        if self.provider == GitProvider.GITHUB:
            return await self._add_github_comment(
                repo_owner, repo_name, pr_number, comment_body
            )
        elif self.provider == GitProvider.GITLAB:
            return await self._add_gitlab_comment(
                repo_owner, repo_name, pr_number, comment_body
            )
        else:
            raise NotImplementedError(f"Comments not supported for {self.provider}")

    async def _add_github_comment(
        self,
        repo_owner: str,
        repo_name: str,
        pr_number: int,
        body: str
    ) -> Dict[str, Any]:
        """Adiciona comentário no PR do GitHub."""
        endpoint = f"/repos/{repo_owner}/{repo_name}/pulls/{pr_number}/comments"
        payload = {"body": body}

        response = await self._client.post(endpoint, json=payload)
        response.raise_for_status()
        comment_data = response.json()

        return {
            "comment_id": comment_data.get('id'),
            "url": comment_data.get('html_url')
        }

    async def _add_gitlab_comment(
        self,
        repo_owner: str,
        repo_name: str,
        mr_number: int,
        body: str
    ) -> Dict[str, Any]:
        """Adiciona comentário no MR do GitLab."""
        # Para GitLab, precisamos do project_id
        # Primeiro tentamos encontrar o projeto pelo nome
        project_id = await self._get_gitlab_project_id(repo_owner, repo_name)
        if not project_id:
            raise ValueError(f"Project {repo_owner}/{repo_name} not found")

        endpoint = f"/projects/{project_id}/merge_requests/{mr_number}/notes"
        payload = {"body": body}

        response = await self._client.post(endpoint, json=payload)
        response.raise_for_status()
        comment_data = response.json()

        return {
            "comment_id": comment_data.get('id'),
            "url": comment_data.get('web_url')
        }

    async def _get_gitlab_project_id(self, repo_owner: str, repo_name: str) -> Optional[int]:
        """Busca project_id no GitLab pelo nome."""
        try:
            endpoint = f"/projects/{repo_owner}%2F{repo_name}"
            response = await self._client.get(endpoint)
            if response.status_code == 200:
                return response.json().get('id')
        except Exception as e:
            logger.warning('gitlab_project_lookup_failed', repo=f"{repo_owner}/{repo_name}", error=str(e))
        return None

    def _format_validation_comment(
        self,
        validation_results: List[ValidationResult],
        overall_status: str
    ) -> str:
        """Formata comentário de validação."""
        lines = [
            "## 🔍 Code Review - Neural Code Forge",
            "",
            f"**Status:** {overall_status.upper()}",
            "",
            "### Validation Results",
            ""
        ]

        # Se não houver validações, adicionar mensagem
        if not validation_results:
            lines.append("No validations performed.")
        else:
            # Agrupar por tipo
            by_type = {}
            for result in validation_results:
                vtype = result.validation_type.value
                if vtype not in by_type:
                    by_type[vtype] = []
                by_type[vtype].append(result)

            # Ordenar por criticidade
            for vtype in ['SAST', 'DAST', 'SCA', 'LICENSE_CHECK']:
                if vtype not in by_type:
                    continue

                lines.append(f"#### {vtype}")

                for result in by_type[vtype]:
                    status_icon = "✅" if result.status == ValidationStatus.PASSED else "❌"
                    lines.append(f"- {status_icon} **{result.tool_name}**")

                    if result.issues_count > 0:
                        lines.append(f"  - Issues: {result.issues_count}")
                        if result.critical_issues > 0:
                            lines.append(f"  - 🔴 Critical: {result.critical_issues}")
                        if result.high_issues > 0:
                            lines.append(f"  - 🟠 High: {result.high_issues}")
                        if result.medium_issues > 0:
                            lines.append(f"  - 🟡 Medium: {result.medium_issues}")
                        if result.low_issues > 0:
                            lines.append(f"  - 🔵 Low: {result.low_issues}")

                    if result.score is not None:
                        score_percent = int(result.score * 100)
                        lines.append(f"  - Score: {score_percent}%")

                    if result.report_uri:
                        lines.append(f"  - [Report]({result.report_uri})")

                    lines.append("")

        # Adicionar recomendações
        if overall_status == "changes_requested":
            lines.extend([
                "### 🔧 Recommendations",
                "",
                "Please review the issues above and make necessary changes before proceeding.",
                ""
            ])
        elif overall_status == "approved":
            lines.extend([
                "### ✅ Approved",
                "",
                "All validations passed! This artifact is ready for merge.",
                ""
            ])

        lines.extend([
            "---",
            "*Generated by Neural Code Forge*"
        ])

        return "\n".join(lines)

    async def set_review_status(
        self,
        repo_owner: str,
        repo_name: str,
        pr_number: int,
        status: ReviewStatus,
        comment: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Define status de review (aprova/rejeita).

        Args:
            repo_owner: Dono do repositório
            repo_name: Nome do repositório
            pr_number: Número do PR
            status: Status do review
            comment: Comentário opcional

        Returns:
            Dict com dados da review criada
        """
        if self.provider == GitProvider.GITHUB:
            return await self._set_github_review_status(
                repo_owner, repo_name, pr_number, status, comment
            )
        elif self.provider == GitProvider.GITLAB:
            return await self._set_gitlab_review_status(
                repo_owner, repo_name, pr_number, status, comment
            )
        else:
            raise NotImplementedError(f"Review not supported for {self.provider}")

    async def _set_github_review_status(
        self,
        repo_owner: str,
        repo_name: str,
        pr_number: int,
        status: ReviewStatus,
        comment: Optional[str] = None
    ) -> Dict[str, Any]:
        """Define status de review no GitHub."""
        event_map = {
            ReviewStatus.APPROVED: "APPROVE",
            ReviewStatus.CHANGES_REQUESTED: "REQUEST_CHANGES",
            ReviewStatus.COMMENTED: "COMMENT"
        }

        endpoint = f"/repos/{repo_owner}/{repo_name}/pulls/{pr_number}/reviews"
        payload = {
            "event": event_map.get(status, "COMMENT")
        }

        if comment:
            payload["body"] = comment

        response = await self._client.post(endpoint, json=payload)
        response.raise_for_status()
        review_data = response.json()

        return {
            "review_id": review_data.get('id'),
            "user": review_data.get('user', {}).get('login'),
            "state": review_data.get('state'),
            "submitted_at": review_data.get('submitted_at')
        }

    async def _set_gitlab_review_status(
        self,
        repo_owner: str,
        repo_name: str,
        mr_number: int,
        status: ReviewStatus,
        comment: Optional[str] = None
    ) -> Dict[str, Any]:
        """Define status de review no GitLab."""
        project_id = await self._get_gitlab_project_id(repo_owner, repo_name)
        if not project_id:
            raise ValueError(f"Project {repo_owner}/{repo_name} not found")

        # GitLab usa emoji de aprovação
        approval_map = {
            ReviewStatus.APPROVED: "thumbsup",
            ReviewStatus.CHANGES_REQUESTED: "thumbsdown"
        }

        endpoint = f"/projects/{project_id}/merge_requests/{mr_number}/approval"
        payload = {"approval": approval_map.get(status, "thumbsup")}

        if comment:
            # Adicionar como note separado
            await self._add_gitlab_comment(repo_owner, repo_name, mr_number, comment)

        response = await self._client.post(endpoint, json=payload)
        response.raise_for_status()

        return {
            "status": status.value,
            "project_id": project_id,
            "mr_number": mr_number
        }

    async def close(self):
        """Fecha o cliente HTTP."""
        await self._client.aclose()


class CodeReviewIntegration:
    """
    Integração de Code Review com o Pipeline do CodeForge.

    Orquestra criação de PRs/MRs e comentários de validação.
    """

    def __init__(
        self,
        github_client: Optional[CodeReviewClient] = None,
        gitlab_client: Optional[CodeReviewClient] = None,
        default_provider: GitProvider = GitProvider.GITHUB
    ):
        self.github_client = github_client
        self.gitlab_client = gitlab_client
        self.default_provider = default_provider

    async def create_review_for_artifact(
        self,
        artifact_id: str,
        artifact_content: str,
        validation_results: List[ValidationResult],
        repo_owner: str,
        repo_name: str,
        source_branch: str,
        target_branch: str = "main",
        provider: Optional[GitProvider] = None
    ) -> Dict[str, Any]:
        """
        Cria PR/MR para um artefato com comentários de validação.

        Args:
            artifact_id: ID do artefato
            artifact_content: Conteúdo gerado
            validation_results: Resultados das validações
            repo_owner: Dono do repositório
            repo_name: Nome do repositório
            source_branch: Branch de origem
            target_branch: Branch de destino
            provider: Provider Git

        Returns:
            Dict com dados do PR/MR criado
        """
        provider = provider or self.default_provider
        client = self._get_client(provider)

        # Determinar título e descrição
        title = f"feat: Generated artifact {artifact_id}"
        description = self._generate_pr_description(artifact_id, validation_results)

        # Criar PR/MR
        if provider == GitProvider.GITHUB:
            pr_or_mr = await client.create_pull_request(
                repo_owner=repo_owner,
                repo_name=repo_name,
                title=title,
                description=description,
                source_branch=source_branch,
                target_branch=target_branch,
                draft=True  # Criar como draft até validações passarem
            )
        elif provider == GitProvider.GITLAB:
            # Para GitLab precisamos do project_id
            # Tenta inferir do repo_owner/repo_name
            project_id = await client._get_gitlab_project_id(repo_owner, repo_name)
            if not project_id:
                raise ValueError(f"Could not find GitLab project: {repo_owner}/{repo_name}")

            pr_or_mr = await client.create_merge_request(
                project_id=project_id,
                source_branch=source_branch,
                target_branch=target_branch,
                title=title,
                description=description,
                draft=True
            )

        # Adicionar comentário de validação
        pr_number = pr_or_mr.get('pr_number') or pr_or_mr.get('mr_number')
        await client.add_validation_comment(
            repo_owner=repo_owner,
            repo_name=repo_name,
            pr_number=pr_number,
            validation_results=validation_results,
            overall_status=self._calculate_overall_status(validation_results)
        )

        # Se tudo passou, converter de draft para normal
        if self._all_validations_passed(validation_results):
            await self._convert_from_draft(client, repo_owner, repo_name, pr_or_mr)

        logger.info(
            'code_review_created',
            artifact_id=artifact_id,
            provider=provider,
            pr_or_mr_id=pr_or_mr.get('pr_number') or pr_or_mr.get('mr_number')
        )

        return pr_or_mr

    def _get_client(self, provider: GitProvider) -> CodeReviewClient:
        """Retorna cliente apropriado para o provider."""
        if provider == GitProvider.GITHUB:
            if not self.github_client:
                raise ValueError("GitHub client not configured")
            return self.github_client
        elif provider == GitProvider.GITLAB:
            if not self.gitlab_client:
                raise ValueError("GitLab client not configured")
            return self.gitlab_client
        else:
            raise ValueError(f"Unsupported provider: {provider}")

    def _generate_pr_description(
        self,
        artifact_id: str,
        validation_results: List[ValidationResult]
    ) -> str:
        """Gera descrição do PR/MR."""
        # Obter timestamp formatado ou N/A
        timestamp = "N/A"
        if validation_results and validation_results[0].executed_at:
            timestamp = validation_results[0].executed_at.isoformat()

        return f'''## 📦 Generated Artifact

This pull request contains code generated by Neural Code Forge.

**Artifact ID:** `{artifact_id}`
**Generated at:** {timestamp}

## 🔍 Validations

The following validations were performed:

{self._format_validation_summary(validation_results)}

## 📝 Changes

- Auto-generated code and infrastructure
- Includes Dockerfile, Helm charts, and Kubernetes manifests
- Follows best practices and security guidelines

## ✅ Checklist

- [x] Code generated by Neural Code Forge
- [x] Security scans performed
- [x] Quality checks completed
- [ ] Manual review required
- [ ] Tests passed locally

---

*This is an automated pull request. Please review the generated code carefully before merging.*
'''

    def _format_validation_summary(self, validation_results: List[ValidationResult]) -> str:
        """Formata resumo de validações."""
        if not validation_results:
            return "No validations performed."

        lines = []
        for result in validation_results:
            status_icon = "✅" if result.status == ValidationStatus.PASSED else "❌"
            lines.append(
                f"- {status_icon} **{result.tool_name}** ({result.validation_type.value}): "
                f"{result.issues_count} issues"
            )

        return "\n".join(lines)

    def _calculate_overall_status(self, validation_results: List[ValidationResult]) -> str:
        """Calcula status geral baseado nas validações."""
        if not validation_results:
            return "commented"

        critical_count = sum(r.critical_issues for r in validation_results)
        high_count = sum(r.high_issues for r in validation_results)

        if critical_count > 0:
            return "changes_requested"
        elif high_count > 5:
            return "changes_requested"
        elif any(r.status == ValidationStatus.FAILED for r in validation_results):
            return "changes_requested"
        else:
            return "approved"

    def _all_validations_passed(self, validation_results: List[ValidationResult]) -> bool:
        """Verifica se todas as validações passaram."""
        return all(
            r.status == ValidationStatus.PASSED and r.critical_issues == 0
            for r in validation_results
        )

    async def _convert_from_draft(
        self,
        client: CodeReviewClient,
        repo_owner: str,
        repo_name: str,
        pr_or_mr: Dict[str, Any]
    ):
        """Converte PR/MR de draft para normal."""
        # Implementação dependeria do provider
        # Para GitHub, seria um PATCH no PR com draft=false
        pass
