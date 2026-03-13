"""
Testes estendidos para CodeComposer.

Este modulo testa metodos e caminhos nao cobertos pelos testes existentes,
incluindo metodos _generate_* e fallback behavior.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from src.services.code_composer import CodeComposer
from src.models.pipeline_context import PipelineContext
from src.models.execution_ticket import (
    ExecutionTicket, TaskType, TicketStatus, Priority, RiskBand,
    SLA, QoS, SecurityLevel, DeliveryMode, Consistency, Durability
)
from src.models.template import Template, TemplateMetadata, TemplateType
from src.types.artifact_types import CodeLanguage, ArtifactCategory
from src.models.artifact import GenerationMethod
import uuid


class TestGeneratePythonLibrary:
    """Testes para _generate_python_library."""

    @pytest.fixture
    def code_composer(self, mock_mongodb_client):
        """Instancia do CodeComposer para testes."""
        return CodeComposer(
            mongodb_client=mock_mongodb_client,
            llm_client=None,
            analyst_client=None,
            mcp_client=None
        )

    def test_generate_python_library_default_name(self, code_composer):
        """Testa geracao de biblioteca Python com nome padrao."""
        params = {}
        result = code_composer._generate_python_library(params)

        assert 'my-lib' in result
        assert '__version__' in result
        # .title() converte 'my-lib' para 'My_Lib'
        assert 'class My_Lib' in result

    def test_generate_python_library_custom_name(self, code_composer):
        """Testa geracao de biblioteca Python com nome customizado."""
        params = {'service_name': 'awesome-lib'}
        result = code_composer._generate_python_library(params)

        assert 'awesome-lib' in result
        # .title() converte 'awesome-lib' para 'Awesome_Lib'
        assert 'class Awesome_Lib' in result

    def test_generate_python_library_structure(self, code_composer):
        """Testa que biblioteca Python tem estrutura correta."""
        params = {'service_name': 'testlib'}  # sem hifen para evitar underscore
        result = code_composer._generate_python_library(params)

        # Verificar elementos principais
        assert '"""' in result  # Docstring
        assert '__version__' in result
        assert 'class Testlib' in result
        assert 'def __init__' in result
        assert 'def process' in result


class TestGeneratePythonScript:
    """Testes para _generate_python_script."""

    @pytest.fixture
    def code_composer(self, mock_mongodb_client):
        """Instancia do CodeComposer para testes."""
        return CodeComposer(
            mongodb_client=mock_mongodb_client,
            llm_client=None,
            analyst_client=None,
            mcp_client=None
        )

    def test_generate_python_script_default_name(self, code_composer):
        """Testa geracao de script Python com nome padrao."""
        params = {}
        result = code_composer._generate_python_script(params)

        assert '#!/usr/bin/env python3' in result
        assert 'my-script' in result

    def test_generate_python_script_custom_name(self, code_composer):
        """Testa geracao de script Python com nome customizado."""
        params = {'service_name': 'custom-script'}
        result = code_composer._generate_python_script(params)

        assert 'custom-script' in result

    def test_generate_python_script_structure(self, code_composer):
        """Testa que script Python tem estrutura correta."""
        params = {'service_name': 'test-script'}
        result = code_composer._generate_python_script(params)

        assert 'import logging' in result
        assert 'def main():' in result
        assert 'if __name__ == "__main__":' in result


class TestGenerateJavaScriptVariants:
    """Testes para geradores JavaScript."""

    @pytest.fixture
    def code_composer(self, mock_mongodb_client):
        """Instancia do CodeComposer para testes."""
        return CodeComposer(
            mongodb_client=mock_mongodb_client,
            llm_client=None,
            analyst_client=None,
            mcp_client=None
        )

    def test_generate_javascript_microservice(self, code_composer):
        """Testa geracao de microservico JavaScript."""
        params = {'service_name': 'js-service', 'description': 'JS API'}
        result = code_composer._generate_javascript_microservice(params)

        assert 'const express' in result
        assert "require('express')" in result
        assert "require('helmet')" in result
        assert 'js-service' in result
        assert '/health' in result

    def test_generate_javascript_library(self, code_composer):
        """Testa geracao de biblioteca JavaScript."""
        params = {'service_name': 'js-lib', 'description': 'JS Lib'}
        result = code_composer._generate_javascript_library(params)

        assert "'use strict'" in result
        # O metodo .replace('-', '').replace('_', '') remove hifens e underscores
        assert 'class Jslib' in result
        assert 'module.exports' in result

    def test_generate_javascript_script(self, code_composer):
        """Testa geracao de script JavaScript."""
        params = {'service_name': 'js-script', 'description': 'JS Script'}
        result = code_composer._generate_javascript_script(params)

        assert '#!/usr/bin/env node' in result
        assert "require('commander')" in result
        assert "require('winston')" in result
        assert 'js-script' in result


class TestGenerateTypeScriptVariants:
    """Testes para geradores TypeScript."""

    @pytest.fixture
    def code_composer(self, mock_mongodb_client):
        """Instancia do CodeComposer para testes."""
        return CodeComposer(
            mongodb_client=mock_mongodb_client,
            llm_client=None,
            analyst_client=None,
            mcp_client=None
        )

    def test_generate_typescript_microservice(self, code_composer):
        """Testa geracao de microservico TypeScript."""
        params = {'service_name': 'ts-service', 'description': 'TS API'}
        result = code_composer._generate_typescript_microservice(params)

        assert 'import express' in result
        assert 'import helmet' in result
        assert 'interface HealthResponse' in result
        # O metodo remove hifens e underscores: ts-service -> Tsservice
        assert 'class TsserviceApp' in result

    def test_generate_typescript_library(self, code_composer):
        """Testa geracao de biblioteca TypeScript."""
        params = {'service_name': 'tslib', 'description': 'TS Lib'}
        result = code_composer._generate_typescript_library(params)

        assert 'export interface' in result
        assert 'export class Tslib' in result
        assert 'export default' in result


class TestGenerateGoVariants:
    """Testes para geradores Go."""

    @pytest.fixture
    def code_composer(self, mock_mongodb_client):
        """Instancia do CodeComposer para testes."""
        return CodeComposer(
            mongodb_client=mock_mongodb_client,
            llm_client=None,
            analyst_client=None,
            mcp_client=None
        )

    def test_generate_go_microservice(self, code_composer):
        """Testa geracao de microservico Go."""
        params = {'service_name': 'go-service', 'description': 'Go API'}
        result = code_composer._generate_go_microservice(params)

        assert 'package main' in result
        assert 'import (' in result
        assert 'func healthHandler' in result
        assert 'func rootHandler' in result
        assert 'func main()' in result

    def test_generate_go_library(self, code_composer):
        """Testa geracao de biblioteca Go."""
        params = {'service_name': 'go-lib', 'description': 'Go Lib'}
        result = code_composer._generate_go_library(params)

        assert 'type Options struct' in result
        assert 'type Library struct' in result
        assert 'func New' in result
        assert 'func (l *Library) Process' in result


class TestGenerateJavaMicroservice:
    """Testes para _generate_java_microservice."""

    @pytest.fixture
    def code_composer(self, mock_mongodb_client):
        """Instancia do CodeComposer para testes."""
        return CodeComposer(
            mongodb_client=mock_mongodb_client,
            llm_client=None,
            analyst_client=None,
            mcp_client=None
        )

    def test_generate_java_microservice(self, code_composer):
        """Testa geracao de microservico Java."""
        params = {'service_name': 'java-service', 'description': 'Java API'}
        result = code_composer._generate_java_microservice(params)

        assert '@SpringBootApplication' in result
        assert '@RestController' in result
        assert 'public static void main' in result
        assert '@GetMapping("/health")' in result


class TestGenerateRustMicroservice:
    """Testes para _generate_rust_microservice."""

    @pytest.fixture
    def code_composer(self, mock_mongodb_client):
        """Instancia do CodeComposer para testes."""
        return CodeComposer(
            mongodb_client=mock_mongodb_client,
            llm_client=None,
            analyst_client=None,
            mcp_client=None
        )

    def test_generate_rust_microservice(self, code_composer):
        """Testa geracao de microservico Rust."""
        params = {'service_name': 'rust-service', 'description': 'Rust API'}
        result = code_composer._generate_rust_microservice(params)

        assert 'use actix_web' in result
        assert '#[derive(Serialize)]' in result
        assert 'async fn health()' in result
        assert '#[actix_web::main]' in result


class TestGenerateBashScript:
    """Testes para _generate_bash_script."""

    @pytest.fixture
    def code_composer(self, mock_mongodb_client):
        """Instancia do CodeComposer para testes."""
        return CodeComposer(
            mongodb_client=mock_mongodb_client,
            llm_client=None,
            analyst_client=None,
            mcp_client=None
        )

    def test_generate_bash_script(self, code_composer):
        """Testa geracao de script Bash."""
        params = {'service_name': 'bash-script', 'description': 'Bash Script'}
        result = code_composer._generate_bash_script(params)

        assert '#!/bin/bash' in result
        assert 'set -euo pipefail' in result
        assert 'log_info()' in result
        assert 'log_warn()' in result
        assert 'log_error()' in result
        assert 'bash-script' in result


class TestGenerateIaCTemplates:
    """Testes para geradores de IaC."""

    @pytest.fixture
    def code_composer(self, mock_mongodb_client):
        """Instancia do CodeComposer para testes."""
        return CodeComposer(
            mongodb_client=mock_mongodb_client,
            llm_client=None,
            analyst_client=None,
            mcp_client=None
        )

    def test_generate_terraform_module(self, code_composer):
        """Testa geracao de modulo Terraform."""
        params = {'service_name': 'tf-module', 'description': 'Terraform Module'}
        result = code_composer._generate_terraform_module(params)

        assert 'variable "name"' in result
        assert 'variable "environment"' in result
        assert 'output "resource_name"' in result
        assert 'tf-module' in result

    def test_generate_helm_chart(self, code_composer):
        """Testa geracao de Helm Chart."""
        params = {'service_name': 'helm-chart', 'description': 'Helm Chart'}
        result = code_composer._generate_helm_chart(params)

        assert 'apiVersion: v2' in result
        assert 'name: helm-chart' in result
        assert 'replicaCount: 1' in result
        assert 'image:' in result

    def test_generate_opa_policy(self, code_composer):
        """Testa geracao de politica OPA."""
        params = {'service_name': 'opa-policy', 'description': 'OPA Policy'}
        result = code_composer._generate_opa_policy(params)

        assert 'package opa_policy' in result
        assert 'default allow = false' in result
        assert 'deny {' in result
        assert 'is_authorized' in result


class TestSelectGeneratorFallback:
    """Testes para _select_generator e fallback behavior."""

    @pytest.fixture
    def code_composer(self, mock_mongodb_client):
        """Instancia do CodeComposer para testes."""
        return CodeComposer(
            mongodb_client=mock_mongodb_client,
            llm_client=None,
            analyst_client=None,
            mcp_client=None
        )

    def test_select_generator_unsupported_language_fallback(
        self,
        code_composer
    ):
        """Testa fallback para Python quando linguagem nao eh suportada."""
        params = {
            'artifact_type': 'MICROSERVICE',
            'language': 'unsupported-lang',
            'service_name': 'test-service'
        }

        result = code_composer._select_generator('MICROSERVICE', 'unsupported-lang', params)

        # Deve usar gerador Python como fallback (FastAPI é framework Python)
        assert 'FastAPI' in result or 'fastapi' in result
        # Verificar que tem estrutura Python
        assert 'import ' in result and 'def ' in result

    def test_select_generator_library_python(self, code_composer):
        """Testa selecao de gerador para biblioteca Python."""
        params = {'service_name': 'testlib'}
        result = code_composer._select_generator('LIBRARY', 'python', params)

        assert '__version__' in result
        assert 'class Testlib' in result

    def test_select_generator_script_python(self, code_composer):
        """Testa selecao de gerador para script Python."""
        params = {'service_name': 'test-script'}
        result = code_composer._select_generator('SCRIPT', 'python', params)

        assert 'def main():' in result

    def test_select_generator_terraform(self, code_composer):
        """Testa selecao de gerador para Terraform."""
        params = {'service_name': 'tf-module'}
        result = code_composer._select_generator('IAC_TERRAFORM', 'hcl', params)

        assert 'variable' in result

    def test_select_generator_helm(self, code_composer):
        """Testa selecao de gerador para Helm."""
        params = {'service_name': 'helm-chart'}
        result = code_composer._select_generator('IAC_HELM', 'yaml', params)

        assert 'apiVersion: v2' in result

    def test_select_generator_opa(self, code_composer):
        """Testa selecao de gerador para OPA."""
        params = {'service_name': 'opa-policy'}
        result = code_composer._select_generator('POLICY_OPA', 'rego', params)

        assert 'package' in result
        assert 'default allow = false' in result


class TestGenerateHeuristic:
    """Testes para _generate_heuristic."""

    @pytest.fixture
    def code_composer(self, mock_mongodb_client):
        """Instancia do CodeComposer para testes."""
        return CodeComposer(
            mongodb_client=mock_mongodb_client,
            llm_client=None,
            analyst_client=None,
            mcp_client=None
        )

    def test_generate_heuristic_microservice_python(self, code_composer):
        """Testa geracao heuristica de microservico Python."""
        params = {
            'artifact_type': 'MICROSERVICE',
            'language': 'python',
            'service_name': 'test-service'
        }

        result = code_composer._generate_heuristic(params)

        assert 'FastAPI' in result
        assert 'test-service' in result

    def test_generate_heuristic_microservice_javascript(self, code_composer):
        """Testa geracao heuristica de microservico JavaScript."""
        params = {
            'artifact_type': 'MICROSERVICE',
            'language': 'javascript',
            'service_name': 'js-service'
        }

        result = code_composer._generate_heuristic(params)

        assert 'express' in result
        assert 'js-service' in result

    def test_generate_heuristic_library_python(self, code_composer):
        """Testa geracao heuristica de biblioteca Python."""
        params = {
            'artifact_type': 'LIBRARY',
            'language': 'python',
            'service_name': 'mylib'  # sem hifen
        }

        result = code_composer._generate_heuristic(params)

        assert '__version__' in result
        assert 'class Mylib' in result

    def test_generate_heuristic_script_python(self, code_composer):
        """Testa geracao heuristica de script Python."""
        params = {
            'artifact_type': 'SCRIPT',
            'language': 'python',
            'service_name': 'my-script'
        }

        result = code_composer._generate_heuristic(params)

        assert 'def main():' in result
        assert 'my-script' in result


class TestBuildLLMPrompt:
    """Testes para _build_llm_prompt."""

    @pytest.fixture
    def code_composer(self, mock_mongodb_client):
        """Instancia do CodeComposer para testes."""
        return CodeComposer(
            mongodb_client=mock_mongodb_client,
            llm_client=None,
            analyst_client=None,
            mcp_client=None
        )

    @pytest.fixture
    def sample_ticket(self):
        """Ticket para testes."""
        ticket_id = str(uuid.uuid4())
        return ExecutionTicket(
            ticket_id=ticket_id,
            plan_id=f'plan-{ticket_id[:8]}',
            intent_id=f'intent-{ticket_id[:8]}',
            decision_id=f'decision-{ticket_id[:8]}',
            correlation_id=str(uuid.uuid4()),
            trace_id=str(uuid.uuid4()),
            span_id=str(uuid.uuid4()),
            task_type=TaskType.BUILD,
            status=TicketStatus.PENDING,
            priority=Priority.NORMAL,
            risk_band=RiskBand.MEDIUM,
            parameters={
                'artifact_type': 'microservice',
                'language': 'Python',
                'service_name': 'test-service',
                'description': 'A test service',
                'requirements': ['Auth', 'Logging', 'Metrics']
            },
            sla=SLA(
                deadline=datetime.now(),
                timeout_ms=300000,
                max_retries=3
            ),
            qos=QoS(
                delivery_mode=DeliveryMode.AT_LEAST_ONCE,
                consistency=Consistency.EVENTUAL,
                durability=Durability.PERSISTENT
            ),
            security_level=SecurityLevel.INTERNAL,
            dependencies=[],
            created_at=datetime.now()
        )

    def test_build_llm_prompt_basic(self, code_composer, sample_ticket):
        """Testa construcao basica de prompt LLM."""
        rag_context = {
            'similar_templates': [],
            'architectural_patterns': []
        }

        prompt = code_composer._build_llm_prompt(sample_ticket, rag_context)

        assert 'Generate a microservice' in prompt
        assert 'Python' in prompt
        assert 'test-service' in prompt
        assert 'A test service' in prompt
        assert '- Auth' in prompt
        assert '- Logging' in prompt

    def test_build_llm_prompt_with_templates(self, code_composer, sample_ticket):
        """Testa prompt LLM com templates similares."""
        rag_context = {
            'similar_templates': [
                {'text': 'FastAPI microservice template', 'similarity': 0.92},
                {'text': 'Python service template', 'similarity': 0.85}
            ],
            'architectural_patterns': []
        }

        prompt = code_composer._build_llm_prompt(sample_ticket, rag_context)

        assert 'Similar Templates' in prompt
        assert 'FastAPI microservice' in prompt

    def test_build_llm_prompt_with_patterns(self, code_composer, sample_ticket):
        """Testa prompt LLM com padroes arquiteturais."""
        rag_context = {
            'similar_templates': [],
            'architectural_patterns': [
                'Repository Pattern',
                'Service Layer',
                'Dependency Injection'
            ]
        }

        prompt = code_composer._build_llm_prompt(sample_ticket, rag_context)

        assert 'Architectural Patterns' in prompt
        assert 'Repository Pattern' in prompt
        assert 'Service Layer' in prompt

    def test_build_llm_prompt_empty_requirements(self, code_composer):
        """Testa prompt LLM com requisitos vazios."""
        ticket_id = str(uuid.uuid4())
        ticket = ExecutionTicket(
            ticket_id=ticket_id,
            plan_id=f'plan-{ticket_id[:8]}',
            intent_id=f'intent-{ticket_id[:8]}',
            decision_id=f'decision-{ticket_id[:8]}',
            correlation_id=str(uuid.uuid4()),
            trace_id=str(uuid.uuid4()),
            span_id=str(uuid.uuid4()),
            task_type=TaskType.BUILD,
            status=TicketStatus.PENDING,
            priority=Priority.NORMAL,
            risk_band=RiskBand.MEDIUM,
            parameters={
                'artifact_type': 'microservice',
                'language': 'Python',
                'service_name': 'test-service',
                'description': '',
                'requirements': []
            },
            sla=SLA(
                deadline=datetime.now(),
                timeout_ms=300000,
                max_retries=3
            ),
            qos=QoS(
                delivery_mode=DeliveryMode.AT_LEAST_ONCE,
                consistency=Consistency.EVENTUAL,
                durability=Durability.PERSISTENT
            ),
            security_level=SecurityLevel.INTERNAL,
            dependencies=[],
            created_at=datetime.now()
        )

        rag_context = {'similar_templates': [], 'architectural_patterns': []}

        prompt = code_composer._build_llm_prompt(ticket, rag_context)

        # Prompt deve ser gerado mesmo sem requisitos
        assert 'Generate a microservice' in prompt


class TestBuildRAGContext:
    """Testes para _build_rag_context."""

    @pytest.fixture
    def code_composer(self, mock_mongodb_client, mock_analyst_client):
        """Instancia do CodeComposer para testes."""
        return CodeComposer(
            mongodb_client=mock_mongodb_client,
            llm_client=None,
            analyst_client=mock_analyst_client,
            mcp_client=None
        )

    @pytest.mark.asyncio
    async def test_build_rag_context_success(self, code_composer):
        """Testa construcao bem-sucedida de contexto RAG."""
        ticket_id = str(uuid.uuid4())
        ticket = ExecutionTicket(
            ticket_id=ticket_id,
            plan_id=f'plan-{ticket_id[:8]}',
            intent_id=f'intent-{ticket_id[:8]}',
            decision_id=f'decision-{ticket_id[:8]}',
            correlation_id=str(uuid.uuid4()),
            trace_id=str(uuid.uuid4()),
            span_id=str(uuid.uuid4()),
            task_type=TaskType.BUILD,
            status=TicketStatus.PENDING,
            priority=Priority.NORMAL,
            risk_band=RiskBand.MEDIUM,
            parameters={
                'description': 'Test service',
                'language': 'python',
                'artifact_type': 'microservice'
            },
            sla=SLA(
                deadline=datetime.now(),
                timeout_ms=300000,
                max_retries=3
            ),
            qos=QoS(
                delivery_mode=DeliveryMode.AT_LEAST_ONCE,
                consistency=Consistency.EVENTUAL,
                durability=Durability.PERSISTENT
            ),
            security_level=SecurityLevel.INTERNAL,
            dependencies=[],
            created_at=datetime.now()
        )

        result = await code_composer._build_rag_context(ticket)

        assert 'similar_templates' in result
        assert 'architectural_patterns' in result

    @pytest.mark.asyncio
    async def test_build_rag_context_no_analyst_client(self, mock_mongodb_client):
        """Testa contexto RAG quando analyst_client nao esta disponivel."""
        code_composer = CodeComposer(
            mongodb_client=mock_mongodb_client,
            llm_client=None,
            analyst_client=None,
            mcp_client=None
        )

        ticket_id = str(uuid.uuid4())
        ticket = ExecutionTicket(
            ticket_id=ticket_id,
            plan_id=f'plan-{ticket_id[:8]}',
            intent_id=f'intent-{ticket_id[:8]}',
            decision_id=f'decision-{ticket_id[:8]}',
            correlation_id=str(uuid.uuid4()),
            trace_id=str(uuid.uuid4()),
            span_id=str(uuid.uuid4()),
            task_type=TaskType.BUILD,
            status=TicketStatus.PENDING,
            priority=Priority.NORMAL,
            risk_band=RiskBand.MEDIUM,
            parameters={'description': 'Test'},
            sla=SLA(
                deadline=datetime.now(),
                timeout_ms=300000,
                max_retries=3
            ),
            qos=QoS(
                delivery_mode=DeliveryMode.AT_LEAST_ONCE,
                consistency=Consistency.EVENTUAL,
                durability=Durability.PERSISTENT
            ),
            security_level=SecurityLevel.INTERNAL,
            dependencies=[],
            created_at=datetime.now()
        )

        result = await code_composer._build_rag_context(ticket)

        assert result == {'similar_templates': [], 'architectural_patterns': []}

    @pytest.mark.asyncio
    async def test_build_rag_context_embedding_failure(self, code_composer):
        """Testa contexto RAG quando geracao de embedding falha."""
        code_composer.analyst_client.get_embedding = AsyncMock(return_value=None)

        ticket_id = str(uuid.uuid4())
        ticket = ExecutionTicket(
            ticket_id=ticket_id,
            plan_id=f'plan-{ticket_id[:8]}',
            intent_id=f'intent-{ticket_id[:8]}',
            decision_id=f'decision-{ticket_id[:8]}',
            correlation_id=str(uuid.uuid4()),
            trace_id=str(uuid.uuid4()),
            span_id=str(uuid.uuid4()),
            task_type=TaskType.BUILD,
            status=TicketStatus.PENDING,
            priority=Priority.NORMAL,
            risk_band=RiskBand.MEDIUM,
            parameters={'description': 'Test', 'language': 'python'},
            sla=SLA(
                deadline=datetime.now(),
                timeout_ms=300000,
                max_retries=3
            ),
            qos=QoS(
                delivery_mode=DeliveryMode.AT_LEAST_ONCE,
                consistency=Consistency.EVENTUAL,
                durability=Durability.PERSISTENT
            ),
            security_level=SecurityLevel.INTERNAL,
            dependencies=[],
            created_at=datetime.now()
        )

        result = await code_composer._build_rag_context(ticket)

        # Deve retornar lista vazia de templates quando embedding falha
        assert result['similar_templates'] == []
        assert 'architectural_patterns' in result

    @pytest.mark.asyncio
    async def test_build_rag_context_exception_handling(self, code_composer):
        """Testa contexto RAG quando excecao eh lancada."""
        code_composer.analyst_client.get_embedding = AsyncMock(
            side_effect=Exception("Service unavailable")
        )

        ticket_id = str(uuid.uuid4())
        ticket = ExecutionTicket(
            ticket_id=ticket_id,
            plan_id=f'plan-{ticket_id[:8]}',
            intent_id=f'intent-{ticket_id[:8]}',
            decision_id=f'decision-{ticket_id[:8]}',
            correlation_id=str(uuid.uuid4()),
            trace_id=str(uuid.uuid4()),
            span_id=str(uuid.uuid4()),
            task_type=TaskType.BUILD,
            status=TicketStatus.PENDING,
            priority=Priority.NORMAL,
            risk_band=RiskBand.MEDIUM,
            parameters={'description': 'Test', 'language': 'python'},
            sla=SLA(
                deadline=datetime.now(),
                timeout_ms=300000,
                max_retries=3
            ),
            qos=QoS(
                delivery_mode=DeliveryMode.AT_LEAST_ONCE,
                consistency=Consistency.EVENTUAL,
                durability=Durability.PERSISTENT
            ),
            security_level=SecurityLevel.INTERNAL,
            dependencies=[],
            created_at=datetime.now()
        )

        result = await code_composer._build_rag_context(ticket)

        # Deve retornar listas vazias em caso de erro
        assert result == {'similar_templates': [], 'architectural_patterns': []}
