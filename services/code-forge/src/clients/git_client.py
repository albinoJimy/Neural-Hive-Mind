import os
import urllib.parse
from pathlib import Path
from typing import Optional, Dict, Any, List

import git
import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

logger = structlog.get_logger()


class GitClient:
    """Cliente para operações Git com suporte a GitLab e GitHub APIs"""

    def __init__(
        self,
        templates_repo: str,
        templates_branch: str,
        local_path: str,
        gitlab_url: Optional[str] = None,
        gitlab_token: Optional[str] = None,
        github_token: Optional[str] = None,
        timeout: int = 30
    ):
        self.templates_repo = templates_repo
        self.templates_branch = templates_branch
        self.local_path = Path(local_path)
        self.repo: Optional[git.Repo] = None

        self.gitlab_url = (gitlab_url or os.environ.get('GITLAB_URL', 'https://gitlab.com')).rstrip('/')
        self.gitlab_token = gitlab_token or os.environ.get('GITLAB_TOKEN')
        self.github_token = github_token or os.environ.get('GITHUB_TOKEN')
        self.timeout = timeout

        self._gitlab_client: Optional[httpx.AsyncClient] = None
        self._github_client: Optional[httpx.AsyncClient] = None

        self._project_id: Optional[str] = None

    async def _ensure_gitlab_client(self) -> httpx.AsyncClient:
        """Inicializa cliente GitLab de forma lazy"""
        if self._gitlab_client is None:
            self._gitlab_client = httpx.AsyncClient(
                base_url=f'{self.gitlab_url}/api/v4',
                headers={'PRIVATE-TOKEN': self.gitlab_token},
                timeout=self.timeout
            )
        return self._gitlab_client

    async def _ensure_github_client(self) -> httpx.AsyncClient:
        """Inicializa cliente GitHub de forma lazy"""
        if self._github_client is None:
            self._github_client = httpx.AsyncClient(
                base_url='https://api.github.com',
                headers={
                    'Authorization': f'Bearer {self.github_token}',
                    'Accept': 'application/vnd.github+json',
                    'X-GitHub-Api-Version': '2022-11-28'
                },
                timeout=self.timeout
            )
        return self._github_client

    def _extract_project_info(self, repo_url: str) -> tuple:
        """
        Extrai informações do projeto da URL

        Args:
            repo_url: URL do repositório

        Returns:
            Tuple (provider, owner, repo_name)
        """
        if 'gitlab' in repo_url.lower():
            provider = 'gitlab'
        elif 'github' in repo_url.lower():
            provider = 'github'
        else:
            provider = 'gitlab'

        parsed = urllib.parse.urlparse(repo_url)
        path_parts = parsed.path.strip('/').replace('.git', '').split('/')

        if len(path_parts) >= 2:
            owner = '/'.join(path_parts[:-1])
            repo_name = path_parts[-1]
        else:
            owner = path_parts[0] if path_parts else ''
            repo_name = ''

        return provider, owner, repo_name

    async def clone_templates_repo(self):
        """Clona repositório de templates localmente"""
        try:
            if self.local_path.exists():
                logger.info('templates_repo_already_exists', path=str(self.local_path))
                self.repo = git.Repo(self.local_path)
                await self.pull_latest()
            else:
                logger.info('cloning_templates_repo', repo=self.templates_repo)
                self.repo = git.Repo.clone_from(
                    self.templates_repo,
                    self.local_path,
                    branch=self.templates_branch
                )
                logger.info('templates_repo_cloned', path=str(self.local_path))

        except Exception as e:
            logger.error('clone_templates_repo_failed', error=str(e))
            raise

    async def pull_latest(self):
        """Atualiza templates com git pull"""
        if not self.repo:
            raise RuntimeError('Repositório não foi clonado')

        try:
            origin = self.repo.remotes.origin
            origin.pull(self.templates_branch)
            logger.info('templates_updated', branch=self.templates_branch)

        except Exception as e:
            logger.error('pull_latest_failed', error=str(e))
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def create_branch(self, repo_url: str, branch_name: str) -> str:
        """
        Cria branch para artefatos gerados

        Args:
            repo_url: URL do repositório
            branch_name: Nome da branch

        Returns:
            Nome da branch criada
        """
        provider, owner, repo_name = self._extract_project_info(repo_url)
        logger.info('creating_branch', provider=provider, branch=branch_name, repo=repo_url)

        try:
            if provider == 'gitlab':
                return await self._create_gitlab_branch(owner, repo_name, branch_name)
            else:
                return await self._create_github_branch(owner, repo_name, branch_name)

        except Exception as e:
            logger.error('create_branch_failed', branch=branch_name, error=str(e))
            raise

    async def _create_gitlab_branch(self, project_path: str, repo_name: str, branch_name: str) -> str:
        """Cria branch no GitLab"""
        client = await self._ensure_gitlab_client()
        project_id = urllib.parse.quote(f'{project_path}/{repo_name}', safe='')

        response = await client.post(
            f'/projects/{project_id}/repository/branches',
            json={'branch': branch_name, 'ref': 'main'}
        )

        if response.status_code == 400 and 'already exists' in response.text.lower():
            logger.info('branch_already_exists', branch=branch_name)
            return branch_name

        response.raise_for_status()
        logger.info('gitlab_branch_created', branch=branch_name)
        return branch_name

    async def _create_github_branch(self, owner: str, repo_name: str, branch_name: str) -> str:
        """Cria branch no GitHub"""
        client = await self._ensure_github_client()

        ref_response = await client.get(f'/repos/{owner}/{repo_name}/git/ref/heads/main')
        ref_response.raise_for_status()
        sha = ref_response.json().get('object', {}).get('sha')

        response = await client.post(
            f'/repos/{owner}/{repo_name}/git/refs',
            json={'ref': f'refs/heads/{branch_name}', 'sha': sha}
        )

        if response.status_code == 422 and 'Reference already exists' in response.text:
            logger.info('branch_already_exists', branch=branch_name)
            return branch_name

        response.raise_for_status()
        logger.info('github_branch_created', branch=branch_name)
        return branch_name

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def commit_artifacts(
        self,
        repo_url: str,
        branch: str,
        artifacts: List[Dict[str, Any]],
        message: str
    ) -> str:
        """
        Commit de artefatos gerados

        Args:
            repo_url: URL do repositório
            branch: Branch para commit
            artifacts: Lista de artefatos [{path, content}]
            message: Mensagem de commit

        Returns:
            SHA do commit
        """
        provider, owner, repo_name = self._extract_project_info(repo_url)
        logger.info('committing_artifacts', provider=provider, branch=branch, count=len(artifacts))

        try:
            if provider == 'gitlab':
                return await self._commit_gitlab_artifacts(owner, repo_name, branch, artifacts, message)
            else:
                return await self._commit_github_artifacts(owner, repo_name, branch, artifacts, message)

        except Exception as e:
            logger.error('commit_artifacts_failed', error=str(e))
            raise

    async def _check_gitlab_file_exists(
        self,
        client: httpx.AsyncClient,
        project_id: str,
        file_path: str,
        branch: str
    ) -> bool:
        """
        Verifica se arquivo existe no GitLab.

        Args:
            client: Cliente HTTP do GitLab
            project_id: ID do projeto (URL encoded)
            file_path: Caminho do arquivo
            branch: Branch para verificar

        Returns:
            True se o arquivo existe, False caso contrário
        """
        encoded_path = urllib.parse.quote(file_path, safe='')
        try:
            response = await client.get(
                f'/projects/{project_id}/repository/files/{encoded_path}',
                params={'ref': branch}
            )
            return response.status_code == 200
        except Exception:
            return False

    async def _commit_gitlab_artifacts(
        self,
        project_path: str,
        repo_name: str,
        branch: str,
        artifacts: List[Dict[str, Any]],
        message: str
    ) -> str:
        """Commit artefatos no GitLab"""
        client = await self._ensure_gitlab_client()
        project_id = urllib.parse.quote(f'{project_path}/{repo_name}', safe='')

        # Determinar ação (create ou update) para cada arquivo
        actions = []
        for artifact in artifacts:
            file_path = artifact.get('path')
            file_exists = await self._check_gitlab_file_exists(
                client, project_id, file_path, branch
            )
            action = 'update' if file_exists else 'create'
            actions.append({
                'action': action,
                'file_path': file_path,
                'content': artifact.get('content')
            })

        response = await client.post(
            f'/projects/{project_id}/repository/commits',
            json={
                'branch': branch,
                'commit_message': message,
                'actions': actions
            }
        )
        response.raise_for_status()

        commit_sha = response.json().get('id', '')
        logger.info('gitlab_commit_created', branch=branch, sha=commit_sha[:8])
        return commit_sha

    async def _commit_github_artifacts(
        self,
        owner: str,
        repo_name: str,
        branch: str,
        artifacts: List[Dict[str, Any]],
        message: str
    ) -> str:
        """Commit artefatos no GitHub usando Git Data API"""
        import base64
        client = await self._ensure_github_client()

        ref_response = await client.get(f'/repos/{owner}/{repo_name}/git/ref/heads/{branch}')
        ref_response.raise_for_status()
        base_sha = ref_response.json().get('object', {}).get('sha')

        commit_response = await client.get(f'/repos/{owner}/{repo_name}/git/commits/{base_sha}')
        commit_response.raise_for_status()
        base_tree_sha = commit_response.json().get('tree', {}).get('sha')

        tree_items = []
        for artifact in artifacts:
            blob_response = await client.post(
                f'/repos/{owner}/{repo_name}/git/blobs',
                json={
                    'content': base64.b64encode(artifact.get('content', '').encode()).decode(),
                    'encoding': 'base64'
                }
            )
            blob_response.raise_for_status()
            blob_sha = blob_response.json().get('sha')

            tree_items.append({
                'path': artifact.get('path'),
                'mode': '100644',
                'type': 'blob',
                'sha': blob_sha
            })

        tree_response = await client.post(
            f'/repos/{owner}/{repo_name}/git/trees',
            json={'base_tree': base_tree_sha, 'tree': tree_items}
        )
        tree_response.raise_for_status()
        new_tree_sha = tree_response.json().get('sha')

        commit_resp = await client.post(
            f'/repos/{owner}/{repo_name}/git/commits',
            json={
                'message': message,
                'tree': new_tree_sha,
                'parents': [base_sha]
            }
        )
        commit_resp.raise_for_status()
        new_commit_sha = commit_resp.json().get('sha')

        await client.patch(
            f'/repos/{owner}/{repo_name}/git/refs/heads/{branch}',
            json={'sha': new_commit_sha}
        )

        logger.info('github_commit_created', branch=branch, sha=new_commit_sha[:8])
        return new_commit_sha

    async def push_branch(self, repo_url: str, branch: str):
        """
        Push de branch para remote

        Para GitLab: após commit via API, branch já está no remote
        Para GitHub: após commit via API, branch já está no remote

        Args:
            repo_url: URL do repositório
            branch: Nome da branch
        """
        provider, _, _ = self._extract_project_info(repo_url)
        logger.info('branch_pushed', provider=provider, branch=branch)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def create_merge_request(
        self,
        repo_url: str,
        branch: str,
        title: str,
        description: str,
        target_branch: str = 'main'
    ) -> str:
        """
        Cria Merge Request no GitLab ou Pull Request no GitHub

        Args:
            repo_url: URL do repositório
            branch: Branch com alterações
            title: Título do MR/PR
            description: Descrição do MR/PR
            target_branch: Branch de destino

        Returns:
            URL do Merge Request/Pull Request criado
        """
        provider, owner, repo_name = self._extract_project_info(repo_url)
        logger.info('creating_merge_request', provider=provider, branch=branch)

        try:
            if provider == 'gitlab':
                return await self._create_gitlab_mr(owner, repo_name, branch, title, description, target_branch)
            else:
                return await self._create_github_pr(owner, repo_name, branch, title, description, target_branch)

        except Exception as e:
            logger.error('create_merge_request_failed', error=str(e))
            raise

    async def _create_gitlab_mr(
        self,
        project_path: str,
        repo_name: str,
        branch: str,
        title: str,
        description: str,
        target_branch: str
    ) -> str:
        """Cria Merge Request no GitLab"""
        client = await self._ensure_gitlab_client()
        project_id = urllib.parse.quote(f'{project_path}/{repo_name}', safe='')

        response = await client.post(
            f'/projects/{project_id}/merge_requests',
            json={
                'source_branch': branch,
                'target_branch': target_branch,
                'title': title,
                'description': description
            }
        )
        response.raise_for_status()

        mr_url = response.json().get('web_url', '')
        logger.info('gitlab_mr_created', branch=branch, url=mr_url)
        return mr_url

    async def _create_github_pr(
        self,
        owner: str,
        repo_name: str,
        branch: str,
        title: str,
        description: str,
        target_branch: str
    ) -> str:
        """Cria Pull Request no GitHub"""
        client = await self._ensure_github_client()

        response = await client.post(
            f'/repos/{owner}/{repo_name}/pulls',
            json={
                'head': branch,
                'base': target_branch,
                'title': title,
                'body': description
            }
        )
        response.raise_for_status()

        pr_url = response.json().get('html_url', '')
        logger.info('github_pr_created', branch=branch, url=pr_url)
        return pr_url

    async def close(self):
        """Fecha clientes HTTP"""
        if self._gitlab_client:
            await self._gitlab_client.aclose()
            self._gitlab_client = None

        if self._github_client:
            await self._github_client.aclose()
            self._github_client = None
