"""Cliente HTTP para integracao com Hypothesis Library API."""

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.config.settings import get_settings

logger = structlog.get_logger()


class HypothesisLibraryClientError(Exception):
    """Erro de chamada a API do Hypothesis Library."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class HypothesisLibraryTimeoutError(Exception):
    """Timeout em operacoes do Hypothesis Library."""


class HypothesisLibraryClient:
    """
    Cliente HTTP para Hypothesis Library API.

    Responsavel por criar hipoteses, iniciar testes e completar experimentos.
    """

    DEFAULT_BASE_URL = "http://hypothesis-library:8001"
    DEFAULT_TIMEOUT = 30

    def __init__(
        self,
        base_url: str | None = None,
        timeout: int = DEFAULT_TIMEOUT,
        retry_attempts: int = 3,
    ):
        """
        Inicializa cliente Hypothesis Library.

        Args:
            base_url: URL base do Hypothesis Library (default: settings.hypothesis_library_url ou DEFAULT_BASE_URL)
            timeout: Timeout padrao para requisicoes em segundos
            retry_attempts: Numero de tentativas em caso de falha
        """
        settings = get_settings()
        self.base_url = (
            base_url or getattr(settings, "hypothesis_library_url", self.DEFAULT_BASE_URL)
        ).rstrip("/")

        self.timeout = timeout
        self.retry_attempts = retry_attempts
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            verify=True,
        )
        self.logger = logger.bind(service="hypothesis_library_client")

    def _get_headers(self) -> dict[str, str]:
        """Retorna headers para requisicoes."""
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def close(self):
        """Fecha cliente HTTP."""
        await self.client.aclose()
        self.logger.info("hypothesis_library_client_closed")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(
            (httpx.HTTPStatusError, httpx.TimeoutException, httpx.ConnectError)
        ),
    )
    async def create_hypothesis(
        self,
        hypothesis_data: dict,
        author: str = "optimizer-agents",
    ) -> dict | None:
        """
        Cria nova hipotese no Hypothesis Library.

        Args:
            hypothesis_data: Dicionario com dados da hipotese (HypothesisCreate schema)
                - title: Titulo da hipotese
                - description: Descricao detalhada
                - expected_outcome: Resultado esperado
                - metrics: Lista de metricas afetadas
                - baseline_metrics: Metricas baseline atuais
                - target_metrics: Metricas target desejadas
                - priority: Prioridade (CRITICAL, HIGH, MEDIUM, LOW)
                - tags: Tags para categorizacao
                - requires_experiment: Se requer validacao via experimento
                - auto_approve: Aprovacao automatica
                - metadata: Metadados adicionais
            author: Autor da hipotese (default: "optimizer-agents")

        Returns:
            Dicionario com hipotese criada ou None se falhou

        Raises:
            HypothesisLibraryClientError: Erro na API
            HypothesisLibraryTimeoutError: Timeout na requisicao
        """
        self.logger.info(
            "create_hypothesis",
            title=hypothesis_data.get("title"),
            author=author,
        )

        try:
            response = await self.client.post(
                f"{self.base_url}/api/v1/hypotheses",
                json=hypothesis_data,
                params={"author": author},
                headers=self._get_headers(),
            )
            response.raise_for_status()

            result = response.json()
            self.logger.info(
                "hypothesis_created",
                hypothesis_id=result.get("hypothesis_id"),
                title=result.get("title"),
            )
            return result

        except httpx.HTTPStatusError as e:
            self.logger.error(
                "create_hypothesis_failed",
                status_code=e.response.status_code,
                error=str(e),
            )
            raise HypothesisLibraryClientError(
                f"Falha ao criar hipotese: {e}",
                status_code=e.response.status_code,
            )

        except httpx.TimeoutException as e:
            self.logger.error("create_hypothesis_timeout", error=str(e))
            raise HypothesisLibraryTimeoutError(f"Timeout ao criar hipotese: {e}")

        except Exception as e:
            self.logger.error("create_hypothesis_error", error=str(e))
            return None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(
            (httpx.HTTPStatusError, httpx.TimeoutException, httpx.ConnectError)
        ),
    )
    async def start_testing(
        self,
        hypothesis_id: str,
        experiment_id: str,
        started_by: str = "optimizer-agents",
    ) -> dict | None:
        """
        Inicia teste de hipotese.

        Transicao: APPROVED -> IN_TESTING

        Args:
            hypothesis_id: ID da hipotese
            experiment_id: ID do experimento criado no ExperimentationEngine
            started_by: Usuario/sistema que iniciou o teste

        Returns:
            Dicionario com hipotese e transicao realizados ou None se falhou

        Raises:
            HypothesisLibraryClientError: Erro na API
            HypothesisLibraryTimeoutError: Timeout na requisicao
        """
        self.logger.info(
            "start_testing",
            hypothesis_id=hypothesis_id,
            experiment_id=experiment_id,
            started_by=started_by,
        )

        try:
            response = await self.client.post(
                f"{self.base_url}/api/v1/hypotheses/{hypothesis_id}/start-test",
                json={"experiment_id": experiment_id},
                params={"started_by": started_by},
                headers=self._get_headers(),
            )
            response.raise_for_status()

            result = response.json()
            self.logger.info(
                "hypothesis_testing_started",
                hypothesis_id=hypothesis_id,
                experiment_id=experiment_id,
                status=result.get("hypothesis", {}).get("status"),
            )
            return result

        except httpx.HTTPStatusError as e:
            self.logger.error(
                "start_testing_failed",
                hypothesis_id=hypothesis_id,
                status_code=e.response.status_code,
                error=str(e),
            )
            raise HypothesisLibraryClientError(
                f"Falha ao iniciar teste da hipotese {hypothesis_id}: {e}",
                status_code=e.response.status_code,
            )

        except httpx.TimeoutException as e:
            self.logger.error(
                "start_testing_timeout",
                hypothesis_id=hypothesis_id,
                error=str(e),
            )
            raise HypothesisLibraryTimeoutError(
                f"Timeout ao iniciar teste da hipotese {hypothesis_id}: {e}"
            )

        except Exception as e:
            self.logger.error(
                "start_testing_error",
                hypothesis_id=hypothesis_id,
                error=str(e),
            )
            return None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(
            (httpx.HTTPStatusError, httpx.TimeoutException, httpx.ConnectError)
        ),
    )
    async def complete_testing(
        self,
        hypothesis_id: str,
        results: dict,
        completed_by: str = "optimizer-agents",
    ) -> dict | None:
        """
        Completa teste com resultados.

        Transicao: IN_TESTING -> COMPLETED

        Args:
            hypothesis_id: ID da hipotese
            results: Resultados do experimento (HypothesisResults schema)
                - experiment_id: ID do experimento
                - status: Status do experimento
                - outcome: Outcome (validated, refuted, inconclusive)
                - confidence_level: Nivel de confianca estatistica (0.0-1.0)
                - improvement_percentage: Melhoria observada
                - statistical_significance: Significancia estatistica
                - actual_baseline_metrics: Metricas baseline observadas
                - actual_target_metrics: Metricas target observadas
                - lessons_learned: Aprendizados do experimento
                - completed_at: Data de conclusao
            completed_by: Usuario/sistema que completou o teste

        Returns:
            Dicionario com hipotese e transicao realizados ou None se falhou

        Raises:
            HypothesisLibraryClientError: Erro na API
            HypothesisLibraryTimeoutError: Timeout na requisicao
        """
        self.logger.info(
            "complete_testing",
            hypothesis_id=hypothesis_id,
            outcome=results.get("outcome"),
            confidence_level=results.get("confidence_level"),
            completed_by=completed_by,
        )

        try:
            response = await self.client.post(
                f"{self.base_url}/api/v1/hypotheses/{hypothesis_id}/complete",
                json=results,
                params={"completed_by": completed_by},
                headers=self._get_headers(),
            )
            response.raise_for_status()

            result = response.json()
            self.logger.info(
                "hypothesis_testing_completed",
                hypothesis_id=hypothesis_id,
                outcome=results.get("outcome"),
                status=result.get("hypothesis", {}).get("status"),
            )
            return result

        except httpx.HTTPStatusError as e:
            self.logger.error(
                "complete_testing_failed",
                hypothesis_id=hypothesis_id,
                status_code=e.response.status_code,
                error=str(e),
            )
            raise HypothesisLibraryClientError(
                f"Falha ao completar teste da hipotese {hypothesis_id}: {e}",
                status_code=e.response.status_code,
            )

        except httpx.TimeoutException as e:
            self.logger.error(
                "complete_testing_timeout",
                hypothesis_id=hypothesis_id,
                error=str(e),
            )
            raise HypothesisLibraryTimeoutError(
                f"Timeout ao completar teste da hipotese {hypothesis_id}: {e}"
            )

        except Exception as e:
            self.logger.error(
                "complete_testing_error",
                hypothesis_id=hypothesis_id,
                error=str(e),
            )
            return None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(
            (httpx.HTTPStatusError, httpx.TimeoutException, httpx.ConnectError)
        ),
    )
    async def get_hypothesis(self, hypothesis_id: str) -> dict | None:
        """
        Busca hipotese por ID.

        Args:
            hypothesis_id: ID da hipotese

        Returns:
            Dicionario com hipotese e transicoes permitidas ou None se nao encontrado

        Raises:
            HypothesisLibraryClientError: Erro na API
            HypothesisLibraryTimeoutError: Timeout na requisicao
        """
        self.logger.info("get_hypothesis", hypothesis_id=hypothesis_id)

        try:
            response = await self.client.get(
                f"{self.base_url}/api/v1/hypotheses/{hypothesis_id}",
                params={"role": "author"},
                headers=self._get_headers(),
            )

            if response.status_code == 404:
                self.logger.warning(
                    "hypothesis_not_found",
                    hypothesis_id=hypothesis_id,
                )
                return None

            response.raise_for_status()
            result = response.json()

            self.logger.debug(
                "hypothesis_retrieved",
                hypothesis_id=hypothesis_id,
                status=result.get("hypothesis", {}).get("status"),
            )
            return result

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None

            self.logger.error(
                "get_hypothesis_failed",
                hypothesis_id=hypothesis_id,
                status_code=e.response.status_code,
                error=str(e),
            )
            raise HypothesisLibraryClientError(
                f"Falha ao buscar hipotese {hypothesis_id}: {e}",
                status_code=e.response.status_code,
            )

        except httpx.TimeoutException as e:
            self.logger.error(
                "get_hypothesis_timeout",
                hypothesis_id=hypothesis_id,
                error=str(e),
            )
            raise HypothesisLibraryTimeoutError(f"Timeout ao buscar hipotese {hypothesis_id}: {e}")

        except Exception as e:
            self.logger.error(
                "get_hypothesis_error",
                hypothesis_id=hypothesis_id,
                error=str(e),
            )
            return None

    async def health_check(self) -> bool:
        """
        Verifica se o Hypothesis Library esta saudavel.

        Returns:
            True se Hypothesis Library esta respondendo
        """
        try:
            response = await self.client.get(
                f"{self.base_url}/api/v1/hypotheses/aggregations",
                headers=self._get_headers(),
            )
            is_healthy = response.status_code == 200
            self.logger.debug(
                "health_check",
                healthy=is_healthy,
                status_code=response.status_code,
            )
            return is_healthy
        except Exception as e:
            self.logger.warning("health_check_failed", error=str(e))
            return False
