"""
Testes unitarios para o fail-fast de MONGODB_DATABASE explicito.

Convergencia DBs (Fase 5, Task 8.1): em ambiente de deployment real,
MONGODB_DATABASE tem de ser definido explicitamente — elimina o default implicito
'neural_hive' que gerou o drift que partiu o pipeline (f786fb16/6fddd01d).

Testa-se a funcao pura ``require_mongodb_database_explicit`` (o validator de Settings
salta sob pytest por desenho, por isso a logica esta extraida para ser testavel sem
depender desse guard). NAO toca em conftest.py nem em testes existentes.
"""

import pytest
from src.config.settings import require_mongodb_database_explicit


class TestRequireMongodbDatabaseExplicit:
    @pytest.mark.parametrize("environment", ["production", "prod", "staging", "development", "dev"])
    def test_raises_em_deployment_sem_env_explicito(self, environment):
        """Ambiente real + MONGODB_DATABASE ausente + fora de pytest -> falha-fast."""
        with pytest.raises(ValueError, match="MONGODB_DATABASE"):
            require_mongodb_database_explicit(environment, explicit=False, under_pytest=False)

    @pytest.mark.parametrize("environment", ["production", "staging", "development"])
    def test_ok_quando_env_explicito(self, environment):
        """Ambiente real + MONGODB_DATABASE definido explicitamente -> nao falha."""
        require_mongodb_database_explicit(environment, explicit=True, under_pytest=False)

    @pytest.mark.parametrize("environment", ["test", "local", "TEST", "Local"])
    def test_ok_em_test_local_mesmo_sem_env(self, environment):
        """Ambiente test/local mantem o default (nao quebra testes/CI)."""
        require_mongodb_database_explicit(environment, explicit=False, under_pytest=False)

    def test_ok_sob_pytest_mesmo_em_producao_sem_env(self):
        """Sob pytest nunca falha (coleta/instanciacao de Settings em CI nao quebra)."""
        require_mongodb_database_explicit("production", explicit=False, under_pytest=True)
