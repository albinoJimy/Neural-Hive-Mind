"""
Fixtures para Schema Registry (Apicurio) em testes E2E.

Fornece clientes HTTP e mocks para validação de schemas Avro.
"""

import uuid
from typing import Dict, Optional

import httpx
import pytest


@pytest.fixture(scope="session")
async def schema_registry_client(k8s_service_endpoints: Dict[str, str]):
    """
    Cliente HTTP para Schema Registry (Apicurio).

    Usa endpoint real do cluster Kubernetes.
    """
    # Construir URL base para Schema Registry
    endpoint = k8s_service_endpoints.get("schema_registry", "")
    if not endpoint.startswith("http"):
        base_url = f"http://{endpoint}"
    else:
        base_url = endpoint

    async with httpx.AsyncClient(
        base_url=base_url,
        timeout=30.0,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.fixture(scope="function")
def schema_registry_mock():
    """
    Mock do Schema Registry para testes isolados.

    Simula API do Apicurio Registry (Confluent compatible).
    Registra schemas dinamicamente e retorna IDs.
    """
    schemas: Dict[str, Dict] = {}
    schema_id_counter = 1

    class SchemaRegistryMock:
        def __init__(self):
            self.schemas = schemas
            self._schema_id_counter = schema_id_counter

        def register_schema(self, subject: str, schema: Dict) -> int:
            """Registra um schema e retorna o ID."""
            schema_id = self._schema_id_counter
            self._schema_id_counter += 1

            if subject not in self.schemas:
                self.schemas[subject] = {"versions": []}

            version = len(self.schemas[subject]["versions"]) + 1
            self.schemas[subject]["versions"].append({
                "id": schema_id,
                "version": version,
                "schema": schema,
            })

            return schema_id

        def get_schema_by_id(self, schema_id: int) -> Optional[Dict]:
            """Busca schema por ID."""
            for subject_data in self.schemas.values():
                for version_data in subject_data["versions"]:
                    if version_data["id"] == schema_id:
                        return version_data["schema"]
            return None

        def get_subjects(self) -> list:
            """Lista todos os subjects registrados."""
            return list(self.schemas.keys())

        def get_versions(self, subject: str) -> list:
            """Lista versões de um subject."""
            if subject not in self.schemas:
                return []
            return [v["version"] for v in self.schemas[subject]["versions"]]

        def get_latest_schema(self, subject: str) -> Optional[Dict]:
            """Retorna o schema mais recente de um subject."""
            if subject not in self.schemas or not self.schemas[subject]["versions"]:
                return None
            return self.schemas[subject]["versions"][-1]

    return SchemaRegistryMock()


@pytest.fixture(scope="function")
def schema_registry_url(k8s_service_endpoints: Dict[str, str]) -> str:
    """
    URL do Schema Registry para uso em configurações de producer/consumer.
    """
    endpoint = k8s_service_endpoints.get("schema_registry", "")
    if not endpoint.startswith("http"):
        return f"http://{endpoint}"
    return endpoint
