# Code Composer - CodeForge

## Visão Geral

O **Code Composer** é o Subpipeline 2 do CodeForge, responsável por gerar código em múltiplas linguagens e formatos baseado no template selecionado.

```
┌─────────────────────────────────────────────────────────────────────┐
│                        CODE COMPOSER                                │
├─────────────────────────────────────────────────────────────────────┤
│  Entrada:                                                           │
│  ├── selected_template      (Template Selector)                    │
│  ├── ticket                 (ExecutionTicket)                      │
│  └── generation_method      (TEMPLATE/LLM/HYBRID/HEURISTIC)         │
├─────────────────────────────────────────────────────────────────────┤
│  Saída:                                                            │
│  ├── CodeForgeArtifact       (código gerado)                       │
│  ├── content_uri             (mongodb://artifacts/{id})             │
│  └── confidence_score        (0.0 a 1.0)                            │
└─────────────────────────────────────────────────────────────────────┘
```

## Métodos de Geração

| Método | Descrição | Confidence | Uso |
|--------|-----------|------------|-----|
| **TEMPLATE** | Template pré-definido | 0.85 | Padrão, mais rápido |
| **HEURISTIC** | Regras determinísticas | 0.78 | Sem LLM disponível |
| **LLM** | Geração via IA com RAG | 0.70+ | Código customizado |
| **HYBRID** | Template + LLM enrichment | 0.75-0.90 | Melhor dos dois mundos |

## Fluxo de Geração

```
                    ┌─────────────────┐
                    │ PipelineContext │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
         TEMPLATE?        LLM?        HYBRID?   HEURISTIC?
              │              │              │          │
              ▼              ▼              ▼          ▼
        ┌──────────┐   ┌──────────┐   ┌──────────┐ ┌───────────┐
        │ Template │   │   LLM    │   │ Template │ │ Heuristic │
        │  Generator│  │ + RAG    │   │ + LLM    │ │  Rules    │
        └─────┬────┘   └─────┬────┘   └─────┬────┘ └─────┬─────┘
              │              │              │              │
              └──────────────┴──────────────┴──────────────┘
                             │
                    ┌────────▼────────┐
                    │ Save to MongoDB │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │CodeForgeArtifact│
                    └─────────────────┘
```

## Linguagens Suportadas

### Microserviços

| Linguagem | Framework | Gerador | Arquivo |
|-----------|-----------|---------|---------|
| **Python** | FastAPI | `_generate_python_microservice()` | `code_composer.py:479` |
| **JavaScript** | Express | `_generate_javascript_microservice()` | `code_composer.py:518` |
| **TypeScript** | Express | `_generate_typescript_microservice()` | `code_composer.py:574` |
| **Go** | net/http | `_generate_go_microservice()` | `code_composer.py:664` |
| **Java** | Spring Boot | `_generate_java_microservice()` | `code_composer.py:729` |
| **Rust** | Actix-web | `_generate_rust_microservice()` | `code_composer.py:776` |
| **C#** | ASP.NET | DockerfileGenerator | `dockerfile_generator.py:452` |

> **Nota C#:** Code generation por TEMPLATE está parcialmente implementado (apenas Dockerfile). Use modo LLM para código C# completo.

### Bibliotecas

| Linguagem | Gerador | Arquivo |
|-----------|---------|---------|
| **Python** | `_generate_python_library()` | `code_composer.py:431` |
| **JavaScript** | `_generate_javascript_library()` | `code_composer.py:834` |
| **TypeScript** | `_generate_typescript_library()` | `code_composer.py:877` |
| **Go** | `_generate_go_library()` | `code_composer.py:926` |

> **Nota:** Bibliotecas para Java, Rust e C# não estão implementadas. Use o modo LLM ou c manualmente.

### Scripts

| Linguagem | Gerador | Arquivo |
|-----------|---------|---------|
| **Python** | `_generate_python_script()` | `code_composer.py:453` |
| **JavaScript** | Commander + Winston | `_generate_javascript_script()` | `code_composer.py:974` |
| **Bash** | `_generate_bash_script()` | `code_composer.py:1026` |

> **Nota:** Scripts para Go, Java, Rust e C# use o modo LLM ou TEMPLATE com customização.

### Infrastructure as Code

| Tipo | Gerador | Arquivo |
|------|---------|---------|
| **Terraform** | `_generate_terraform_module()` | `code_composer.py:1067` |
| **Helm** | `_generate_helm_chart()` | `code_composer.py:1116` |
| **OPA/Rego** | `_generate_opa_policy()` | `code_composer.py:1167` |

> **Nota:** Para Kubernetes manifests nativos, CloudFormation, e outras ferramentas IaC, use o modo LLM.

## Exemplo: Microserviço Python

```python
# Input
parameters = {
    'service_name': 'user-api',
    'description': 'User management API',
    'language': 'python',
    'artifact_type': 'MICROSERVICE'
}

# Output (TEMPLATE)
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import structlog

logger = structlog.get_logger(__name__)
app = FastAPI(
    title="user-api",
    description="User management API",
    version="1.0.0"
)

class HealthResponse(BaseModel):
    """Resposta do health check"""
    status: str
    service: str

@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint"""
    return HealthResponse(status="healthy", service="user-api")

@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "Welcome to user-api", "version": "1.0.0"}
```

## Exemplo: Microserviço TypeScript

```typescript
// Output (TEMPLATE)
import express, { Request, Response, Application } from 'express';
import helmet from 'helmet';

const PORT = process.env.PORT || 3000;

interface HealthResponse {
  status: string;
  service: string;
  timestamp: string;
}

class UserApiApp {
  private app: Application;

  constructor() {
    this.app = express();
    this.setupMiddleware();
    this.setupRoutes();
    this.setupErrorHandling();
  }

  private setupMiddleware(): void {
    this.app.use(helmet());
    this.app.use(express.json());
  }

  private setupRoutes(): void {
    this.app.get('/health', (req: Request, res: Response) => {
      res.json({
        status: 'healthy',
        service: 'user-api',
        timestamp: new Date().toISOString()
      });
    });
  }

  // ...
}

export default UserApiApp;
```

## RAG Context (LLM Mode)

Quando usando modo LLM, o Code Composer busca:

1. **Templates Similares** - Top-5 templates semelhantes via embedding
2. **Padrões Arquiteturais** - Padrões do domínio (TECHNICAL, SECURITY, etc.)

```
Query: "python microservice user management"
         │
         ▼
┌─────────────────┐
│ Analyst Agents  │ → Embedding + Similarity Search
└─────────────────┘
         │
         ▼
┌─────────────────────────────┐
│ RAG Context                 │
│ ├── similar_templates (5)   │
│ └── architectural_patterns  │
└─────────────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│ LLM Prompt + Context        │
└─────────────────────────────┘
```

## Matriz de Tipos de Artefato

### ArtifactCategory (categorias de alto nível)

| Tipo | Descrição |
|------|-----------|
| CODE | Código fonte de aplicação |
| IAC | Infrastructure as Code |
| TEST | Testes unitários/integração |
| POLICY | Políticas (OPA/Rego) |
| DOCUMENTATION | Documentação gerada |
| CONTAINER | Definições de container |
| CHART | Helm Charts |
| FUNCTION | Serverless functions |

### ArtifactSubtype (subtipos específicos)

| Tipo | Descrição |
|------|-----------|
| microservice | Serviço HTTP com HEALTHCHECK |
| lambda_function | Função serverless compacta |
| cli_tool | Ferramenta de linha de comando |
| library | Pacote/biblioteca para importação |
| script | Script executável |

> **Nota:** ArtifactSubtype é usado pelo DockerfileGenerator para selecionar o template apropriado.

## Uso

```python
from src.services.code_composer import CodeComposer
from src.services.pipeline_engine import PipelineContext

code_composer = CodeComposer(
    mongodb_client=mongodb_client,
    llm_client=llm_client,      # Opcional
    analyst_client=analyst_client,  # Opcional
    mcp_client=mcp_client       # Opcional
)

await code_composer.compose(context)

# Acessar artefato gerado
artifact = context.artifacts[0]
print(f"Artifact ID: {artifact.artifact_id}")
print(f"Method: {artifact.generation_method}")
print(f"Confidence: {artifact.confidence_score}")
print(f"Content URI: {artifact.content_uri}")
```

## Seleção de Gerador

```python
def _select_generator(artifact_type: str, language: str, parameters: dict) -> str:
    """
    Seleciona o gerador baseado em tipo e linguagem.

    Matrix (usando tipos unificados):
    type_generators = {
        'MICROSERVICE': {
            'python': _generate_python_microservice,
            'javascript': _generate_javascript_microservice,
            'typescript': _generate_typescript_microservice,
            'go': _generate_go_microservice,
            'java': _generate_java_microservice,
            'rust': _generate_rust_microservice,
        },
        'LIBRARY': {
            'python': _generate_python_library,
            'javascript': _generate_javascript_library,
            'typescript': _generate_typescript_library,
            'go': _generate_go_library,
        },
        'SCRIPT': {
            'python': _generate_python_script,
            'javascript': _generate_javascript_script,
            'bash': _generate_bash_script,
        },
        'IAC_TERRAFORM': {
            'hcl': _generate_terraform_module,
        },
        'IAC_HELM': {
            'yaml': _generate_helm_chart,
        },
        'POLICY_OPA': {
            'rego': _generate_opa_policy,
        },
    }

    Tipos disponíveis em src/types/artifact_types.py:
    - ArtifactCategory: CODE, IAC, TEST, POLICY, DOCUMENTATION, CONTAINER, CHART, FUNCTION
    - ArtifactSubtype: microservice, lambda_function, cli_tool, library, script
    - CodeLanguage: python, javascript, typescript, go, java, rust, csharp, bash, hcl, yaml, rego
    """
```

## Integrações MCP

O Code Composer integra com **MCP Tool Catalog** para:

- Seleção de ferramentas especializadas
- Enriquecimento de metadados
- Rastreamento de ferramentas utilizadas

```python
metadata = {
    'mcp_selection_id': mcp_selection_id,
    'mcp_tools_used': ','.join(tool_names)
}
```
