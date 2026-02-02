"""Adapters para integracao com bibliotecas externas."""

# Import lazy para evitar falha quando neural_hive_specialists nao esta instalado
# A funcao create_feedback_collector_config levanta ImportError se chamada sem a dependencia

__all__ = ['create_feedback_collector_config']


def __getattr__(name: str):
    """Lazy import para evitar falha de modulo ausente."""
    if name == 'create_feedback_collector_config':
        from .feedback_config_adapter import create_feedback_collector_config
        return create_feedback_collector_config
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
