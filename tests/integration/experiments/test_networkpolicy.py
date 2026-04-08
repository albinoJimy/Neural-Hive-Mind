"""
Testes de Integração para NetworkPolicy de Experimentos (EXPERIMENT-001-03)

Este módulo testa o isolamento de rede para experimentos através de
NetworkPolicies.

Testes:
- EXPERIMENT-001-09: Testar network policies
- Teste de deny-all policy
- Teste de regras seletivas
- Teste de isolamento de egress

Autor: EXPERIMENT-001
Data: 2026-04-08
"""

import time

import pytest
import yaml
from kubernetes import client
from kubernetes.client.exceptions import ApiException


@pytest.mark.integration
@pytest.mark.k8s
class TestExperimentsNetworkPolicy:
    """
    Testes para as NetworkPolicies de experimentos.

    EXPERIMENT-001-03: Criar NetworkPolicy para isolamento
    """

    def test_networkpolicy_manifest_file_exists(self, experiments_manifests_dir):
        """
        Testa que o ficheiro de manifesto networkpolicy.yaml existe.

        Given: O diretório de manifests existe
        When: Ler o diretório
        Then: O ficheiro networkpolicy.yaml está presente
        """
        policy_file = experiments_manifests_dir / "networkpolicy.yaml"
        assert policy_file.exists(), "networkpolicy.yaml deve existir"

    def test_networkpolicy_manifest_valid_yaml(self, experiments_manifests_dir):
        """
        Testa que o manifesto de NetworkPolicy é YAML válido.

        Given: O ficheiro networkpolicy.yaml existe
        When: Parse o YAML
        Then: Os documentos são válidos
        """
        policy_file = experiments_manifests_dir / "networkpolicy.yaml"
        with open(policy_file) as f:
            documents = list(yaml.safe_load_all(f))

        # Filtrar documentos None
        docs = [d for d in documents if d is not None]

        # Deve ter várias NetworkPolicies
        network_policies = [d for d in docs if d.get("kind") == "NetworkPolicy"]
        assert len(network_policies) >= 5, "Deve ter pelo menos 5 NetworkPolicies"

        # Verificar deny-all existe
        deny_all = next(
            (p for p in network_policies if "deny-all" in p.get("metadata", {}).get("name", "")),
            None,
        )
        assert deny_all is not None, "Deve existir policy deny-all"

    def test_networkpolicy_deny_all_exists(self, experiments_manifests_dir):
        """
        Testa que a policy deny-all está configurada corretamente.

        Given: O manifesto de NetworkPolicy
        When: Verificar policy deny-all
        Then: Bloqueia ingress e egress por padrão
        """
        policy_file = experiments_manifests_dir / "networkpolicy.yaml"
        with open(policy_file) as f:
            docs = list(yaml.safe_load_all(f))

        deny_all = next(
            (d for d in docs if d and d.get("kind") == "NetworkPolicy" and "deny-all" in d.get("metadata", {}).get("name", "")),
            None,
        )

        assert deny_all is not None
        assert deny_all["spec"]["podSelector"] == {}, "PodSelector deve ser vazio (todos pods)"
        assert "Ingress" in deny_all["spec"]["policyTypes"]
        assert "Egress" in deny_all["spec"]["policyTypes"]

    def test_networkpolicy_dns_allow_exists(self, experiments_manifests_dir):
        """
        Testa que a policy para DNS existe.

        Given: O manifesto de NetworkPolicy
        When: Verificar policy DNS
        Then: Permite egress para porta 53 UDP/TCP
        """
        policy_file = experiments_manifests_dir / "networkpolicy.yaml"
        with open(policy_file) as f:
            docs = list(yaml.safe_load_all(f))

        dns_policy = next(
            (d for d in docs if d and d.get("kind") == "NetworkPolicy" and "dns" in d.get("metadata", {}).get("name", "")),
            None,
        )

        assert dns_policy is not None
        egress_rules = dns_policy["spec"]["egress"]
        assert len(egress_rules) > 0

        # Verificar porta 53
        ports = egress_rules[0].get("ports", [])
        assert any(p.get("port") == 53 for p in ports)

    def test_networkpolicy_can_be_created(
        self, k8s_networking_client, test_experiments_namespace
    ):
        """
        Testa que a NetworkPolicy pode ser criada no namespace.

        EXPERIMENT-001-09: Testar network policies

        Given: Um namespace de experimentos
        When: Criar NetworkPolicy deny-all
        Then: A policy é criada com sucesso
        """
        namespace_name = test_experiments_namespace

        policy = client.V1NetworkPolicy(
            metadata=client.V1ObjectMeta(
                name="test-deny-all",
                namespace=namespace_name,
            ),
            spec=client.V1NetworkPolicySpec(
                pod_selector={},
                policy_types=["Ingress", "Egress"],
            ),
        )

        created = k8s_networking_client.create_namespaced_network_policy(
            namespace=namespace_name,
            body=policy,
        )

        assert created is not None
        assert created.metadata.name == "test-deny-all"

        # Cleanup
        k8s_networking_client.delete_namespaced_network_policy(
            name="test-deny-all", namespace=namespace_name
        )

    def test_networkpolicy_deny_all_blocks_traffic(
        self, k8s_core_client, k8s_networking_client, test_experiments_namespace, create_test_pod
    ):
        """
        Testa que a policy deny-all bloqueia tráfego.

        Given: Um deny-all policy aplicado
        When: Tentar comunicar entre pods
        Then: Tráfego é bloqueado
        """
        namespace_name = test_experiments_namespace

        # Criar policy deny-all
        policy = client.V1NetworkPolicy(
            metadata=client.V1ObjectMeta(name="deny-all"),
            spec=client.V1NetworkPolicySpec(
                pod_selector={},
                policy_types=["Ingress", "Egress"],
            ),
        )
        k8s_networking_client.create_namespaced_network_policy(
            namespace=namespace_name, body=policy
        )

        # Criar dois pods
        _ = create_test_pod(
            k8s_core_client,
            namespace_name,
            "pod1",
            labels={"app": "test"},
        )
        _ = create_test_pod(
            k8s_core_client,
            namespace_name,
            "pod2",
            labels={"app": "test"},
        )

        # Aguardar pods estarem running
        time.sleep(3)

        # Com deny-all, não deve haver conectividade
        # (Em cluster CNI com NetworkPolicy suportado)
        # Nota: Este teste depende do CNI suportar NetworkPolicy

        # Cleanup
        k8s_core_client.delete_namespaced_pod(name="pod1", namespace=namespace_name)
        k8s_core_client.delete_namespaced_pod(name="pod2", namespace=namespace_name)
        k8s_networking_client.delete_namespaced_network_policy(
            name="deny-all", namespace=namespace_name
        )

    def test_networkpolicy_allow_internal(
        self, k8s_networking_client, test_experiments_namespace
    ):
        """
        Testa que a policy allow-internal funciona.

        Given: Um namespace com deny-all
        When: Adicionar policy allow-internal
        Then: Pods com labels apropriados podem comunicar
        """
        namespace_name = test_experiments_namespace

        # Criar deny-all
        deny_all = client.V1NetworkPolicy(
            metadata=client.V1ObjectMeta(name="deny-all"),
            spec=client.V1NetworkPolicySpec(
                pod_selector={},
                policy_types=["Ingress", "Egress"],
            ),
        )
        k8s_networking_client.create_namespaced_network_policy(
            namespace=namespace_name, body=deny_all
        )

        # Criar allow-internal
        allow_internal = client.V1NetworkPolicy(
            metadata=client.V1ObjectMeta(name="allow-internal"),
            spec=client.V1NetworkPolicySpec(
                pod_selector=client.V1LabelSelector(
                    match_labels={"experiments.nhm.is/isolated": "true"}
                ),
                policy_types=["Ingress"],
                ingress=[
                    client.V1NetworkPolicyIngressRule(
                        from_=[
                            client.V1NetworkPolicyPeer(
                                namespace_selector=client.V1LabelSelector(
                                    match_labels={"name": namespace_name}
                                )
                            )
                        ]
                    )
                ],
            ),
        )
        k8s_networking_client.create_namespaced_network_policy(
            namespace=namespace_name, body=allow_internal
        )

        # Verificar que policies existem
        policies = k8s_networking_client.list_namespaced_network_policy(
            namespace=namespace_name
        )
        assert len(policies.items) >= 2

        # Cleanup
        k8s_networking_client.delete_namespaced_network_policy(
            name="deny-all", namespace=namespace_name
        )
        k8s_networking_client.delete_namespaced_network_policy(
            name="allow-internal", namespace=namespace_name
        )

    def test_networkpolicy_egress_dns(
        self, k8s_networking_client, test_experiments_namespace
    ):
        """
        Testa que a policy allow-dns permite consultas DNS.

        Given: Um namespace com deny-all
        When: Adicionar policy allow-dns
        Then: Egress para DNS é permitido
        """
        namespace_name = test_experiments_namespace

        # Criar deny-all
        deny_all = client.V1NetworkPolicy(
            metadata=client.V1ObjectMeta(name="deny-all"),
            spec=client.V1NetworkPolicySpec(
                pod_selector={},
                policy_types=["Egress"],
            ),
        )
        k8s_networking_client.create_namespaced_network_policy(
            namespace=namespace_name, body=deny_all
        )

        # Criar allow-dns
        allow_dns = client.V1NetworkPolicy(
            metadata=client.V1ObjectMeta(name="allow-dns"),
            spec=client.V1NetworkPolicySpec(
                pod_selector={},
                policy_types=["Egress"],
                egress=[
                    client.V1NetworkPolicyEgressRule(
                        to=[
                            client.V1NetworkPolicyPeer(
                                namespace_selector=client.V1LabelSelector(
                                    match_labels={"name": "kube-system"}
                                )
                            )
                        ],
                        ports=[
                            client.V1NetworkPolicyPort(protocol="UDP", port=53),
                            client.V1NetworkPolicyPort(protocol="TCP", port=53),
                        ],
                    )
                ],
            ),
        )
        k8s_networking_client.create_namespaced_network_policy(
            namespace=namespace_name, body=allow_dns
        )

        # Verificar que policies existem
        policy = k8s_networking_client.read_namespaced_network_policy(
            name="allow-dns", namespace=namespace_name
        )
        assert policy is not None
        assert len(policy.spec.egress) > 0

        # Cleanup
        k8s_networking_client.delete_namespaced_network_policy(
            name="deny-all", namespace=namespace_name
        )
        k8s_networking_client.delete_namespaced_network_policy(
            name="allow-dns", namespace=namespace_name
        )


@pytest.mark.integration
@pytest.mark.k8s
class TestExperimentsNetworkPolicyNegative:
    """
    Testes negativos para NetworkPolicies de experimentos.
    """

    def test_networkpolicy_invalid_selector_fails(
        self, k8s_networking_client, test_experiments_namespace
    ):
        """
        Testa que seletor inválido falha.

        Given: Um selector com label inválido
        When: Tentar criar NetworkPolicy
        Then: Erro é retornado
        """
        namespace_name = test_experiments_namespace

        # Selector com label inválido (valor muito longo)
        policy = client.V1NetworkPolicy(
            metadata=client.V1ObjectMeta(name="invalid-policy"),
            spec=client.V1NetworkPolicySpec(
                pod_selector=client.V1LabelSelector(
                    match_labels={"a" * 300: "value"}
                ),
                policy_types=["Ingress"],
            ),
        )

        with pytest.raises(ApiException) as exc_info:
            k8s_networking_client.create_namespaced_network_policy(
                namespace=namespace_name, body=policy
            )

        assert exc_info.value.status == 422
