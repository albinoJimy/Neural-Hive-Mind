"""
Helpers para testcontainers em testes de integracao.

Este modulo fornece funcoes utilitarias para iniciar containers Docker
que simulam servicos externos como ArgoCD, GitLab CI, OPA, etc.

Uso:
    Os helpers sao opcionais e podem ser usados quando testes de integracao
    mais realistas sao necessarios. Para testes rapidos, use os mocks puros
    definidos em conftest.py.

Requisitos:
    - Docker deve estar instalado e rodando
    - testcontainers>=3.7.1

Exemplo:
    ```python
    import pytest
    from fixtures.testcontainers_helpers import start_opa_container

    @pytest.fixture(scope='module')
    def opa_container():
        container = start_opa_container()
        yield container
        container.stop()
    ```
"""

import os
import json
import time
from typing import Optional, Dict, Any

try:
    from testcontainers.core.container import DockerContainer
    from testcontainers.core.waiting_utils import wait_for_logs
    TESTCONTAINERS_AVAILABLE = True
except ImportError:
    TESTCONTAINERS_AVAILABLE = False
    DockerContainer = None


def is_testcontainers_available() -> bool:
    """Verifica se testcontainers esta disponivel."""
    return TESTCONTAINERS_AVAILABLE


# ============================================
# OPA Container
# ============================================


def start_opa_container(
    image: str = 'openpolicyagent/opa:latest',
    port: int = 8181,
    policies_dir: Optional[str] = None
) -> Optional['DockerContainer']:
    """
    Inicia container OPA real com politicas de teste.

    Args:
        image: Imagem Docker do OPA
        port: Porta para expor a API OPA
        policies_dir: Diretorio com arquivos .rego para montar

    Returns:
        DockerContainer ou None se testcontainers nao disponivel

    Exemplo:
        ```python
        container = start_opa_container()
        opa_url = f'http://localhost:{container.get_exposed_port(8181)}'
        # ... executar testes ...
        container.stop()
        ```
    """
    if not TESTCONTAINERS_AVAILABLE:
        return None

    container = DockerContainer(image)
    container.with_exposed_ports(port)
    container.with_command('run --server')

    if policies_dir and os.path.isdir(policies_dir):
        container.with_volume_mapping(policies_dir, '/policies', 'ro')
        container.with_command('run --server --bundle /policies')

    container.start()

    # Aguardar OPA estar pronto
    _wait_for_http(container, port, '/health')

    return container


def get_opa_test_policy() -> str:
    """
    Retorna politica OPA de teste.

    Returns:
        String com politica Rego para testes
    """
    return '''
package policy

default allow = false

allow {
    input.user == "admin"
}

allow {
    input.action == "read"
}

violations[msg] {
    input.action == "delete"
    input.resource == "protected"
    msg := "Cannot delete protected resources"
}
'''


# ============================================
# ArgoCD Mock Container
# ============================================


def start_argocd_mock_container(
    image: str = 'nginx:alpine',
    port: int = 8080
) -> Optional['DockerContainer']:
    """
    Inicia container mock de ArgoCD API.

    Este container usa nginx para simular endpoints da API ArgoCD.
    Util para testes de integracao mais realistas.

    Args:
        image: Imagem Docker base
        port: Porta para expor a API

    Returns:
        DockerContainer ou None se testcontainers nao disponivel

    Nota:
        Para testes simples, prefira usar os mocks em conftest.py.
        Testcontainers e mais lento mas permite testar comportamento
        de rede real.
    """
    if not TESTCONTAINERS_AVAILABLE:
        return None

    # Configuracao nginx para mock
    nginx_conf = '''
server {
    listen 8080;

    location /api/v1/applications {
        if ($request_method = POST) {
            return 200 '{"metadata": {"name": "test-app"}}';
        }
        if ($request_method = GET) {
            return 200 '{"items": []}';
        }
    }

    location ~ /api/v1/applications/(.+) {
        return 200 '{"metadata": {"name": "$1"}, "status": {"health": {"status": "Healthy"}, "sync": {"status": "Synced"}}}';
    }

    location /health {
        return 200 '{"status": "ok"}';
    }
}
'''

    container = DockerContainer(image)
    container.with_exposed_ports(port)

    container.start()

    return container


# ============================================
# GitLab CI Mock Container
# ============================================


def start_gitlab_mock_container(
    image: str = 'nginx:alpine',
    port: int = 80
) -> Optional['DockerContainer']:
    """
    Inicia container mock de GitLab CI API.

    Args:
        image: Imagem Docker base
        port: Porta para expor a API

    Returns:
        DockerContainer ou None se testcontainers nao disponivel
    """
    if not TESTCONTAINERS_AVAILABLE:
        return None

    container = DockerContainer(image)
    container.with_exposed_ports(port)

    container.start()

    return container


# ============================================
# Docker-in-Docker Container
# ============================================


def start_dind_container(
    image: str = 'docker:dind',
    privileged: bool = True
) -> Optional['DockerContainer']:
    """
    Inicia container Docker-in-Docker para testes de execucao Docker.

    Args:
        image: Imagem Docker DinD
        privileged: Se deve rodar em modo privilegiado

    Returns:
        DockerContainer ou None se testcontainers nao disponivel

    Aviso:
        Containers privilegiados tem acesso total ao host.
        Use apenas em ambientes de teste controlados.
    """
    if not TESTCONTAINERS_AVAILABLE:
        return None

    container = DockerContainer(image)
    container.with_exposed_ports(2375)

    if privileged:
        container.with_kwargs(privileged=True)

    container.with_env('DOCKER_TLS_CERTDIR', '')

    container.start()

    # Aguardar Docker daemon estar pronto
    time.sleep(5)

    return container


# ============================================
# Helpers Utilitarios
# ============================================


def _wait_for_http(
    container: 'DockerContainer',
    port: int,
    path: str = '/',
    timeout: int = 30
) -> bool:
    """
    Aguarda endpoint HTTP estar disponivel.

    Args:
        container: Container Docker
        port: Porta interna do container
        path: Path do endpoint de health
        timeout: Timeout em segundos

    Returns:
        True se endpoint respondeu, False se timeout
    """
    import urllib.request
    import urllib.error

    exposed_port = container.get_exposed_port(port)
    host = container.get_container_host_ip()
    url = f'http://{host}:{exposed_port}{path}'

    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            response = urllib.request.urlopen(url, timeout=5)
            if response.status == 200:
                return True
        except (urllib.error.URLError, urllib.error.HTTPError):
            pass
        time.sleep(1)

    return False


def get_container_url(container: 'DockerContainer', port: int) -> str:
    """
    Retorna URL para acessar container.

    Args:
        container: Container Docker
        port: Porta interna do container

    Returns:
        URL no formato http://host:port
    """
    exposed_port = container.get_exposed_port(port)
    host = container.get_container_host_ip()
    return f'http://{host}:{exposed_port}'


# ============================================
# Pytest Fixtures Reutilizaveis
# ============================================


def create_opa_fixture():
    """
    Factory para criar fixture pytest de OPA.

    Uso:
        ```python
        # Em conftest.py
        from fixtures.testcontainers_helpers import create_opa_fixture

        opa_container = create_opa_fixture()
        ```
    """
    import pytest

    @pytest.fixture(scope='module')
    def opa_container():
        if not TESTCONTAINERS_AVAILABLE:
            pytest.skip('testcontainers not available')

        container = start_opa_container()
        yield container
        if container:
            container.stop()

    return opa_container


def create_dind_fixture():
    """
    Factory para criar fixture pytest de Docker-in-Docker.

    Uso:
        ```python
        # Em conftest.py
        from fixtures.testcontainers_helpers import create_dind_fixture

        dind_container = create_dind_fixture()
        ```
    """
    import pytest

    @pytest.fixture(scope='module')
    def dind_container():
        if not TESTCONTAINERS_AVAILABLE:
            pytest.skip('testcontainers not available')

        container = start_dind_container()
        yield container
        if container:
            container.stop()

    return dind_container
