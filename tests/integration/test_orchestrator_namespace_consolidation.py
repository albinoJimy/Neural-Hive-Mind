"""
Teste de Integração / Regressão — Consolidação de Namespaces do Orchestrator.

Spec: .agent-os/specs/2026-06-01-orchestrator-namespace-consolidation/

Este é um *config-contract test* DETERMINÍSTICO: não requer cluster Kubernetes
nem acesso à rede. Faz parse dos values.yaml versionados dos 3 clientes do
orchestrator-dynamic e garante que todos apontam para o endpoint canónico,
protegendo contra regressão da fragmentação de namespaces/portas que existia
antes da consolidação.

Contrato canónico (ADR em sub-specs/contract-decision.md):
  - Host: orchestrator-dynamic.neural-hive.svc.cluster.local
  - Porta: 50053 (gRPC, serviço OrchestratorStrategic)
  - TLS: false (insecure — SPIRE removido do cluster)

Autor: orchestrator-namespace-consolidation
Data: 2026-06-02
"""

from pathlib import Path

import pytest
import yaml

# ROOT do repositório: este ficheiro está em tests/integration/, logo parents[2].
REPO_ROOT = Path(__file__).resolve().parents[2]

# Contrato canónico decidido na ADR.
CANONICAL_HOST = "orchestrator-dynamic.neural-hive.svc.cluster.local"
CANONICAL_PORT = 50053

# Anti-padrões que NÃO podem voltar a aparecer no bloco orchestrator dos clientes.
DEAD_NAMESPACE = "neural-hive-orchestration"
WRONG_PORTS = (50051, 50052)

# Caminhos dos values.yaml versionados de cada cliente.
QUEEN_VALUES = REPO_ROOT / "helm-charts" / "queen-agent" / "values.yaml"
OPTIMIZER_VALUES = REPO_ROOT / "helm-charts" / "optimizer-agents" / "values.yaml"
SELF_HEALING_VALUES = REPO_ROOT / "helm-charts" / "self-healing-engine" / "values.yaml"


def _load_values(path):
    """Carrega e faz parse de um ficheiro values.yaml para dict."""
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@pytest.mark.integration()
class TestOrchestratorNamespaceConsolidation:
    """Garante que os 3 clientes apontam para o endpoint canónico do orchestrator."""

    def test_queen_agent_orchestrator_endpoint(self):
        """queen-agent: config.orchestrator.{grpcHost,grpcPort} == contrato canónico."""
        values = _load_values(QUEEN_VALUES)
        orchestrator = values["config"]["orchestrator"]

        assert orchestrator["grpcHost"] == CANONICAL_HOST
        assert orchestrator["grpcPort"] == CANONICAL_PORT

    def test_optimizer_agents_orchestrator_endpoint(self):
        """optimizer-agents: config.grpcClients.orchestrator.{host,port} == contrato canónico."""
        values = _load_values(OPTIMIZER_VALUES)
        orchestrator = values["config"]["grpcClients"]["orchestrator"]

        assert orchestrator["host"] == CANONICAL_HOST
        assert orchestrator["port"] == CANONICAL_PORT

    def test_self_healing_orchestrator_endpoint(self):
        """self-healing-engine: bloco config.orchestrator == contrato canónico."""
        values = _load_values(SELF_HEALING_VALUES)
        orchestrator = values["config"]["orchestrator"]

        assert orchestrator["grpcHost"] == CANONICAL_HOST
        assert orchestrator["grpcPort"] == CANONICAL_PORT
        # TLS insecure — SPIRE removido do cluster.
        assert orchestrator["useTls"] is False


def _orchestrator_blocks():
    """Devolve (id, bloco_orchestrator) de cada cliente para parametrização."""
    queen = _load_values(QUEEN_VALUES)["config"]["orchestrator"]
    optimizer = _load_values(OPTIMIZER_VALUES)["config"]["grpcClients"]["orchestrator"]
    self_healing = _load_values(SELF_HEALING_VALUES)["config"]["orchestrator"]
    return [
        ("queen-agent", queen),
        ("optimizer-agents", optimizer),
        ("self-healing-engine", self_healing),
    ]


# Calculado UMA vez ao importar o módulo: evita I/O dupla na colecção do pytest
# (o decorator @parametrize consome esta lista para os params e para os ids).
_ORCH_BLOCKS = _orchestrator_blocks()


@pytest.mark.integration()
class TestOrchestratorAntiPatterns:
    """Garante que nenhum cliente reintroduz os anti-padrões da fragmentação anterior.

    Nota de escopo: esta verificação cobre apenas o bloco ``config.orchestrator``
    (ou ``config.grpcClients.orchestrator``) de cada cliente. A referência ao
    namespace ``neural-hive-orchestration`` em ``config.executionTicketService``
    pertence a outro serviço (execution-ticket-service) e é dívida acompanhada
    fora desta spec.
    """

    @pytest.mark.parametrize(
        ("client_id", "block"),
        _ORCH_BLOCKS,
        ids=[client_id for client_id, _ in _ORCH_BLOCKS],
    )
    def test_no_dead_namespace_in_orchestrator_block(self, client_id, block):
        """O namespace morto neural-hive-orchestration não pode aparecer no bloco orchestrator."""
        host = block.get("grpcHost") or block.get("host")
        assert (
            DEAD_NAMESPACE not in host
        ), f"{client_id}: bloco orchestrator referencia namespace morto '{DEAD_NAMESPACE}'"

    @pytest.mark.parametrize(
        ("client_id", "block"),
        _ORCH_BLOCKS,
        ids=[client_id for client_id, _ in _ORCH_BLOCKS],
    )
    def test_no_wrong_ports_in_orchestrator_block(self, client_id, block):
        """As portas trocadas 50051/50052 não podem aparecer no bloco orchestrator."""
        port = block.get("grpcPort") or block.get("port")
        assert port is not None, f"{client_id}: bloco orchestrator sem chave de porta"
        assert (
            port not in WRONG_PORTS
        ), f"{client_id}: bloco orchestrator usa porta errada {port} (esperado {CANONICAL_PORT})"

    def test_self_healing_does_not_enable_tls(self):
        """self-healing-engine não pode reativar TLS (SPIRE removido do cluster)."""
        values = _load_values(SELF_HEALING_VALUES)
        # useTls deve ser o booleano False — nem True (reativaria TLS) nem None (ausente).
        assert (
            values["config"]["orchestrator"]["useTls"] is False
        ), "self-healing-engine: useTls deve ser o booleano False, não True nem None"


@pytest.mark.integration()
def test_self_healing_networkpolicy_egress_orchestrator_namespace():
    """A egress da NetworkPolicy do self-healing para a porta 50053 (orchestrator gRPC)
    deve selecionar o namespace canónico neural-hive (e NÃO orchestrator-dynamic).

    Nota: neste values, ``namespaceSelector.matchLabels`` é uma STRING
    (ex.: ``matchLabels: neural-hive``), não um dict.
    """
    values = _load_values(SELF_HEALING_VALUES)
    egress = values["networkPolicy"]["egress"]

    matching_rule = None
    for rule in egress:
        ports = rule.get("ports") or []
        if any(p.get("port") == CANONICAL_PORT for p in ports):
            matching_rule = rule
            break

    assert (
        matching_rule is not None
    ), f"NetworkPolicy egress não tem regra para a porta {CANONICAL_PORT} (orchestrator gRPC)"

    match_labels = matching_rule["namespaceSelector"]["matchLabels"]
    assert match_labels == "neural-hive", (
        f"egress da porta {CANONICAL_PORT} deve apontar para o namespace canónico "
        f"'neural-hive', mas aponta para '{match_labels}'"
    )
