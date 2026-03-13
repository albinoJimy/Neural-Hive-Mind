import uuid
import hashlib
from datetime import datetime
from typing import Optional
import structlog

from ..models.pipeline_context import PipelineContext
from ..models.artifact import CodeForgeArtifact, GenerationMethod
from ..types.artifact_types import ArtifactCategory
from ..clients.mongodb_client import MongoDBClient
from ..clients.llm_client import LLMClient
from ..clients.mcp_tool_catalog_client import MCPToolCatalogClient
from ..clients.analyst_agents_client import AnalystAgentsClient

logger = structlog.get_logger()


class CodeComposer:
    """Subpipeline 2: Composição de Código e IaC"""

    def __init__(
        self,
        mongodb_client: MongoDBClient,
        llm_client: Optional[LLMClient] = None,
        analyst_client: Optional[AnalystAgentsClient] = None,
        mcp_client: Optional[MCPToolCatalogClient] = None
    ):
        self.mongodb_client = mongodb_client
        self.llm_client = llm_client
        self.analyst_client = analyst_client
        self.mcp_client = mcp_client

    async def compose(self, context: PipelineContext):
        """
        Gera artefatos baseados no template selecionado

        Args:
            context: Contexto do pipeline
        """
        template = context.selected_template
        ticket = context.ticket

        logger.info('code_composition_started', template_id=template.template_id)

        # === INTEGRAÇÃO MCP: Determinar método de geração ===
        generation_method_str = getattr(context, 'generation_method', None)
        if generation_method_str:
            generation_method_str = generation_method_str.upper()
        if not generation_method_str or generation_method_str not in GenerationMethod.__members__:
            generation_method_str = 'TEMPLATE'

        # Validar e normalizar generation_method
        generation_method_enum = GenerationMethod.__members__.get(
            generation_method_str,
            GenerationMethod.TEMPLATE
        )

        if generation_method_str not in GenerationMethod.__members__:
            logger.warning(
                'invalid_generation_method_using_fallback',
                requested_method=generation_method_str,
                fallback_method='TEMPLATE'
            )
            generation_method_str = 'TEMPLATE'

        if generation_method_str == 'LLM' and self.llm_client:
            code_content, confidence_score, effective_method = await self._generate_via_llm(context)
            generation_method_enum = GenerationMethod.__members__.get(
                effective_method,
                GenerationMethod.LLM
            )
        elif generation_method_str == 'HYBRID' and self.llm_client:
            code_content, confidence_score = await self._generate_hybrid(context)
            effective_method = 'HYBRID'
        elif generation_method_str == 'HEURISTIC':
            code_content = self._generate_heuristic(ticket.parameters)
            confidence_score = 0.78
            effective_method = 'HEURISTIC'
            generation_method_enum = GenerationMethod.__members__.get(
                'HEURISTIC',
                GenerationMethod.HEURISTIC
            )
        else:
            # Fallback para template (método original)
            code_content = self._generate_python_microservice(ticket.parameters)
            confidence_score = 0.85
            effective_method = 'TEMPLATE'
            generation_method_enum = GenerationMethod.TEMPLATE

        # Calcular hash
        content_hash = hashlib.sha256(code_content.encode()).hexdigest()

        # Salvar no MongoDB
        artifact_id = str(uuid.uuid4())
        await self.mongodb_client.save_artifact_content(artifact_id, code_content)

        # Preparar metadata com valores string (CodeForgeArtifact.metadata é Dict[str, str])
        mcp_selection_id = getattr(context, 'mcp_selection_id', None) or ''
        selected_tools = getattr(context, 'selected_tools', [])
        mcp_tools_used = ','.join(t.get('tool_name', '') for t in selected_tools if t.get('tool_name'))

        # Criar artefato
        artifact = CodeForgeArtifact(
            artifact_id=artifact_id,
            ticket_id=ticket.ticket_id,
            plan_id=getattr(ticket, 'plan_id', None),
            intent_id=getattr(ticket, 'intent_id', None),
            decision_id=getattr(ticket, 'decision_id', None),
            correlation_id=getattr(ticket, 'correlation_id', str(uuid.uuid4())),
            trace_id=context.trace_id,
            span_id=context.span_id,
            artifact_type=ArtifactCategory.CODE,
            language=ticket.parameters.get('language', 'python'),
            template_id=template.template_id,
            confidence_score=confidence_score,
            generation_method=generation_method_enum,
            content_uri=f'mongodb://artifacts/{artifact_id}',
            content_hash=content_hash,
            created_at=datetime.now(),
            metadata={
                'mcp_selection_id': mcp_selection_id,
                'mcp_tools_used': mcp_tools_used
            }
        )

        context.add_artifact(artifact)
        logger.info(
            'artifact_generated',
            artifact_id=artifact_id,
            type=artifact.artifact_type,
            generation_method=generation_method_str,
            confidence=confidence_score
        )

    async def _generate_via_llm(self, context: PipelineContext) -> tuple[str, float, str]:
        """
        Gera código via LLM com RAG context.

        Args:
            context: Contexto do pipeline

        Returns:
            Tupla (código_gerado, confidence_score, método_efetivo)
        """
        ticket = context.ticket

        # Construir RAG context
        rag_context = {"similar_templates": [], "architectural_patterns": []}
        if self.analyst_client:
            rag_context = await self._build_rag_context(ticket)

        # Construir prompt com RAG context
        prompt = self._build_llm_prompt(ticket, rag_context)

        # Gerar via LLM
        constraints = {
            'language': ticket.parameters.get('language', 'python'),
            'framework': ticket.parameters.get('framework', ''),
            'patterns': ticket.parameters.get('patterns', []),
            'max_lines': ticket.parameters.get('max_lines', 1000)
        }

        llm_result = await self.llm_client.generate_code(
            prompt=prompt,
            constraints=constraints,
            temperature=0.2
        )

        if not llm_result:
            # Fallback para heurística se LLM falhar
            logger.warning('llm_generation_failed_using_heuristic', ticket_id=ticket.ticket_id)
            return self._generate_heuristic(ticket.parameters), 0.75, 'HEURISTIC'

        code_content = llm_result.get('code', '')
        confidence_score = llm_result.get('confidence_score', 0.7)

        return code_content, confidence_score, 'LLM'

    async def _generate_hybrid(self, context: PipelineContext) -> tuple[str, float]:
        """
        Gera código usando abordagem híbrida (Template + LLM).

        Args:
            context: Contexto do pipeline

        Returns:
            Tupla (código_gerado, confidence_score)
        """
        # 1. Gerar base via template
        base_code = self._generate_python_microservice(context.ticket.parameters)

        # 2. Enriquecer via LLM
        enhancement_prompt = f"""Enhance this code with production-ready features:

{base_code}

Add:
- Error handling
- Logging
- Configuration management
- Health checks
- Metrics

Maintain the existing structure."""

        constraints = {
            'language': context.ticket.parameters.get('language', 'python'),
            'framework': context.ticket.parameters.get('framework', ''),
            'patterns': ['error_handling', 'logging', 'metrics'],
            'max_lines': 2000
        }

        llm_result = await self.llm_client.generate_code(
            prompt=enhancement_prompt,
            constraints=constraints,
            temperature=0.3
        )

        if not llm_result:
            # Fallback para código base se enriquecimento falhar
            return base_code, 0.85

        enhanced_code = llm_result.get('code', base_code)
        llm_confidence = llm_result.get('confidence_score', 0.7)

        # Confidence híbrido (média ponderada)
        hybrid_confidence = (0.6 * llm_confidence) + (0.4 * 0.85)  # 0.85 = template confidence

        return enhanced_code, hybrid_confidence

    async def _build_rag_context(self, ticket) -> dict:
        """
        Constrói contexto RAG buscando templates similares e padrões arquiteturais.

        Args:
            ticket: Execution ticket

        Returns:
            Dict com similar_templates e architectural_patterns
        """
        if not self.analyst_client:
            return {"similar_templates": [], "architectural_patterns": []}

        try:
            # Query text para busca semântica
            query_text = f"{ticket.parameters.get('description', '')} {ticket.parameters.get('language', '')} {ticket.parameters.get('artifact_type', '')}"

            # Gerar embedding do query text
            embedding = await self.analyst_client.get_embedding(query_text)

            # Buscar templates similares usando embedding
            similar_templates = []
            if embedding:
                similar_templates = await self.analyst_client.find_similar_templates(
                    embedding=embedding,
                    top_k=5
                )
            else:
                logger.warning(
                    'embedding_generation_failed_skipping_template_search',
                    ticket_id=ticket.ticket_id
                )

            # Buscar padrões arquiteturais
            architectural_patterns = await self.analyst_client.get_architectural_patterns(
                domain=ticket.parameters.get('domain', 'TECHNICAL')
            )

            logger.info(
                'rag_context_built',
                ticket_id=ticket.ticket_id,
                similar_templates_count=len(similar_templates),
                patterns_count=len(architectural_patterns)
            )

            return {
                "similar_templates": similar_templates,
                "architectural_patterns": architectural_patterns
            }

        except Exception as e:
            logger.error(
                'rag_context_failed',
                ticket_id=ticket.ticket_id,
                error=str(e)
            )
            return {"similar_templates": [], "architectural_patterns": []}

    def _build_llm_prompt(self, ticket, rag_context: dict) -> str:
        """
        Constrói prompt estruturado para LLM com contexto RAG.

        Args:
            ticket: Execution ticket
            rag_context: Contexto RAG com templates similares e padrões arquiteturais

        Returns:
            Prompt estruturado para LLM
        """
        similar_templates = rag_context.get('similar_templates', [])
        architectural_patterns = rag_context.get('architectural_patterns', [])

        # Construir seção de templates similares
        templates_section = ""
        if similar_templates:
            templates_section = "\nSimilar Templates (for reference):\n"
            templates_section += "\n".join([
                f"- {t.get('text', 'Unknown')[:100]}... (similarity: {t.get('similarity', 0.0):.2f})"
                for t in similar_templates[:3]
            ])

        # Construir seção de padrões arquiteturais
        patterns_section = ""
        if architectural_patterns:
            patterns_section = "\nArchitectural Patterns to follow:\n"
            patterns_section += "\n".join([f"- {p}" for p in architectural_patterns[:5]])

        # Prompt completo
        prompt = f"""Generate a {ticket.parameters.get('artifact_type', 'microservice')} in {ticket.parameters.get('language', 'Python')}.

Service: {ticket.parameters.get('service_name', 'my-service')}

Requirements:
{ticket.parameters.get('description', 'No description provided')}
{chr(10).join(f'- {req}' for req in ticket.parameters.get('requirements', []))}
{templates_section}
{patterns_section}

Generate production-ready code with:
- Proper error handling
- Type hints and docstrings
- Unit tests
- Logging and observability hooks
- Following best practices for {ticket.parameters.get('language', 'Python')}
"""

        return prompt

    def _generate_heuristic(self, parameters: dict) -> str:
        """
        Geração baseada em regras determinísticas.

        Args:
            parameters: Parâmetros do ticket

        Returns:
            Código gerado via heurística
        """
        artifact_type = parameters.get('artifact_type', 'MICROSERVICE').upper()
        language = parameters.get('language', 'python').lower()
        service_name = parameters.get('service_name', 'my-service')

        logger.info(
            'heuristic_generation_started',
            artifact_type=artifact_type,
            language=language,
            service_name=service_name
        )

        # Selecionar gerador baseado em tipo e linguagem
        code = self._select_generator(artifact_type, language, parameters)

        logger.info(
            'heuristic_generation_completed',
            artifact_type=artifact_type,
            language=language,
            code_length=len(code)
        )

        return code

    def _select_generator(self, artifact_type: str, language: str, parameters: dict) -> str:
        """
        Seleciona o gerador apropriado baseado em tipo e linguagem.

        Args:
            artifact_type: Tipo do artefato
            language: Linguagem de programação
            parameters: Parâmetros do ticket

        Returns:
            Código gerado
        """
        # Mapeamento tipo -> função geradora
        type_generators = {
            'MICROSERVICE': {
                'python': self._generate_python_microservice,
                'javascript': self._generate_javascript_microservice,
                'typescript': self._generate_typescript_microservice,
                'go': self._generate_go_microservice,
                'java': self._generate_java_microservice,
                'rust': self._generate_rust_microservice,
            },
            'LIBRARY': {
                'python': self._generate_python_library,
                'javascript': self._generate_javascript_library,
                'typescript': self._generate_typescript_library,
                'go': self._generate_go_library,
            },
            'SCRIPT': {
                'python': self._generate_python_script,
                'javascript': self._generate_javascript_script,
                'bash': self._generate_bash_script,
            },
            'IAC_TERRAFORM': {
                'hcl': self._generate_terraform_module,
            },
            'IAC_HELM': {
                'yaml': self._generate_helm_chart,
            },
            'POLICY_OPA': {
                'rego': self._generate_opa_policy,
            },
        }

        # Buscar gerador específico
        generators = type_generators.get(artifact_type, {})
        generator = generators.get(language)

        if generator:
            return generator(parameters)

        # Fallback para gerador Python se linguagem não suportada
        logger.warning(
            'language_not_supported_fallback_to_python',
            artifact_type=artifact_type,
            language=language
        )
        return self._generate_python_microservice(parameters)

    def _generate_python_library(self, params: dict) -> str:
        """Gera biblioteca Python baseada em template"""
        library_name = params.get('service_name', 'my-lib')
        return f'''# {library_name} - Generated by Neural Code Forge
"""
{library_name} - A Python library
"""

__version__ = "0.1.0"


class {library_name.replace('-', '_').title()}:
    """Main library class"""

    def __init__(self):
        pass

    def process(self, data):
        """Process data"""
        return data
'''

    def _generate_python_script(self, params: dict) -> str:
        """Gera script Python baseado em template"""
        script_name = params.get('service_name', 'my-script')
        return f'''#!/usr/bin/env python3
# {script_name} - Generated by Neural Code Forge
"""
{script_name} - A Python script
"""

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    """Main function"""
    logger.info("Script started")
    # Add your logic here
    logger.info("Script completed")


if __name__ == "__main__":
    main()
'''

    def _generate_python_microservice(self, params: dict) -> str:
        """Gera código Python baseado em template"""
        service_name = params.get('service_name', 'my-service')
        description = params.get('description', 'Generated microservice')
        return f'''# {service_name} - Generated by Neural Code Forge
"""
{description}
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import structlog

logger = structlog.get_logger(__name__)
app = FastAPI(
    title="{service_name}",
    description="{description}",
    version="1.0.0"
)


class HealthResponse(BaseModel):
    """Resposta do health check"""
    status: str
    service: str


@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint"""
    return HealthResponse(status="healthy", service="{service_name}")


@app.get("/")
async def root():
    """Root endpoint"""
    return {{"message": "Welcome to {service_name}", "version": "1.0.0"}}
'''

    def _generate_javascript_microservice(self, params: dict) -> str:
        """Gera microservício em JavaScript/Node.js"""
        service_name = params.get('service_name', 'my-service')
        description = params.get('description', 'Generated microservice')
        return f'''// {service_name} - Generated by Neural Code Forge
/**
 * {description}
 */

const express = require('express');
const helmet = require('helmet');

const app = express();
const PORT = process.env.PORT || 3000;

// Middleware
app.use(helmet());
app.use(express.json());
app.use(express.urlencoded({{ extended: true }}));

// Health check
app.get('/health', (req, res) => {{
  res.json({{
    status: 'healthy',
    service: '{service_name}',
    timestamp: new Date().toISOString()
  }});
}});

// Root endpoint
app.get('/', (req, res) => {{
  res.json({{
    message: 'Welcome to {service_name}',
    version: '1.0.0'
  }});
}});

// Error handling
app.use((err, req, res, next) => {{
  console.error(err.stack);
  res.status(500).json({{
    error: 'Internal Server Error',
    message: process.env.NODE_ENV === 'production' ? 'An error occurred' : err.message
  }});
}});

// Start server
if (require.main === module) {{
  app.listen(PORT, () => {{
    console.log(`{service_name} listening on port ${{PORT}}`);
  }});
}}

module.exports = app;
'''

    def _generate_typescript_microservice(self, params: dict) -> str:
        """Gera microservício em TypeScript/Node.js"""
        service_name = params.get('service_name', 'my-service')
        className = service_name.replace('-', '').replace('_', '').title().replace(' ', '')
        return f'''// {service_name} - Generated by Neural Code Forge
/**
 * Generated TypeScript microservice
 */

import express, {{ Request, Response, Application }} from 'express';
import helmet from 'helmet';

const PORT = process.env.PORT || 3000;

interface HealthResponse {{
  status: string;
  service: string;
  timestamp: string;
}}

interface ErrorResponse {{
  error: string;
  message?: string;
}}

class {className}App {{
  private app: Application;

  constructor() {{
    this.app = express();
    this.setupMiddleware();
    this.setupRoutes();
    this.setupErrorHandling();
  }}

  private setupMiddleware(): void {{
    this.app.use(helmet());
    this.app.use(express.json());
    this.app.use(express.urlencoded({{ extended: true }}));
  }}

  private setupRoutes(): void {{
    this.app.get('/health', (req: Request, res: Response) => {{
      const response: HealthResponse = {{
        status: 'healthy',
        service: '{service_name}',
        timestamp: new Date().toISOString()
      }};
      res.json(response);
    }});

    this.app.get('/', (req: Request, res: Response) => {{
      res.json({{
        message: 'Welcome to {service_name}',
        version: '1.0.0'
      }});
    }});
  }}

  private setupErrorHandling(): void {{
    this.app.use((err: Error, req: Request, res: Response, next: any) => {{
      console.error(err.stack);
      const errorResponse: ErrorResponse = {{
        error: 'Internal Server Error',
        message: process.env.NODE_ENV === 'production' ? undefined : err.message
      }};
      res.status(500).json(errorResponse);
    }});
  }}

  public start(): void {{
    this.app.listen(PORT, () => {{
      console.log(`{service_name} listening on port ${{PORT}}`);
    }});
  }}

  public getApp(): Application {{
    return this.app;
  }}
}}

// Start application if run directly
if (require.main === module) {{
  const app = new {className}App();
  app.start();
}}

export default {className}App;
'''

    def _generate_go_microservice(self, params: dict) -> str:
        """Gera microservício em Go"""
        service_name = params.get('service_name', 'my-service')
        module_name = service_name.replace('-', '_')
        return f'''// Package main - {service_name} - Generated by Neural Code Forge
// {params.get('description', 'Generated microservice')}

package main

import (
	"encoding/json"
	"log"
	"net/http"
	"os"
	"time"
)

// HealthResponse representa a resposta do health check
type HealthResponse struct {{
	Status    string    `json:"status"`
	Service   string    `json:"service"`
	Timestamp time.Time `json:"timestamp"`
}}

// Response representa uma resposta genérica da API
type Response struct {{
	Message string `json:"message"`
	Version string `json:"version"`
}}

func healthHandler(w http.ResponseWriter, r *http.Request) {{
	w.Header().Set("Content-Type", "application/json")
	resp := HealthResponse{{
		Status:    "healthy",
		Service:   "{service_name}",
		Timestamp: time.Now(),
	}}
	json.NewEncoder(w).Encode(resp)
}}

func rootHandler(w http.ResponseWriter, r *http.Request) {{
	w.Header().Set("Content-Type", "application/json")
	resp := Response{{
		Message: "Welcome to {service_name}",
		Version: "1.0.0",
	}}
	json.NewEncoder(w).Encode(resp)
}}

func main() {{
	port := os.Getenv("PORT")
	if port == "" {{
		port = "8080"
	}}

	http.HandleFunc("/health", healthHandler)
	http.HandleFunc("/", rootHandler)

	log.Printf("{service_name} listening on port %s", port)
	if err := http.ListenAndServe(":"+port, nil); err != nil {{
		log.Fatalf("Failed to start server: %v", err)
	}}
}}
'''

    def _generate_java_microservice(self, params: dict) -> str:
        """Gera microservício em Java (Spring Boot)"""
        service_name = params.get('service_name', 'my-service')
        package_name = service_name.replace('-', '.')
        class_name = ''.join(word.title() for word in service_name.replace('-', ' ').split())
        return f'''// {service_name} - Generated by Neural Code Forge
package com.neuralhive.{package_name};

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.*;
import org.springframework.http.ResponseEntity;

import java.time.LocalDateTime;
import java.util.HashMap;
import java.util.Map;

/**
 * {params.get('description', 'Generated microservice')}
 */
@SpringBootApplication
@RestController
public class {class_name}Application {{

    public static void main(String[] args) {{
        SpringApplication.run({class_name}Application.class, args);
    }}

    @GetMapping("/health")
    public ResponseEntity<Map<String, Object>> health() {{
        Map<String, Object> response = new HashMap<>();
        response.put("status", "healthy");
        response.put("service", "{service_name}");
        response.put("timestamp", LocalDateTime.now().toString());
        return ResponseEntity.ok(response);
    }}

    @GetMapping("/")
    public ResponseEntity<Map<String, String>> root() {{
        Map<String, String> response = new HashMap<>();
        response.put("message", "Welcome to {service_name}");
        response.put("version", "1.0.0");
        return ResponseEntity.ok(response);
    }}
}}
'''

    def _generate_rust_microservice(self, params: dict) -> str:
        """Gera microservício em Rust"""
        service_name = params.get('service_name', 'my-service')
        return f'''// {service_name} - Generated by Neural Code Forge
// {params.get('description', 'Generated microservice')}

use actix_web::{{web, App, HttpResponse, HttpServer, Responder}};
use serde::Serialize;
use std::time::SystemTime;

#[derive(Serialize)]
struct HealthResponse {{
    status: String,
    service: String,
    timestamp: String,
}}

#[derive(Serialize)]
struct RootResponse {{
    message: String,
    version: String,
}}

async fn health() -> impl Responder {{
    let response = HealthResponse {{
        status: "healthy".to_string(),
        service: "{service_name}".to_string(),
        timestamp: SystemTime::now()
            .duration_since(SystemTime::UNIX_EPOCH)
            .unwrap()
            .as_secs()
            .to_string(),
    }};
    HttpResponse::Ok().json(response)
}}

async fn root() -> impl Responder {{
    let response = RootResponse {{
        message: format!("Welcome to {{}}", "{service_name}"),
        version: "1.0.0".to_string(),
    }};
    HttpResponse::Ok().json(response)
}}

#[actix_web::main]
async fn main() -> std::io::Result<()> {{
    let bind_address = "0.0.0.0:8080";
    HttpServer::new(move || {{
        App::new()
            .route("/health", web::get().to(health))
            .route("/", web::get().to(root))
    }})
    .bind(bind_address)?
    .run()
    .await
}}
'''

    def _generate_javascript_library(self, params: dict) -> str:
        """Gera biblioteca JavaScript"""
        lib_name = params.get('service_name', 'my-lib')
        return f'''// {lib_name} - Generated by Neural Code Forge
/**
 * {params.get('description', 'Generated JavaScript library')}
 */

'use strict';

class {lib_name.replace('-', '').replace('_', '').title().replace(' ', '')} {{
  constructor(options = {{}}) {{
    this.options = {{
      debug: false,
      ...options
    }};
  }}

  /**
   * Process data
   */
  process(data) {{
    if (this.options.debug) {{
      console.log('[{lib_name}] Processing:', data);
    }}
    return data;
  }}

  /**
   * Transform data
   */
  transform(data, fn) {{
    if (typeof fn !== 'function') {{
      throw new Error('Transform requires a function');
    }}
    return fn(data);
  }}
}}

module.exports = {lib_name.replace('-', '')};
module.exports.default = {lib_name.replace('-', '')};
'''

    def _generate_typescript_library(self, params: dict) -> str:
        """Gera biblioteca TypeScript"""
        lib_name = params.get('service_name', 'my-lib')
        className = lib_name.replace('-', '').replace('_', '').title().replace(' ', '')
        return f'''// {lib_name} - Generated by Neural Code Forge
/**
 * {params.get('description', 'Generated TypeScript library')}
 */

export interface {className}Options {{
  debug?: boolean;
}}

export type TransformFunction<T, R> = (data: T) => R;

export class {className} {{
  private options: {className}Options;

  constructor(options: {className}Options = {{}}) {{
    this.options = {{
      debug: false,
      ...options
    }};
  }}

  /**
   * Process data
   */
  public process<T>(data: T): T {{
    if (this.options.debug) {{
      console.log('[{lib_name}] Processing:', data);
    }}
    return data;
  }}

  /**
   * Transform data using a function
   */
  public transform<T, R>(data: T, fn: TransformFunction<T, R>): R {{
    if (typeof fn !== 'function') {{
      throw new Error('Transform requires a function');
    }}
    return fn(data);
  }}
}}

export default {className};
'''

    def _generate_go_library(self, params: dict) -> str:
        """Gera biblioteca Go"""
        lib_name = params.get('service_name', 'my-lib')
        package_name = lib_name.replace('-', '_')
        return f'''// Package {package_name} - {params.get('description', 'Generated Go library')}
// Generated by Neural Code Forge

package {package_name}

import (
	"fmt"
	"log"
)

// Options represents library configuration
type Options struct {{
	Debug bool
}}

// Library is the main struct
type Library struct {{
	opts Options
}}

// New creates a new Library instance
func New(opts Options) *Library {{
	if opts.Debug {{
		log.SetFlags(log.LstdFlags | log.Lshortfile)
	}}
	return &Library{{
		opts: opts,
	}}
}}

// Process processes input data
func (l *Library) Process(data interface{{}}) interface{{}} {{
	if l.opts.Debug {{
		log.Printf("[{lib_name}] Processing: %v", data)
	}}
	return data
}}

// Transform applies a transformation function
func (l *Library) Transform(data interface{{}}, fn func(interface{{}}) interface{{}}) interface{{}} {{
	return fn(data)
}}
'''

    def _generate_javascript_script(self, params: dict) -> str:
        """Gera script JavaScript"""
        script_name = params.get('service_name', 'my-script')
        return f'''#!/usr/bin/env node
// {script_name} - Generated by Neural Code Forge
/**
 * {params.get('description', 'Generated script')}
 */

const {{ program }} = require('commander');
const winston = require('winston');

const logger = winston.createLogger({{
  level: process.env.LOG_LEVEL || 'info',
  format: winston.format.combine(
    winston.format.timestamp(),
    winston.format.json()
  ),
  transports: [
    new winston.transports.Console({{
      format: winston.format.simple()
    }})
  ]
}});

program
  .name('{script_name}')
  .description('{params.get('description', 'Generated script')}')
  .version('1.0.0')
  .option('-v, --verbose', 'verbose output')
  .parse(process.argv);

async function main() {{
  logger.info('Script started');

  const options = program.opts();
  if (options.verbose) {{
    logger.level = 'debug';
  }}

  // Add your logic here
  logger.info('Processing...');

  logger.info('Script completed');
}}

main().catch(err => {{
  logger.error('Script failed', {{ error: err.message }});
  process.exit(1);
}});
'''

    def _generate_bash_script(self, params: dict) -> str:
        """Gera script Bash"""
        script_name = params.get('service_name', 'my-script')
        return f'''#!/bin/bash
# {script_name} - Generated by Neural Code Forge
# {params.get('description', 'Generated script')}

set -euo pipefail

# Colors for output
RED='\\033[0;31m'
GREEN='\\033[0;32m'
YELLOW='\\033[1;33m'
NC='\\033[0m' # No Color

# Logging functions
log_info() {{
    echo -e "${{GREEN}}[INFO]${{NC}} $*"
}}

log_warn() {{
    echo -e "${{YELLOW}}[WARN]${{NC}} $*"
}}

log_error() {{
    echo -e "${{RED}}[ERROR]${{NC}} $*" >&2
}}

# Main function
main() {{
    log_info "Starting {script_name}..."

    # Add your logic here

    log_info "{script_name} completed successfully"
}}

# Run main
main "$@"
'''

    def _generate_terraform_module(self, params: dict) -> str:
        """Gera módulo Terraform"""
        module_name = params.get('service_name', 'my-module')
        return f'''# Terraform Module - {module_name}
# Generated by Neural Code Forge
# {params.get('description', 'Generated Terraform module')}

variable "name" {{
  description = "Name prefix for resources"
  type        = string
  default     = "{module_name}"
}}

variable "environment" {{
  description = "Environment tag"
  type        = string
  default     = "dev"
}}

variable "tags" {{
  description = "Additional tags"
  type        = map(string)
  default     = {{}}
}}

# Locals
locals {{
  common_tags = merge(
    {{
      Name      = var.name
      ManagedBy = "Neural-Code-Forge"
      Environment = var.environment
    }},
    var.tags
  )
}}

# Outputs
output "resource_name" {{
  description = "Name of created resource"
  value       = var.name
}}

output "tags" {{
  description = "Tags applied to resources"
  value       = local.common_tags
}}
'''

    def _generate_helm_chart(self, params: dict) -> str:
        """Gera Helm Chart (values.yaml + Chart.yaml)"""
        chart_name = params.get('service_name', 'my-chart')
        return f'''# Helm Chart - {chart_name}
# Generated by Neural Code Forge

# Chart.yaml
apiVersion: v2
name: {chart_name}
description: {params.get('description', 'Generated Helm chart')}
type: application
version: 1.0.0
appVersion: "1.0.0"

# values.yaml
replicaCount: 1

image:
  repository: {chart_name}
  pullPolicy: IfNotPresent
  tag: "1.0.0"

service:
  type: ClusterIP
  port: 80

ingress:
  enabled: false

resources: {{
  limits:
    cpu: 500m
    memory: 512Mi
  requests:
    cpu: 250m
    memory: 256Mi
}}

autoscaling:
  enabled: false
  minReplicas: 1
  maxReplicas: 100
  targetCPUUtilizationPercentage: 80

nodeSelector: {{}}

tolerations: []

affinity: {{}}
'''

    def _generate_opa_policy(self, params: dict) -> str:
        """Gera política OPA/Rego"""
        policy_name = params.get('service_name', 'my-policy')
        return f'''# OPA Policy - {policy_name}
# Generated by Neural Code Forge
# {params.get('description', 'Generated OPA policy')}

package {policy_name.replace('-', '_')}

import data.lib.{policy_name.replace('-', '_')}

default allow = false

# Allow if all checks pass
allow {{
  not deny
}}

deny {{
  checks[msg]
}}

# Policy checks
checks[msg] {{
  not input.user
  msg := "User information is required"
}}

checks[msg] {{
  not input.action
  msg := "Action is required"
}}

checks[msg] {{
  input.action == "delete"
  not input.resource
  msg := "Resource is required for delete action"
}}

# Admin bypass
allow {{
  input.user.role == "admin"
}}

# Helper functions
is_authorized[action] {{
  allowed_actions[input.user.role][action]
}}

allowed_actions = {{
  "admin": ["create", "read", "update", "delete"],
  "user": ["read", "update"],
  "guest": ["read"],
}}
'''
