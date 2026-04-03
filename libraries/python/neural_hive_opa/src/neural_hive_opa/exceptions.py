"""
Exceções customizadas para OPA Client.

Todas as exceções específicas de integração com OPA.
"""


class OPAError(Exception):
    """Base exception para erros OPA."""


class OPAConnectionError(OPAError):
    """Erro de conexão com OPA."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class OPAPolicyNotFoundError(OPAError):
    """Política não encontrada (404)."""

    def __init__(self, policy_path: str, status_code: int = 404):
        self.policy_path = policy_path
        self.status_code = status_code
        super().__init__(f"Policy not found: {policy_path} (status: {status_code})")


class OPAEvaluationError(OPAError):
    """Erro na avaliação de política."""

    def __init__(self, message: str, policy: str | None = None):
        self.message = message
        self.policy = policy
        super().__init__(message)


class OPACircuitBreakerOpenError(OPAError):
    """Circuit breaker está aberto."""

    def __init__(self, message: str = "Circuit breaker is open"):
        self.message = message
        super().__init__(message)


class OPATimeoutError(OPAError):
    """Timeout na requisição OPA."""

    def __init__(self, message: str = "OPA request timeout"):
        self.message = message
        super().__init__(message)
