# Exemplos do Protocolo MCP

## Visão Geral

Este documento contém exemplos práticos de comunicação JSON-RPC 2.0 com os MCP Servers do Neural Hive-Mind.

## Trivy MCP Server

### Inicialização

**Request:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {
    "protocolVersion": "2024-11-05",
    "capabilities": {},
    "clientInfo": {
      "name": "mcp-tool-catalog",
      "version": "1.0.0"
    }
  }
}
```

**Response:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "protocolVersion": "2024-11-05",
    "capabilities": {
      "tools": {
        "listChanged": true
      }
    },
    "serverInfo": {
      "name": "Trivy MCP Server",
      "version": "1.0.0"
    }
  }
}
```

### Listar Ferramentas

**Request:**
```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/list",
  "params": {}
}
```

**Response:**
```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "tools": [
      {
        "name": "scan_image",
        "description": "Escaneia imagem de container para vulnerabilidades usando Trivy",
        "inputSchema": {
          "type": "object",
          "properties": {
            "image": {
              "type": "string",
              "description": "Nome da imagem (ex: nginx:latest)"
            },
            "severity": {
              "type": "string",
              "default": "HIGH,CRITICAL",
              "description": "Severidades a reportar"
            },
            "ignore_unfixed": {
              "type": "boolean",
              "default": true,
              "description": "Ignorar vulnerabilidades sem correção"
            }
          },
          "required": ["image"]
        }
      },
      {
        "name": "scan_filesystem",
        "description": "Escaneia sistema de arquivos para vulnerabilidades",
        "inputSchema": {
          "type": "object",
          "properties": {
            "path": {
              "type": "string",
              "description": "Caminho do diretório"
            },
            "scanners": {
              "type": "string",
              "default": "vuln,config,secret"
            }
          },
          "required": ["path"]
        }
      },
      {
        "name": "scan_repository",
        "description": "Escaneia repositório Git para vulnerabilidades",
        "inputSchema": {
          "type": "object",
          "properties": {
            "repo_url": {
              "type": "string",
              "description": "URL do repositório Git"
            },
            "branch": {
              "type": "string",
              "default": "main"
            }
          },
          "required": ["repo_url"]
        }
      }
    ]
  }
}
```

### Scan de Imagem

**Request:**
```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "scan_image",
    "arguments": {
      "image": "nginx:alpine",
      "severity": "HIGH,CRITICAL"
    }
  }
}
```

**Response:**
```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\"success\": true, \"image\": \"nginx:alpine\", \"vulnerability_counts\": {\"CRITICAL\": 0, \"HIGH\": 2, \"MEDIUM\": 0, \"LOW\": 0}, \"total_vulnerabilities\": 2, \"duration_seconds\": 15.3}"
      }
    ]
  }
}
```

## SonarQube MCP Server

### Quality Gate

**Request:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "get_quality_gate",
    "arguments": {
      "project_key": "my-project"
    }
  }
}
```

**Response:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\"success\": true, \"project_key\": \"my-project\", \"status\": \"PASSED\", \"conditions\": [{\"metric\": \"coverage\", \"status\": \"OK\", \"value\": \"85.5\", \"threshold\": \"80\"}]}"
      }
    ]
  }
}
```

### Buscar Issues

**Request:**
```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "get_issues",
    "arguments": {
      "project_key": "my-project",
      "severity": "CRITICAL,BLOCKER",
      "issue_type": "BUG,VULNERABILITY"
    }
  }
}
```

**Response:**
```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\"success\": true, \"project_key\": \"my-project\", \"total_issues\": 3, \"severity_counts\": {\"CRITICAL\": 1, \"BLOCKER\": 2}, \"issues\": [{\"key\": \"AX12...\", \"severity\": \"CRITICAL\", \"type\": \"BUG\", \"message\": \"Null pointer dereference\", \"component\": \"src/main.py\", \"line\": 42}]}"
      }
    ]
  }
}
```

## AI CodeGen MCP Server

### Gerar Código

**Request:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "generate_code",
    "arguments": {
      "prompt": "Criar função Python para calcular fatorial recursivamente",
      "language": "python",
      "provider": "openai",
      "max_tokens": 500
    }
  }
}
```

**Response:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\"success\": true, \"provider\": \"openai\", \"language\": \"python\", \"code\": \"def factorial(n: int) -> int:\\n    \\\"\\\"\\\"Calcula o fatorial de n recursivamente.\\\"\\\"\\\"\\n    if n <= 1:\\n        return 1\\n    return n * factorial(n - 1)\", \"model\": \"gpt-4-turbo-preview\", \"usage\": {\"prompt_tokens\": 25, \"completion_tokens\": 45}}"
      }
    ]
  }
}
```

### Explicar Código

**Request:**
```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "explain_code",
    "arguments": {
      "code": "def qsort(arr):\n    if len(arr) <= 1:\n        return arr\n    pivot = arr[len(arr) // 2]\n    left = [x for x in arr if x < pivot]\n    middle = [x for x in arr if x == pivot]\n    right = [x for x in arr if x > pivot]\n    return qsort(left) + middle + qsort(right)",
      "language": "python"
    }
  }
}
```

**Response:**
```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\"success\": true, \"provider\": \"openai\", \"explanation\": \"Este código implementa o algoritmo QuickSort...\"}"
      }
    ]
  }
}
```

## Erros

### Ferramenta Não Encontrada

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "error": {
    "code": -32601,
    "message": "Method not found",
    "data": {
      "tool": "ferramenta_inexistente"
    }
  }
}
```

### Parâmetros Inválidos

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "error": {
    "code": -32602,
    "message": "Invalid params",
    "data": {
      "missing": ["image"],
      "message": "Parâmetro obrigatório 'image' não fornecido"
    }
  }
}
```

### Erro Interno

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "error": {
    "code": -32603,
    "message": "Internal error",
    "data": {
      "message": "Timeout ao executar scan",
      "timeout_seconds": 300
    }
  }
}
```

## Teste via curl

### Health Check
```bash
curl -s http://localhost:3000/health | jq
```

### Initialize
```bash
curl -X POST http://localhost:3000 \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {}
  }' | jq
```

### List Tools
```bash
curl -X POST http://localhost:3000 \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/list",
    "params": {}
  }' | jq
```

### Call Tool
```bash
curl -X POST http://localhost:3000 \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 3,
    "method": "tools/call",
    "params": {
      "name": "scan_image",
      "arguments": {
        "image": "alpine:latest"
      }
    }
  }' | jq
```
