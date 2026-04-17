# Fluxo H Gaps Correction Implementation Plan

> **Para agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Corrigir gaps críticos e moderados identificados na revisão do Fluxo H para levar a implementação de 82% para 95% completo.

**Architecture:** Correções focadas em: (1) remover dependência incorreta, (2) implementar persistence de entidades, (3) adicionar endpoints de download e pause/resume, (4) padronizar versões de APIs.

**Tech Stack:** Python 3.12+, FastAPI, MongoDB, Kafka, Docker Compose

---

## Contexto da Revisão

A revisão do Fluxo H identificou os seguintes gaps que precisam de correção:

**Críticos (bloqueantes):**
1. Dependência `debezium-connector` incorreta no pyproject.toml
2. Falta de docker-compose para desenvolvimento local

**Moderados (funcionalidade):**
3. Entity persistence incompleta na coleção MongoDB `entities`
4. Endpoint de download de documentos ausente
5. Endpoints pause/resume para migrações ausentes

**Menores (consistência):**
6. Versões de APIs inconsistentes
7. Configurações LLM diferentes da spec

Este plano foca nos gaps 1, 3, 4 e 5. O gap 2 já foi resolvido com a criação do `docker-compose-fluxo-h.yml`.

---

## Estrutura de Ficheiros

**Ficheiros a modificar:**
- `services/data-migration/pyproject.toml` - Remover dependência incorreta
- `services/doc-ingestion/src/api/routers/parsing.py` - Adicionar entity persistence
- `services/doc-ingestion/src/api/routers/documents.py` - Adicionar endpoint download
- `services/data-migration/src/api/routers/migrations.py` - Adicionar endpoints pause/resume
- `services/doc-ingestion/src/config/settings.py` - Padronizar versão e configs LLM
- `services/data-migration/src/config/settings.py` - Padronizar versão (já está correta)

**Ficheiros a criar (já criados, apenas validar):**
- `docker-compose-fluxo-h.yml` - ✅ Já criado
- `scripts/init-legacy-db.sql` - ✅ Já criado
- `docs/FLUXO_H_REVIEW_FINAL.md` - ✅ Já criado
- `docs/FLUXO_H_SETUP.md` - ✅ Já criado

---

## Task 1: Remover Dependência Debezium Connector Incorreta

**Files:**
- Modify: `services/data-migration/pyproject.toml:36`

- [ ] **Step 1: Verificar dependência incorreta**

```bash
grep -n "debezium-connector" services/data-migration/pyproject.toml
```

Expected: Line 36 contains `debezium-connector = {path = "../../libraries/debezium-connector", develop = true}`

- [ ] **Step 2: Remover linha da dependência**

```bash
# Editar services/data-migration/pyproject.toml
# Remover linha 36:
# debezium-connector = {path = "../../libraries/debezium-connector", develop = true}
```

Edit using sed or manual editor:
```bash
sed -i '36d' services/data-migration/pyproject.toml
```

Or manually remove the line in your editor.

- [ ] **Step 3: Verificar que biblioteca não existe**

```bash
ls -la libraries/debezium-connector 2>&1 | head -5
```

Expected: "Library not found" or "No such file or directory"

- [ ] **Step 4: Validar sintaxe do pyproject.toml**

```bash
cd services/data-migration
poetry check
```

Expected: "All checks passed!"

- [ ] **Step 5: Commit**

```bash
git add services/data-migration/pyproject.toml
git commit -m "fix(data-migration): remove incorrect debezium-connector dependency

The Debezium CDC is configured via REST API (kafka-connect service)
not as a Python library. The CDC Pipeline already uses the correct approach.

Refs: docs/FLUXO_H_REVIEW_FINAL.md"
```

---

## Task 2: Implementar Entity Persistence

**Files:**
- Modify: `services/doc-ingestion/src/api/routers/parsing.py`
- Modify: `services/doc-ingestion/src/repositories/document_repository.py`
- Create: `services/doc-ingestion/src/repositories/entity_repository.py`
- Test: `services/doc-ingestion/tests/integration/test_entity_persistence.py`

- [ ] **Step 1: Write failing test para entity persistence**

Create `services/doc-ingestion/tests/integration/test_entity_persistence.py`:

```python
"""Testes de integração para entity persistence."""

import pytest
from httpx import AsyncClient
from src.main import app
from src.db.mongodb import get_mongodb_client


@pytest.mark.asyncio
async def test_extract_entities_persists_to_mongodb():
    """Testa que entidades extraídas são persistidas na coleção entities."""
    # Setup
    mongodb_client = await get_mongodb_client()
    await mongodb_client.connect()
    
    # Limpar coleção entities
    entities_collection = mongodb_client.db.get("entities")
    await entities_collection.delete_many({})
    
    # Criar documento de teste
    from src.models.document import DocumentCreate, DocumentFormat
    from src.repositories.document_repository import DocumentRepository
    
    repository = DocumentRepository()
    doc_create = DocumentCreate(
        filename="test.pdf",
        format=DocumentFormat.PDF,
        file_size_bytes=1024,
        s3_key="test/test.pdf",
        uploaded_by="test_user",
    )
    document = await repository.create(doc_create)
    
    # Extrair entidades
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            f"/api/v1/documents/{document.id}/parse",
        )
        assert response.status_code == 202
        
        response = await client.post(
            f"/api/v1/documents/{document.id}/extract",
            params={"min_confidence": 0.5}
        )
        assert response.status_code == 202
    
    # Verificar que entidades foram persistidas
    entities = await entities_collection.find({"document_id": document.id}).to_list(None)
    assert len(entities) > 0, "Entities should be persisted"
    assert entities[0].get("document_id") == document.id
    
    # Cleanup
    await entities_collection.delete_many({"document_id": document.id})
    await repository.delete(document.id)
    await mongodb_client.disconnect()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd services/doc-ingestion
pytest tests/integration/test_entity_persistence.py::test_extract_entities_persists_to_mongodb -v
```

Expected: FAIL with "entities should be persisted" (current implementation doesn't persist)

- [ ] **Step 3: Create EntityRepository**

Create `services/doc-ingestion/src/repositories/entity_repository.py`:

```python
"""Repositório para entidades extraídas."""

from datetime import datetime, timezone
from typing import List, Optional

from src.models.entities import ExtractedEntity
from src.db.mongodb import AsyncMongoDBClient


class EntityRepository:
    """Repositório para operações de CRUD de entidades."""

    def __init__(self, mongodb_client: AsyncMongoDBClient):
        """Inicializa repositório.

        Args:
            mongodb_client: Cliente MongoDB assíncrono
        """
        self.mongodb_client = mongodb_client
        self._collection = None

    @property
    def collection(self):
        """Retorna coleção de entidades (lazy initialization)."""
        if self._collection is None:
            self._collection = self.mongodb_client.db.get("entities")
        return self._collection

    async def create_many(
        self, entities: List[ExtractedEntity], document_id: str
    ) -> List[str]:
        """Cria múltiplas entidades.

        Args:
            entities: Lista de entidades a criar
            document_id: ID do documento origen

        Returns:
            Lista de IDs das entidades criadas
        """
        if not entities:
            return []

        documents = []
        for entity in entities:
            doc = {
                **entity.model_dump(),
                "document_id": document_id,
                "extracted_at": datetime.now(timezone.utc).isoformat(),
                "extracted_by": "entity_extractor",
            }
            documents.append(doc)

        result = await self.collection.insert_many(documents)
        return [str(id) for id in result.inserted_ids]

    async def list_by_document(
        self, document_id: str, entity_type: Optional[str] = None
    ) -> List[dict]:
        """Lista entidades de um documento.

        Args:
            document_id: ID do documento
            entity_type: Filtro opcional por tipo

        Returns:
            Lista de entidades
        """
        query = {"document_id": document_id}
        if entity_type:
            query["type"] = entity_type

        cursor = self.collection.find(query)
        entities = await cursor.to_list(length=None)
        return entities

    async def delete_by_document(self, document_id: str) -> int:
        """Deleta todas as entidades de um documento.

        Args:
            document_id: ID do documento

        Returns:
            Número de entidades deletadas
        """
        result = await self.collection.delete_many({"document_id": document_id})
        return result.deleted_count
```

- [ ] **Step 4: Update extract_entities endpoint para persistir entidades**

Modify `services/doc-ingestion/src/api/routers/parsing.py` (around line 240):

Add imports:
```python
from src.repositories.entity_repository import EntityRepository
```

Update the extract_entities function (around line 220):

```python
@router.post("/{document_id}/extract", status_code=status.HTTP_202_ACCEPTED)
async def extract_entities(
    document_id: str,
    min_confidence: float = Query(0.7, ge=0.0, le=1.0, description="Confiança mínima"),
    repository: DocumentRepository = Depends(get_repository),
):
    """Extrair entidades de documento já parseado."""
    job_id = str(uuid.uuid4())

    try:
        # Buscar documento
        document = await repository.get_by_id(document_id)
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document {document_id} not found",
            )

        # Verificar se documento foi parseado
        if not document.parsed_text:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Document must be parsed before entity extraction.",
            )

        # Atualizar status para extraction
        await repository.update_status(document_id, DocumentStatus.EXTRACTION)

        logger.info(
            "entity_extraction_started",
            document_id=document_id,
            job_id=job_id,
        )

        start_time = time.time()

        try:
            # Extrair entidades usando LLM
            extractor = EntityExtractor(min_confidence=min_confidence)
            entities = await extractor.extract(
                document_id=document_id,
                text=document.parsed_text,
                context={
                    "filename": document.filename,
                    "format": document.format.value,
                },
            )

            # ✅ ADICIONAR: Persistir entidades
            from src.db.mongodb import get_mongodb_client
            from src.repositories.entity_repository import EntityRepository

            mongodb_client = await get_mongodb_client()
            entity_repository = EntityRepository(mongodb_client)

            entity_ids = await entity_repository.create_many(
                entities=entities,
                document_id=document_id
            )

            logger.info(
                "entities_persisted",
                document_id=document_id,
                entity_count=len(entity_ids),
            )

            # Calcular tipos extraídos
            entity_types_set = {e.type.value for e in entities}
            entity_types_list = list(entity_types_set)

            # Atualizar documento com resultados
            await repository.update_extraction_results(
                document_id=document_id,
                entity_count=len(entities),
                extracted_entity_types=entity_types_list,
            )

            duration_ms = int((time.time() - start_time) * 1000)

            # Publicar evento Kafka
            producer = get_doc_producer()
            if producer:
                try:
                    await producer.publish_doc_entities_extracted(
                        document_id=document_id,
                        entity_count=len(entities),
                        entity_types=entity_types_list,
                        extraction_duration_ms=duration_ms,
                    )
                except Exception as e:
                    logger.warning("failed_to_publish_entities_event", error=str(e))

            return JSONResponse(
                status_code=status.HTTP_202_ACCEPTED,
                content={
                    "job_id": job_id,
                    "document_id": document_id,
                    "entity_count": len(entities),
                    "entity_types": entity_types_list,
                    "duration_ms": duration_ms,
                    "entities": [e.model_dump() for e in entities],
                    "message": "Entity extraction completed",
                },

        except Exception as e:
            logger.error("entity_extraction_failed", error=str(e))
            await repository.update_status(
                document_id, DocumentStatus.PARSED, error=f"Extraction failed: {str(e)}"
            )
            raise

    except HTTPException:
        raise
    except Exception as e:
        logger.error("extract_entities_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to extract entities: {str(e)}",
        )
```

- [ ] **Step 5: Update list_document_entities endpoint para usar EntityRepository**

Modify `services/doc-ingestion/src/api/routers/parsing.py` (around line 350):

```python
@router.get("/{document_id}/entities")
async def list_document_entities(
    document_id: str,
    entity_type: Optional[str] = Query(None, description="Filtrar por tipo de entidade"),
    repository: DocumentRepository = Depends(get_repository),
):
    """Listar entidades extraídas de um documento."""
    try:
        document = await repository.get_by_id(document_id)

        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document {document_id} not found",
            )

        if document.status != DocumentStatus.EXTRACTED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Document entities not extracted yet. Current status: {document.status.value}",
            )

        # ✅ ADICIONAR: Buscar entidades usando EntityRepository
        from src.db.mongodb import get_mongodb_client
        from src.repositories.entity_repository import EntityRepository

        mongodb_client = await get_mongodb_client()
        entity_repository = EntityRepository(mongodb_client)

        entities = await entity_repository.list_by_document(
            document_id=document_id,
            entity_type=entity_type
        )

        return {
            "document_id": document_id,
            "entity_count": len(entities),
            "entities": entities,
            "extracted_at": document.extracted_at.isoformat() if document.extracted_at else None,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("list_entities_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
```

- [ ] **Step 6: Run test to verify it passes**

```bash
cd services/doc-ingestion
pytest tests/integration/test_entity_persistence.py::test_extract_entities_persists_to_mongodb -v
```

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add services/doc-ingestion/src/repositories/entity_repository.py
git add services/doc-ingestion/src/api/routers/parsing.py
git add services/doc-ingestion/tests/integration/test_entity_persistence.py
git commit -m "feat(doc-ingestion): implement entity persistence in MongoDB

- Add EntityRepository for CRUD operations on entities collection
- Update extract_entities endpoint to persist entities
- Update list_document_entities to fetch from MongoDB
- Add integration test for entity persistence

Resolves: docs/FLUXO_H_REVIEW_FINAL.md Gap #3"
```

---

## Task 3: Adicionar Endpoint de Download de Documentos

**Files:**
- Modify: `services/doc-ingestion/src/api/routers/documents.py`
- Modify: `services/doc-ingestion/src/clients/s3_client.py`
- Test: `services/doc-ingestion/tests/integration/test_document_download.py`

- [ ] **Step 1: Write failing test para endpoint de download**

Create `services/doc-ingestion/tests/integration/test_document_download.py`:

```python
"""Testes de integração para endpoint de download."""

import pytest
from httpx import AsyncClient
from src.main import app


@pytest.mark.asyncio
async def test_download_document():
    """Testa download de documento armazenado no S3."""
    # Setup: criar documento de teste
    from src.models.document import DocumentCreate, DocumentFormat
    from src.repositories.document_repository import DocumentRepository
    from src.clients.s3_client import get_s3_client

    repository = DocumentRepository()
    doc_create = DocumentCreate(
        filename="test_download.pdf",
        format=DocumentFormat.PDF,
        file_size_bytes=1024,
        s3_key="test/test_download.pdf",
        uploaded_by="test_user",
    )
    document = await repository.create(doc_create)

    # Testar download
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(f"/api/v1/documents/{document.id}/download")

    assert response.status_code == 200
    assert response.content == b"test content"  # Conteúdo esperado
    assert "attachment" in response.headers.get("content-disposition", "")

    # Cleanup
    await repository.delete(document.id)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd services/doc-ingestion
pytest tests/integration/test_document_download.py::test_download_document -v
```

Expected: FAIL with "404 Not Found" (endpoint doesn't exist yet)

- [ ] **Step 3: Add download_file method to S3Client**

Modify `services/doc-ingestion/src/clients/s3_client.py`:

Add method to S3Client class:
```python
async def download_file(
    self, s3_key: str, return_metadata: bool = False
) -> bytes | tuple[bytes, str, str]:
    """Download file from S3/MinIO.

    Args:
        s3_key: Key do arquivo no S3
        return_metadata: Se True, retorna (content, filename, content_type)

    Returns:
        Conteúdo do arquivo ou tupla (content, filename, content_type)
    """
    try:
        response = await self._client.get_object(
            Bucket=self._bucket_name,
            Key=s3_key
        )

        content = await response["Body"].read()

        if return_metadata:
            filename = s3_key.split("/")[-1]
            content_type = response.get("ContentType", "application/octet-stream")
            return content, filename, content_type

        return content

    except Exception as e:
        self._logger.error("s3_download_failed", s3_key=s3_key, error=str(e))
        raise
```

- [ ] **Step 4: Add download endpoint to documents router**

Add to `services/doc-ingestion/src/api/routers/documents.py` (around line 430):

```python
@router.get("/{document_id}/download")
async def download_document(
    document_id: str,
    repository: DocumentRepository = Depends(get_repository),
):
    """Download do arquivo original do S3/MinIO.

    Args:
        document_id: ID do documento
        repository: Instância do repositório (injetado)

    Returns:
        Arquivo para download
    """
    try:
        document = await repository.get_by_id(document_id)

        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document {document_id} not found",
            )

        # Download do S3
        s3_client = await get_s3_client()
        file_content, filename, content_type = await s3_client.download_file(
            document.s3_key, return_metadata=True
        )

        from fastapi.responses import Response
        return Response(
            content=file_content,
            media_type=content_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("download_document_error", id=document_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to download document: {str(e)}",
        )
```

- [ ] **Step 5: Run test to verify it passes**

```bash
cd services/doc-ingestion
pytest tests/integration/test_document_download.py::test_download_document -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add services/doc-ingestion/src/api/routers/documents.py
git add services/doc-ingestion/src/clients/s3_client.py
git add services/doc-ingestion/tests/integration/test_document_download.py
git commit -m "feat(doc-ingestion): add document download endpoint

- Add download_file method to S3Client with metadata support
- Add GET /documents/{id}/download endpoint
- Add integration test for document download

Resolves: docs/FLUXO_H_REVIEW_FINAL.md Gap #4"
```

---

## Task 4: Adicionar Endpoints Pause/Resume para Migrações

**Files:**
- Modify: `services/data-migration/src/api/routers/migrations.py`
- Modify: `services/data-migration/src/services/migration_orchestrator.py`
- Test: `services/data-migration/tests/integration/test_migration_pause_resume.py`

- [ ] **Step 1: Write failing test para pause/resume**

Create `services/data-migration/tests/integration/test_migration_pause_resume.py`:

```python
"""Testes de integração para pause/resume de migrações."""

import pytest
from httpx import AsyncClient
from src.main import app


@pytest.mark.asyncio
async def test_pause_migration():
    """Testa pausar uma migração em andamento."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Criar job de migração
        response = await client.post(
            "/api/v1/migrations/jobs",
            json={
                "source_db": {"type": "postgresql", "host": "localhost", "database": "test"},
                "target_db": {"type": "mongodb", "connection_string": "mongodb://localhost"},
            }
        )
        job_id = response.json()["job_id"]

        # Pausar migração
        response = await client.post(f"/api/v1/migrations/jobs/{job_id}/pause")
        assert response.status_code == 200
        assert response.json()["status"] == "paused"


@pytest.mark.asyncio
async def test_resume_migration():
    """Testa retomar uma migração pausada."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Criar e pausar job
        response = await client.post("/api/v1/migrations/jobs", json={...})
        job_id = response.json()["job_id"]
        await client.post(f"/api/v1/migrations/jobs/{job_id}/pause")

        # Retomar migração
        response = await client.post(f"/api/v1/migrations/jobs/{job_id}/resume")
        assert response.status_code == 200
        assert response.json()["status"] == "running"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd services/data-migration
pytest tests/integration/test_migration_pause_resume.py -v
```

Expected: FAIL with "404 Not Found" (endpoints don't exist yet)

- [ ] **Step 3: Add pause_job method to MigrationOrchestrator**

Modify `services/data-migration/src/services/migration_orchestrator.py`:

Add method to MigrationOrchestrator class:
```python
async def pause_job(self, job_id: str) -> dict:
    """Pausa um job de migração em andamento.

    Args:
        job_id: ID do job

    Returns:
        Status atualizado do job

    Raises:
        ValueError: Se job não existe ou não pode ser pausado
    """
    job = await self.get_job(job_id)
    if not job:
        raise ValueError(f"Job {job_id} not found")

    if job.status not in ["running", "pending"]:
        raise ValueError(f"Job {job_id} cannot be paused (current status: {job.status})")

    # Atualizar status para paused
    job.status = "paused"
    job.paused_at = datetime.now(timezone.utc)
    job.paused_by = "user_request"

    # Publicar evento Kafka
    if self._producer:
        await self._producer.publish_migration_paused(
            job_id=job_id,
            reason="user_request"
        )

    await self._update_job(job)
    self._logger.info("migration_job_paused", job_id=job_id)

    return job.model_dump()

async def resume_job(self, job_id: str) -> dict:
    """Retoma um job de migração pausado.

    Args:
        job_id: ID do job

    Returns:
        Status atualizado do job

    Raises:
        ValueError: Se job não existe ou não pode ser retomado
    """
    job = await self.get_job(job_id)
    if not job:
        raise ValueError(f"Job {job_id} not found")

    if job.status != "paused":
        raise ValueError(f"Job {job_id} cannot be resumed (current status: {job.status})")

    # Atualizar status para running
    job.status = "running"
    job.resumed_at = datetime.now(timezone.utc)
    job.resumed_by = "user_request"

    # Publicar evento Kafka
    if self._producer:
        await self._producer.publish_migration_resumed(
            job_id=job_id,
            reason="user_request"
        )

    await self._update_job(job)
    self._logger.info("migration_job_resumed", job_id=job_id)

    return job.model_dump()
```

- [ ] **Step 4: Add pause/reserve endpoints to migrations router**

Add to `services/data-migration/src/api/routers/migrations.py`:

```python
@router.post("/{job_id}/pause")
async def pause_migration(
    job_id: str,
    reason: str = Query(None, description="Razão da pausa")
):
    """Pausa uma migração em andamento.

    Args:
        job_id: ID do job de migração
        reason: Razão opcional da pausa

    Returns:
        Status atualizado do job
    """
    try:
        from src.services.migration_orchestrator import get_migration_orchestrator

        orchestrator = get_migration_orchestrator()
        result = await orchestrator.pause_job(job_id)

        logger.info("migration_paused", job_id=job_id, reason=reason)

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "job_id": job_id,
                "status": "paused",
                "result": result,
                "message": "Migration paused successfully"
            }
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("pause_migration_error", job_id=job_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to pause migration: {str(e)}"
        )


@router.post("/{job_id}/resume")
async def resume_migration(
    job_id: str,
):
    """Retoma uma migração pausada.

    Args:
        job_id: ID do job de migração

    Returns:
        Status atualizado do job
    """
    try:
        from src.services.migration_orchestrator import get_migration_orchestrator

        orchestrator = get_migration_orchestrator()
        result = await orchestrator.resume_job(job_id)

        logger.info("migration_resumed", job_id=job_id)

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "job_id": job_id,
                "status": "running",
                "result": result,
                "message": "Migration resumed successfully"
            }
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("resume_migration_error", job_id=job_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to resume migration: {str(e)}"
        )
```

- [ ] **Step 5: Run test to verify it passes**

```bash
cd services/data-migration
pytest tests/integration/test_migration_pause_resume.py -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add services/data-migration/src/services/migration_orchestrator.py
git add services/data-migration/src/api/routers/migrations.py
git add services/data-migration/tests/integration/test_migration_pause_resume.py
git commit -m "feat(data-migration): add pause/resume endpoints for migrations

- Add pause_job and resume_job methods to MigrationOrchestrator
- Add POST /migrations/jobs/{id}/pause endpoint
- Add POST /migrations/jobs/{id}/resume endpoint
- Add integration tests for pause/resume functionality

Resolves: docs/FLUXO_H_REVIEW_FINAL.md Gap #5"
```

---

## Task 5: Padronizar Versões de APIs e Configurações

**Files:**
- Modify: `services/doc-ingestion/src/config/settings.py`

- [ ] **Step 1: Update versão da API**

```bash
# Editar services/doc-ingestion/src/config/settings.py line 21
# Alterar de api_version: str = "0.1.0"
# Para api_version: str = "1.0.0"
```

Edit:
```python
api_version: str = "1.0.0"
```

- [ ] **Step 2: Update configurações LLM**

```bash
# Editar services/doc-ingestion/src/config/settings.py lines 31-33
# Alterar llm_temperature de 0.7 para 0.3
# Alterar llm_max_tokens de 4000 para 8000
```

Edit:
```python
llm_temperature: float = 0.3
llm_max_tokens: int = 8000
```

- [ ] **Step 3: Verify settings format**

```bash
cd services/doc-ingestion
python -c "from src.config.settings import get_settings; s = get_settings(); print(f'Version: {s.api_version}, Temp: {s.llm_temperature}, Tokens: {s.llm_max_tokens}')"
```

Expected: "Version: 1.0.0, Temp: 0.3, Tokens: 8000"

- [ ] **Step 4: Test API health check**

```bash
# Se o serviço estiver rodando:
curl http://localhost:8018/health
```

Expected: Response contains `"version": "1.0.0"`

- [ ] **Step 5: Commit**

```bash
git add services/doc-ingestion/src/config/settings.py
git commit -m "fix(doc-ingestion): standardize API version and LLM configs

- Update api_version from 0.1.0 to 1.0.0
- Update llm_temperature from 0.7 to 0.3 (match spec)
- Update llm_max_tokens from 4000 to 8000 (match spec)

Resolves: docs/FLUXO_H_REVIEW_FINAL.md Gaps #6 and #7"
```

---

## Task 6: Validar docker-compose-fluxo-h.yml

**Files:**
- Validate: `docker-compose-fluxo-h.yml`
- Validate: `scripts/init-legacy-db.sql`

- [ ] **Step 1: Validate docker-compose syntax**

```bash
docker-compose -f docker-compose-fluxo-h.yml config
```

Expected: No syntax errors

- [ ] **Step 2: Test docker-compose build**

```bash
docker-compose -f docker-compose-fluxo-h.yml build
```

Expected: Images build successfully

- [ ] **Step 3: Test docker-compose up (dry-run)**

```bash
docker-compose -f docker-compose-fluxo-h.yml up --no-start
```

Expected: Containers created but not started

- [ ] **Step 4: Validate init script syntax**

```bash
# Validar SQL syntax
head -50 scripts/init-legacy-db.sql
```

Expected: Valid SQL syntax

- [ ] **Step 5: Create README para docker-compose**

Create `docs/FLUXO_H_SETUP.md` (already created, just validate):
```bash
ls -la docs/FLUXO_H_SETUP.md
```

Expected: File exists

- [ ] **Step 6: Commit (if any changes needed)**

If docker-compose or scripts needed adjustments:
```bash
git add docker-compose-fluxo-h.yml scripts/init-legacy-db.sql docs/FLUXO_H_SETUP.md
git commit -m "feat(fluxo-h): add docker-compose for local development

- Add complete docker-compose-fluxo-h.yml with all Fluxo H services
- Add init-legacy-db.sql script for PostgreSQL setup
- Add FLUXO_H_SETUP.md guide for local development

Resolves: docs/FLUXO_H_REVIEW_FINAL.md Gap #2"
```

---

## Task 7: Testes E2E para Validação

**Files:**
- Create: `services/doc-ingestion/tests/e2e/test_fluxo_h_basic_flow.py`

- [ ] **Step 1: Create E2E test para Fluxo H**

Create `services/doc-ingestion/tests/e2e/test_fluxo_h_basic_flow.py`:

```python
"""Teste E2E básico para Fluxo H."""

import pytest
import asyncio
from httpx import AsyncClient
from src.main import app


@pytest.mark.asyncio
async def test_fluxo_h_document_to_entities():
    """Testa fluxo completo: upload → parse → extract → entities persisted."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        # 1. Upload documento
        with open("tests/fixtures/sample.pdf", "rb") as f:
            response = await client.post(
                "/api/v1/documents/upload",
                data={"file": f, "uploaded_by": "test_user"}
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
```

- [ ] **Step 2: Run E2E test**

```bash
cd services/doc-ingestion
pytest tests/e2e/test_fluxo_h_basic_flow.py -v
```

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add services/doc-ingestion/tests/e2e/test_fluxo_h_basic_flow.py
git commit -m "test(doc-ingestion): add E2E test for Fluxo H basic flow

- Add end-to-end test covering upload → parse → extract → entities
- Validates entity persistence and document download
- Ensures all components work together correctly"
```

---

## Task 8: Atualizar Documentação

**Files:**
- Modify: `docs/FLUXO_H_REVIEW_FINAL.md`
- Modify: `docs/operations/fluxo-h-runbooks.md`

- [ ] **Step 1: Update review final com status corrigido**

Update `docs/FLUXO_H_REVIEW_FINAL.md` header:

Change: `**Status:** 82% Completo`

To: `**Status:** ✅ 95% Completo (após correções)`

- [ ] **Step 2: Adicionar secção de correções implementadas**

Add to `docs/FLUXO_H_REVIEW_FINAL.md`:

```markdown
## Correções Implementadas (2026-04-17)

### Gap #1: Dependência Debezium ✅
- **Resolvido:** Removida dependência incorreta do pyproject.toml
- **Commit:** feat(data-migration): remove incorrect debezium-connector dependency

### Gap #2: Docker Compose ✅
- **Resolvido:** docker-compose-fluxo-h.yml criado e validado
- **Commit:** feat(fluxo-h): add docker-compose for local development

### Gap #3: Entity Persistence ✅
- **Resolvido:** Implementado EntityRepository e persistência
- **Commit:** feat(doc-ingestion): implement entity persistence in MongoDB

### Gap #4: Download Endpoint ✅
- **Resolvido:** Endpoint GET /documents/{id}/download implementado
- **Commit:** feat(doc-ingestion): add document download endpoint

### Gap #5: Pause/Resume ✅
- **Resolvido:** Endpoints pause/resume implementados
- **Commit:** feat(data-migration): add pause/resume endpoints for migrations

### Gap #6-7: Configurações ✅
- **Resolvido:** Versões e configs LLM padronizadas
- **Commit:** fix(doc-ingestion): standardize API version and LLM configs
```

- [ ] **Step 3: Update runbooks com novos endpoints**

Update `docs/operations/fluxo-h-runbooks.md` to include:

- Exemplo de uso do endpoint de download
- Procedimento de pause/resume de migrações
- Comandos para validar entity persistence

- [ ] **Step 4: Commit**

```bash
git add docs/FLUXO_H_REVIEW_FINAL.md docs/operations/fluxo-h-runbooks.md
git commit -m "docs(fluxo-h): update documentation with implemented corrections

- Update FLUXO_H_REVIEW_FINAL.md status to 95% complete
- Add corrections implemented section
- Update runbooks with new endpoints and procedures"
```

---

## Task 9: Verificação Final

**Files:**
- Test: All modified services

- [ ] **Step 1: Run all tests Doc Ingestion**

```bash
cd services/doc-ingestion
pytest tests/ -v --cov=src
```

Expected: All tests pass, coverage > 70%

- [ ] **Step 2: Run all tests Data Migration**

```bash
cd services/data-migration
pytest tests/ -v --cov=src
```

Expected: All tests pass, coverage > 70%

- [ ] **Step 3: Linting check**

```bash
# Doc Ingestion
cd services/doc-ingestion
ruff check src/
black --check src/

# Data Migration
cd ../data-migration
ruff check src/
black --check src/
```

Expected: No linting errors

- [ ] **Step 4: Validate docker-compose**

```bash
cd ../..
docker-compose -f docker-compose-fluxo-h.yml config
docker-compose -f docker-compose-fluxo-h.yml build
```

Expected: No errors

- [ ] **Step 5: Create summary commit**

```bash
git add .
git commit -m "feat(fluxo-h): complete gaps correction - 95% implemented

All critical and moderate gaps from review have been addressed:
- ✅ Removed incorrect Debezium dependency
- ✅ Implemented entity persistence
- ✅ Added document download endpoint
- ✅ Added pause/resume endpoints for migrations
- ✅ Standardized API versions and LLM configs
- ✅ Validated docker-compose for local development
- ✅ Added E2E tests for basic flow

Fluxo H is now 95% complete and ready for production deployment.

Refs: docs/FLUXO_H_REVIEW_FINAL.md"
```

---

## Checklist de Conclusão

Após implementar todas as tarefas:

- [ ] Dependência Debezium removida
- [ ] Entity persistence implementada e testada
- [ ] Endpoint de download funcional
- [ ] Endpoints pause/resume funcionais
- [ ] Configurações padronizadas
- [ ] docker-compose validado
- [ ] Testes E2E passando
- [ ] Documentação atualizada
- [ ] Todos os testes unitários passando
- [ ] Todos os testes de integração passando
- [ ] Linting sem erros

---

## Tempo Estimado

- Task 1 (Debezium): 15 min
- Task 2 (Entity Persistence): 45 min
- Task 3 (Download Endpoint): 30 min
- Task 4 (Pause/Resume): 45 min
- Task 5 (Configs): 10 min
- Task 6 (Docker Compose): 20 min
- Task 7 (E2E Tests): 30 min
- Task 8 (Docs): 20 min
- Task 9 (Verificação): 30 min

**Total:** ~3 horas e 45 minutos

---

## Critérios de Sucesso

Após completar este plano:

1. ✅ Todos os testes unitários passam
2. ✅ Todos os testes de integração passam
3. ✅ Teste E2E do Fluxo H básico passa
4. ✅ Linting sem erros (ruff + black)
5. ✅ docker-compose inicia sem erros
6. ✅ Entities são persistidas no MongoDB
7. ✅ Documentos podem ser descarregados via API
8. ✅ Migrações podem ser pausadas e retomadas
9. ✅ Versões de APIs padronizadas
10. ✅ Configurações LLM seguem a spec

---

## Notas Importantes

1. **TDD:** Seguir o fluxo Test → Implementation → Commit
2. **Commits pequenos:** Cada passo deve ter seu próprio commit
3. **Validação frequente:** Rodar testes após cada tarefa
4. **Documentação em tempo real:** Atualizar docs conforme implementa

---

**Fim do plano de implementação.**
