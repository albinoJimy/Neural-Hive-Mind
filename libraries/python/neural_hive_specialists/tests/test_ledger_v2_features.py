"""
Testes para novas funcionalidades do Ledger V2.

Testa:
- DigitalSigner (geração, verificação, detecção de adulteração)
- SchemaVersionManager e validação OpinionDocumentV2
- LedgerClient.save_opinion com assinatura digital e verify_document_integrity
- LedgerQueryAPI (get_opinions_by_domain, get_opinions_by_feature)
"""

import pytest
import uuid
import json
from datetime import datetime
from typing import Dict, Any
from unittest.mock import Mock, patch, MagicMock

from neural_hive_specialists.config import SpecialistConfig
from neural_hive_specialists.ledger import (
    DigitalSigner,
    SchemaVersionManager,
    OpinionDocumentV2,
    Opinion,
    ReasoningFactor,
    Mitigation,
)
from neural_hive_specialists.ledger_client import LedgerClient
from neural_hive_specialists.ledger.query_api import LedgerQueryAPI


class TestDigitalSigner:
    """Testes unitários para DigitalSigner."""

    @pytest.fixture
    def signer_config(self, tmp_path):
        """Configuração para signer com chaves temporárias."""
        private_key_path = tmp_path / "test_private_key.pem"
        public_key_path = tmp_path / "test_public_key.pem"

        config = {
            "private_key_path": str(private_key_path),
            "public_key_path": str(public_key_path),
        }

        # Gerar e salvar chaves de teste
        signer = DigitalSigner(config)
        private_pem, public_pem = signer.generate_keys()

        # Salvar chaves em arquivo
        with open(private_key_path, "wb") as f:
            f.write(private_pem)
        with open(public_key_path, "wb") as f:
            f.write(public_pem)

        return config

    def test_generate_keys(self, tmp_path):
        """Testa geração de par de chaves RSA."""
        config = {"private_key_path": None, "public_key_path": None}
        signer = DigitalSigner(config)

        # Gerar chaves
        private_pem, public_pem = signer.generate_keys()

        assert private_pem is not None
        assert public_pem is not None
        assert signer.private_key is not None
        assert signer.public_key is not None
        assert b"BEGIN PRIVATE KEY" in private_pem
        assert b"BEGIN PUBLIC KEY" in public_pem

    def test_sign_and_verify_document(self, signer_config):
        """Testa assinatura e verificação de documento."""
        signer = DigitalSigner(signer_config)

        document = {
            "opinion_id": str(uuid.uuid4()),
            "plan_id": str(uuid.uuid4()),
            "opinion": {
                "confidence_score": 0.9,
                "risk_score": 0.1,
                "recommendation": "approve",
                "reasoning_summary": "Test",
            },
        }

        # Assinar documento
        signed_doc = signer.sign_document(document)

        assert "digital_signature" in signed_doc
        assert "content_hash" in signed_doc
        assert "signature_algorithm" in signed_doc
        # Aceita ambos os algoritmos (PSS e PKCS1v15)
        assert signed_doc["signature_algorithm"] in ["RSA-SHA256", "RSA-SHA256-PSS"]

        # Verificar assinatura
        is_valid = signer.verify_signature(signed_doc)
        assert is_valid is True

    def test_detect_tampering(self, signer_config):
        """Testa detecção de adulteração de documento."""
        signer = DigitalSigner(signer_config)

        document = {
            "opinion_id": str(uuid.uuid4()),
            "plan_id": str(uuid.uuid4()),
            "opinion": {
                "confidence_score": 0.9,
                "risk_score": 0.1,
                "recommendation": "approve",
                "reasoning_summary": "Test",
            },
        }

        # Assinar documento
        signed_doc = signer.sign_document(document)

        # Adulterar documento
        signed_doc["opinion"]["confidence_score"] = 0.5

        # Detectar adulteração
        is_tampered = signer.detect_tampering(signed_doc)
        assert is_tampered is True

    def test_verify_signature_without_private_key(self, signer_config):
        """Testa verificação de assinatura apenas com chave pública."""
        # Criar signer com ambas as chaves e assinar
        signer_full = DigitalSigner(signer_config)
        document = {
            "opinion_id": str(uuid.uuid4()),
            "plan_id": str(uuid.uuid4()),
            "opinion": {
                "confidence_score": 0.9,
                "risk_score": 0.1,
                "recommendation": "approve",
                "reasoning_summary": "Test",
            },
        }
        signed_doc = signer_full.sign_document(document)

        # Criar novo signer apenas com chave pública (sem private_key_path)
        verify_config = {
            "private_key_path": None,
            "public_key_path": signer_config["public_key_path"],
        }
        signer_verify = DigitalSigner(verify_config)

        # Deve conseguir verificar apenas com chave pública
        is_valid = signer_verify.verify_signature(signed_doc)
        assert is_valid is True


class TestSchemaVersionManager:
    """Testes unitários para SchemaVersionManager."""

    def test_validate_valid_document(self):
        """Testa validação de documento válido."""
        document = {
            "schema_version": "2.0.0",
            "opinion_id": str(uuid.uuid4()),
            "plan_id": str(uuid.uuid4()),
            "intent_id": str(uuid.uuid4()),
            "specialist_type": "technical",
            "specialist_version": "1.0.0",
            "opinion": {
                "confidence_score": 0.9,
                "risk_score": 0.1,
                "recommendation": "approve",
                "reasoning_summary": "Test summary",
                "reasoning_factors": [],
                "explainability_token": "",
                "explainability": {},
                "mitigations": [],
                "metadata": {},
            },
            "correlation_id": str(uuid.uuid4()),
            "trace_id": None,
            "span_id": None,
            "evaluated_at": datetime.utcnow().isoformat(),
            "processing_time_ms": 100,
            "buffered": False,
            "content_hash": "abc123",
        }

        is_valid = SchemaVersionManager.validate_document(document)
        assert is_valid is True

    def test_validate_invalid_document_missing_field(self):
        """Testa validação de documento com campo obrigatório faltando."""
        document = {
            "schema_version": "2.0.0",
            "opinion_id": str(uuid.uuid4()),
            # Faltando plan_id
            "intent_id": str(uuid.uuid4()),
            "specialist_type": "technical",
        }

        is_valid = SchemaVersionManager.validate_document(document)
        assert is_valid is False

    def test_is_version_compatible(self):
        """Testa verificação de compatibilidade de versão."""
        assert SchemaVersionManager.is_version_compatible("2.0.0") is True
        assert SchemaVersionManager.is_version_compatible("1.0.0") is True
        assert SchemaVersionManager.is_version_compatible("3.0.0") is False


class TestLedgerClientV2Integration:
    """Testes de integração para LedgerClient com features V2."""

    @pytest.fixture
    def config(self, tmp_path):
        """Configuração de teste para LedgerClient."""
        private_key_path = tmp_path / "test_private_key.pem"
        public_key_path = tmp_path / "test_public_key.pem"

        # Gerar e salvar chaves
        signer_config = {"private_key_path": None, "public_key_path": None}
        signer = DigitalSigner(signer_config)
        private_pem, public_pem = signer.generate_keys()

        # Salvar chaves em arquivo
        with open(private_key_path, "wb") as f:
            f.write(private_pem)
        with open(public_key_path, "wb") as f:
            f.write(public_pem)

        config = SpecialistConfig(
            specialist_type="technical",
            service_name="test-specialist",
            mlflow_tracking_uri="http://localhost:5000",
            mlflow_experiment_name="test",
            mlflow_model_name="test-model",
            mongodb_uri="mongodb://localhost:27017",
            mongodb_database="test_db",
            mongodb_opinions_collection="test_opinions",
            redis_cluster_nodes="localhost:6379",
            neo4j_uri="bolt://localhost:7687",
            neo4j_password="test",
            enable_digital_signature=True,
            ledger_private_key_path=str(private_key_path),
            ledger_public_key_path=str(public_key_path),
            enable_schema_validation=True,
            ledger_schema_version="2.0.0",
            enable_jwt_auth=False,  # Desabilitar JWT para testes
            environment="test",  # Ambiente de teste
        )

        return config

    @patch("neural_hive_specialists.ledger_client.MongoClient")
    def test_save_opinion_with_signature(self, mock_mongo_client, config):
        """Testa save_opinion com assinatura digital."""
        # Mock MongoDB
        mock_collection = MagicMock()
        mock_db = MagicMock()
        mock_db.__getitem__.return_value = mock_collection
        mock_client = MagicMock()
        mock_client.__getitem__.return_value = mock_db
        mock_mongo_client.return_value = mock_client

        ledger_client = LedgerClient(config)

        opinion = {
            "confidence_score": 0.9,
            "risk_score": 0.1,
            "recommendation": "approve",
            "reasoning_summary": "Test summary",
            "reasoning_factors": [
                {"factor_name": "security", "weight": 0.5, "score": 0.9}
            ],
            "mitigations": [],
            "metadata": {"domain": "api_integration"},
        }

        opinion_id = ledger_client.save_opinion(
            opinion=opinion,
            plan_id=str(uuid.uuid4()),
            intent_id=str(uuid.uuid4()),
            specialist_type="technical",
            correlation_id=str(uuid.uuid4()),
            specialist_version="1.0.0",
            trace_id="test-trace-id",
            span_id="test-span-id",
            processing_time_ms=150,
        )

        # Verificar que insert_one foi chamado
        assert mock_collection.insert_one.called
        call_args = mock_collection.insert_one.call_args[0][0]

        # Verificar campos do documento
        assert "digital_signature" in call_args
        assert "content_hash" in call_args
        assert "signature_algorithm" in call_args
        assert call_args["specialist_version"] == "1.0.0"
        assert call_args["trace_id"] == "test-trace-id"
        assert call_args["span_id"] == "test-span-id"
        assert call_args["processing_time_ms"] == 150
        assert opinion_id is not None

    @patch("neural_hive_specialists.ledger_client.MongoClient")
    def test_verify_document_integrity_with_signature(self, mock_mongo_client, config):
        """Testa verify_document_integrity com assinatura digital."""
        # Mock MongoDB
        mock_collection = MagicMock()
        mock_db = MagicMock()
        mock_db.__getitem__.return_value = mock_collection
        mock_client = MagicMock()
        mock_client.__getitem__.return_value = mock_db
        mock_mongo_client.return_value = mock_client

        ledger_client = LedgerClient(config)

        # Criar documento assinado
        opinion_id = str(uuid.uuid4())
        document = {
            "opinion_id": opinion_id,
            "plan_id": str(uuid.uuid4()),
            "opinion": {
                "confidence_score": 0.9,
                "risk_score": 0.1,
                "recommendation": "approve",
                "reasoning_summary": "Test",
            },
            "content_hash": "abc123",
            "digital_signature": "signature",
            "signature_algorithm": "RSA-SHA256",
        }

        # Assinar documento real
        signed_doc = ledger_client.digital_signer.sign_document(document)

        # Mock find_one para retornar documento assinado
        mock_collection.find_one.return_value = signed_doc

        # Verificar integridade
        is_valid = ledger_client.verify_document_integrity(opinion_id)

        assert is_valid is True

    @patch("neural_hive_specialists.ledger_client.MongoClient")
    def test_verify_document_integrity_fallback_to_hash(
        self, mock_mongo_client, config
    ):
        """Testa fallback de verify_document_integrity para hash legado."""
        # Desabilitar assinatura digital
        config.enable_digital_signature = False

        # Mock MongoDB
        mock_collection = MagicMock()
        mock_db = MagicMock()
        mock_db.__getitem__.return_value = mock_collection
        mock_client = MagicMock()
        mock_client.__getitem__.return_value = mock_db
        mock_mongo_client.return_value = mock_client

        ledger_client = LedgerClient(config)

        # Criar documento sem assinatura (apenas hash legado)
        opinion_id = str(uuid.uuid4())
        document = {
            "opinion_id": opinion_id,
            "plan_id": str(uuid.uuid4()),
            "intent_id": str(uuid.uuid4()),
            "specialist_type": "technical",
            "correlation_id": str(uuid.uuid4()),
            "opinion_data": {"test": "data"},
            "timestamp": datetime.utcnow(),
            "hash": "legacy_hash_placeholder",
        }

        # Calcular hash legado correto
        document["hash"] = ledger_client._calculate_hash(document)

        # Mock find_one
        mock_collection.find_one.return_value = document

        # Verificar integridade (deve usar fallback)
        is_valid = ledger_client.verify_document_integrity(opinion_id)

        # Deve chamar verify_integrity_impl
        assert is_valid is True


class TestLedgerQueryAPI:
    """Testes para LedgerQueryAPI."""

    @pytest.fixture
    def query_config(self):
        """Configuração para query API."""
        return {
            "mongodb_uri": "mongodb://localhost:27017",
            "mongodb_database": "test_db",
            "mongodb_opinions_collection": "test_opinions",
            "query_cache_ttl_seconds": 300,
        }

    @patch("neural_hive_specialists.ledger.query_api.MongoClient")
    def test_get_opinions_by_domain(self, mock_mongo_client, query_config):
        """Testa consulta de opiniões por domínio."""
        # Mock MongoDB
        mock_collection = MagicMock()
        mock_db = MagicMock()
        mock_db.__getitem__.return_value = mock_collection
        mock_client = MagicMock()
        mock_client.__getitem__.return_value = mock_db
        mock_mongo_client.return_value = mock_client

        query_api = LedgerQueryAPI(query_config)

        # Mock cursor
        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.limit.return_value = mock_cursor
        mock_cursor.skip.return_value = mock_cursor
        mock_cursor.__iter__.return_value = iter(
            [
                {
                    "_id": "test_id",
                    "opinion_id": str(uuid.uuid4()),
                    "opinion": {"metadata": {"domain": "api_integration"}},
                }
            ]
        )
        mock_collection.find.return_value = mock_cursor

        # Chamar método
        opinions = query_api.get_opinions_by_domain("api_integration", limit=10)

        # Verificar resultado
        assert len(opinions) == 1
        assert "opinion_id" in opinions[0]
        assert "_id" not in opinions[0]  # _id deve ser removido
        mock_collection.find.assert_called_once()

    @patch("neural_hive_specialists.ledger.query_api.MongoClient")
    def test_get_opinions_by_feature(self, mock_mongo_client, query_config):
        """Testa consulta de opiniões por feature (reasoning_factor)."""
        # Mock MongoDB
        mock_collection = MagicMock()
        mock_db = MagicMock()
        mock_db.__getitem__.return_value = mock_collection
        mock_client = MagicMock()
        mock_client.__getitem__.return_value = mock_db
        mock_mongo_client.return_value = mock_client

        query_api = LedgerQueryAPI(query_config)

        # Mock cursor
        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.limit.return_value = mock_cursor
        mock_cursor.__iter__.return_value = iter(
            [
                {
                    "_id": "test_id",
                    "opinion_id": str(uuid.uuid4()),
                    "opinion": {
                        "reasoning_factors": [
                            {"factor_name": "security_analysis", "score": 0.9}
                        ]
                    },
                }
            ]
        )
        mock_collection.find.return_value = mock_cursor

        # Chamar método
        opinions = query_api.get_opinions_by_feature(
            "security_analysis", min_score=0.8, limit=10
        )

        # Verificar resultado
        assert len(opinions) == 1
        assert "opinion_id" in opinions[0]
        mock_collection.find.assert_called_once()

        # Verificar query construído
        call_args = mock_collection.find.call_args[0][0]
        assert "opinion.reasoning_factors" in call_args
        assert "$elemMatch" in call_args["opinion.reasoning_factors"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
