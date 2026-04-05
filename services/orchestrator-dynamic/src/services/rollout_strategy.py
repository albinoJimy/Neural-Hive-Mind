"""
RolloutStrategy Engine para Feature Flags.

Implementa estratégias de rollout:
- gradual: Baseado em percentagem de tráfego (hash determinístico)
- whitelist: Lista de tenants permitidos
- canary: Lista de usuários permitidos
- all: Todos os usuários
"""
import hashlib
from typing import Any


class RolloutStrategy:
    """
    Engine de estratégias de rollout para feature flags.

    Avalia se uma flag deve estar ativa para um determinado contexto
    baseado na estratégia configurada.
    """

    @staticmethod
    def evaluate(flag: dict[str, Any], context: dict[str, Any]) -> bool:
        """
        Avalia se uma flag está ativa para o contexto fornecido.

        Args:
            flag: Dados da feature flag com rollout_strategy e rollout_config
            context: Contexto de avaliação (tenant_id, user_id, namespace, etc.)

        Returns:
            True se flag está ativa para o contexto, False caso contrário
        """
        strategy = flag.get("rollout_strategy", "all")
        config = flag.get("rollout_config", {})

        # Primeiro verificar filtro de namespace (comum a todas estratégias)
        if not RolloutStrategy._check_namespace(config, context):
            return False

        # Delegar para estratégia específica
        if strategy == "gradual":
            # Passar flag_name no config para hash determinístico
            config_with_flag = {**config, "flag_name": flag.get("flag_name", "")}
            return RolloutStrategy._evaluate_gradual(config_with_flag, context)
        if strategy == "whitelist":
            return RolloutStrategy._evaluate_whitelist(config, context)
        if strategy == "canary":
            return RolloutStrategy._evaluate_canary(config, context)
        if strategy == "all":
            return True
        # Estratégia desconhecida: safe default False
        return False

    @staticmethod
    def _check_namespace(config: dict[str, Any], context: dict[str, Any]) -> bool:
        """
        Verifica se o namespace está na lista de permitidos.

        Args:
            config: Configuração de rollout
            context: Contexto de avaliação

        Returns:
            True se namespace permitido ou sem restrição, False caso contrário
        """
        allowed_namespaces = config.get("namespaces", [])

        # Sem restrição de namespace
        if not allowed_namespaces:
            return True

        context_namespace = context.get("namespace")
        # Namespace não fornecido mas requerido
        if not context_namespace:
            return False

        return context_namespace in allowed_namespaces

    @staticmethod
    def _evaluate_gradual(config: dict[str, Any], context: dict[str, Any]) -> bool:
        """
        Avalia rollout gradual baseado em percentagem.

        Usa hash determinístico do tenant_id para garantir consistência:
        - Mesmo tenant sempre tem mesmo resultado
        - Distribuição uniforme baseada em percentage

        Args:
            config: Configuração com percentage (0-100)
            context: Contexto com tenant_id ou user_id

        Returns:
            True se hash do tenant está dentro do percentage
        """
        percentage = config.get("percentage", 0)

        # Obter identificador para hash
        identifier = context.get("tenant_id") or context.get("user_id")
        if not identifier:
            return False

        # Hash determinístico: MD5(identifier + flag_name) % 100
        flag_name = config.get("flag_name", "")
        hash_input = f"{identifier}:{flag_name}".encode()
        hash_value = int(hashlib.md5(hash_input).hexdigest(), 16)
        normalized = hash_value % 100

        return normalized < percentage

    @staticmethod
    def _evaluate_whitelist(config: dict[str, Any], context: dict[str, Any]) -> bool:
        """
        Avalia whitelist de tenants.

        Args:
            config: Configuração com whitelist (lista de tenant_ids)
            context: Contexto com tenant_id

        Returns:
            True se tenant_id está na whitelist
        """
        whitelist = config.get("whitelist", [])
        if not whitelist:
            return False

        tenant_id = context.get("tenant_id")
        if not tenant_id:
            return False

        return tenant_id in whitelist

    @staticmethod
    def _evaluate_canary(config: dict[str, Any], context: dict[str, Any]) -> bool:
        """
        Avalia canary release de usuários.

        Args:
            config: Configuração com canary_list (lista de user_ids)
            context: Contexto com user_id

        Returns:
            True se user_id está na canary_list
        """
        canary_list = config.get("canary_list", [])
        if not canary_list:
            return False

        user_id = context.get("user_id")
        if not user_id:
            return False

        return user_id in canary_list
