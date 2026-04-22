"""Teste E2E básico para Fluxo H."""

import asyncio

import pytest
from httpx import AsyncClient

from src.main import app


@pytest.mark.asyncio
async def test_fluxo_h_document_to_entities():
    """Testa fluxo completo: upload → parse → extract → entities persisted."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        # 1. Upload documento
        with open("tests/fixtures/sample.pdf", "rb") as f:
            response = await client.post(
                "/api/v1/documents/upload", data={"file": f, "uploaded_by": "test_user"}
            )
        assert response.status_code == 201
        document_id = response.json()["id"]

        # 2. Parse documento
        response = await client.post(f"/api/v1/documents/{document_id}/parse")
        assert response.status_code == 202

        # Aguardar parsing completar (poll)
        for _ in range(10):
            response = await client.get(f"/api/v1/documents/{document_id}/status")
            if response.json()["status"] in ["parsed", "extraction", "extracted"]:
                break
            await asyncio.sleep(1)

        # 3. Extrair entidades
        response = await client.post(f"/api/v1/documents/{document_id}/extract")
        assert response.status_code == 202

        # Aguardar extração completar
        for _ in range(20):
            response = await client.get(f"/api/v1/documents/{document_id}/status")
            if response.json()["status"] == "extracted":
                break
            await asyncio.sleep(1)

        # 4. Verificar entidades persistidas
        response = await client.get(f"/api/v1/documents/{document_id}/entities")
        assert response.status_code == 200
        entities = response.json()["entities"]
        assert len(entities) > 0
        assert all("id" in e for e in entities)

        # 5. Download documento
        response = await client.get(f"/api/v1/documents/{document_id}/download")
        assert response.status_code == 200
        assert len(response.content) > 0
