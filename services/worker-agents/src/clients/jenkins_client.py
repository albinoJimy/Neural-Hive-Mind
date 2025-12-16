import httpx
import os
from typing import Dict, Optional
import structlog

logger = structlog.get_logger()


class JenkinsClient:
    """Cliente REST simplificado para Jenkins."""

    def __init__(self, base_url: str, token: str, user: Optional[str] = None, timeout: int = 600):
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.user = user or os.getenv('JENKINS_USER', '')
        self.client = httpx.AsyncClient(timeout=timeout, auth=(self.user, self.token))
        self.logger = logger.bind(service='jenkins_client')

    @classmethod
    def from_env(cls, config=None):
        base_url = os.getenv('JENKINS_URL') or getattr(config, 'jenkins_url', None)
        token = os.getenv('JENKINS_TOKEN') or getattr(config, 'jenkins_token', None)
        user = os.getenv('JENKINS_USER') or getattr(config, 'jenkins_user', None)
        if not base_url or not token:
            raise ValueError('Jenkins credentials not configured')
        return cls(base_url, token, user=user, timeout=getattr(config, 'jenkins_timeout_seconds', 600))

    async def trigger_job(self, job_name: str, parameters: Optional[Dict[str, str]] = None) -> int:
        url = f'{self.base_url}/job/{job_name}/buildWithParameters'
        resp = await self.client.post(url, params=parameters or {})
        resp.raise_for_status()
        queue_id = int(resp.headers.get('X-Queue-Id', 0))
        self.logger.info('jenkins_job_triggered', job=job_name, queue_id=queue_id)
        return queue_id

    async def get_build_status(self, job_name: str, build_number: int) -> Dict:
        url = f'{self.base_url}/job/{job_name}/{build_number}/api/json'
        resp = await self.client.get(url)
        resp.raise_for_status()
        return resp.json()

    async def get_test_report(self, job_name: str, build_number: int) -> Dict:
        url = f'{self.base_url}/job/{job_name}/{build_number}/testReport/api/json'
        resp = await self.client.get(url)
        resp.raise_for_status()
        return resp.json()
