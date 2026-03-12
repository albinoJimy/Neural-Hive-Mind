# FAQ - Perguntas Frequentes - CodeForge

## Visão Geral

Perguntas frequentes sobre o uso, configuração e troubleshooting do CodeForge.

## Índice

1. [Conceitos Básicos](#conceitos-básicos)
2. [Docker e Containers](#docker-e-containers)
3. [Pipeline e Execução](#pipeline-e-execução)
4. [Validação e Segurança](#validação-e-segurança)
5. [Integração e Deploy](#integração-e-deploy)
6. [Troubleshooting](#troubleshooting)
7. [Performance e Otimização](#performance-e-otimização)

---

## Conceitos Básicos

### O que é o CodeForge?

O CodeForge é um serviço de geração de código que implementa builds de container reais como parte do pipeline de execução. Ele gera código, Dockerfiles, executa builds de containers e valida segurança em um fluxo unificado.

### Quais linguagens são suportadas?

O CodeForge suporta 6 linguagens:
- **Python**: FastAPI, Flask
- **Node.js**: Express, NestJS
- **TypeScript**: NestJS, Express
- **Go**: Gin, Echo (genérico)
- **Java**: Spring Boot
- **C#**: ASP.NET Core

### O que é um CodeForgeTicket?

Um `CodeForgeTicket` é a estrutura de dados que representa uma solicitação de geração de código. Contém:
- `ticket_id`: Identificador único
- `intent_description`: Descrição do que deve ser gerado
- `parameters`: Configurações específicas (linguagem, framework, etc.)
- `artifact_type`: Tipo do artefato (microservice, lambda, cli_tool, etc.)

### O que são os stages do pipeline?

O pipeline possui 8 stages:
1. **template_selection**: Seleção do template MCP
2. **code_composition**: Geração do código
3. **dockerfile_generation**: Geração do Dockerfile
4. **container_build**: Build da imagem de container
5. **validation**: Scans de segurança e qualidade
6. **testing**: Execução de testes (opcional)
7. **packaging**: Geração de SBOM e assinatura
8. **approval_gate**: Gate de aprovação manual ou automática

---

## Docker e Containers

### Preciso ter Docker instalado?

Depende. Se `enable_container_build=True`, sim - você precisa do Docker daemon rodando. Se `enable_container_build=False`, o Dockerfile é gerado mas o build não é executado.

### Como verificar se o Docker está rodando?

```bash
docker --version      # Verifica versão do Docker CLI
docker info           # Verifica se daemon está acessível
docker ps             # Lista containers (testa conexão)
```

### Posso usar o CodeForge sem Docker?

Sim! Configure `enable_container_build=False`:
```python
engine = PipelineEngine(
    enable_container_build=False  # Gera Dockerfile, não executa build
)
```

### Qual é o tamanho médio das imagens geradas?

Depende da linguagem e configurações:
- **Go (scratch)**: ~5-20 MB
- **Python slim**: ~150-200 MB
- **Node.js alpine**: ~100-150 MB
- **Java JRE**: ~200-250 MB

### Como reduzir o tamanho da imagem?

1. Use imagens base menores (alpine ao invés de slim)
2. Multi-stage builds
3. Remova dependências desnecessárias
4. Use `.dockerignore` para excluir arquivos
5. Para Go, compile para `scratch`

### O que é multi-stage build?

Multi-stage build permite usar múltiplos `FROM` no Dockerfile, criando estágios separados:
- **Builder stage**: Contém ferramentas de compilação
- **Final stage**: Contém apenas o runtime necessário

Isso reduz drasticamente o tamanho da imagem final.

---

## Pipeline e Execução

### Quanto tempo demora um pipeline?

Depende do tipo:
- **Sem container build**: ~10-30 segundos
- **Com container build**: ~2-10 minutos (depende do tamanho)
- **Com validações completas**: +1-3 minutos

### O que acontece se um stage falhar?

Por padrão, o pipeline continua e marca como `REQUIRES_REVIEW` se não for crítica. Falhas críticas (ex: validação de segurança com vulnerabilidades críticas) interrompem o pipeline.

### Como habilitar/desabilitar stages específicos?

```python
# Desabilitar build de container
engine = PipelineEngine(
    enable_container_build=False
)

# Desabilitar validações específicas
validator = Validator(
    enabled_validations=["vulnerability_scan"]  # Apenas esta
)
```

### O que é `auto_approval_threshold`?

É o limiar de confiança (0.0 a 1.0) para aprovação automática. Se a confiança do pipeline for maior que esse valor, o artefato é auto-aprova. Caso contrário, vai para aprovação manual.

```python
engine = PipelineEngine(
    auto_approval_threshold=0.9  # Requer 90% de confiança
)
```

### Como faço retry de um pipeline falhado?

O pipeline não tem retry automático, mas você pode:
```python
max_retries = 3
for attempt in range(max_retries):
    result = await engine.execute_pipeline(ticket)
    if result.status == "COMPLETED":
        break
    await asyncio.sleep(5 * (attempt + 1))  # Backoff
```

### Posso executar stages individualmente?

Sim:
```python
stage_result = await engine.execute_stage(
    stage_name="dockerfile_generation",
    ticket=ticket,
    context={}
)
```

---

## Validação e Segurança

### Quais ferramentas de segurança são usadas?

- **Trivy**: Scan de vulnerabilidades em containers e filesystem
- **SonarQube**: Análise de qualidade de código
- **Snyk** (opcional): Scan de dependências

### O que acontece se encontrar vulnerabilidades críticas?

O pipeline é marcado como `FAILED` e não prossegue para aprovação.

```python
if result.critical_count > 0:
    status = "FAILED"
```

### Como configurar o threshold de vulnerabilidades?

```python
from src.clients.trivy_client import VulnerabilitySeverity

result = await trivy_client.scan_filesystem(
    path="/app",
    severity=["CRITICAL", "HIGH"]  # Apenas estas
)
```

### O que é SBOM?

SBOM (Software Bill of Materials) é uma lista de todas as dependências do projeto, incluindo versões e licenças. O CodeForge gera SBOM automaticamente no formato SPDX-JSON.

### Como assinar artefatos?

O CodeForge usa Sigstore para assinar artefatos:
```python
from src.clients.sigstore_client import SigstoreClient

client = SigstoreClient()
await client.sign_artifact(artifact_path="/app/myapp")
```

---

## Integração e Deploy

### Como integrar com CI/CD?

```yaml
# .github/workflows/codeforge.yml
name: CodeForge Build
on: [push]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run CodeForge
        run: python -m src.cli build --ticket-id ${{ github.sha }}
```

### Como fazer push para um registry privado?

```python
# Após build bem-sucedido
result = await builder.build_container(...)

if result.success:
    # Tag para registry
    import subprocess
    subprocess.run([
        "docker", "tag",
        result.image_tag,
        "registry.example.com/myapp:1.0.0"
    ])

    # Push
    subprocess.run([
        "docker", "push",
        "registry.example.com/myapp:1.0.0"
    ])
```

### Como configurar credenciais de registry?

```bash
# Via Docker CLI
docker login registry.example.com

# Via variáveis de ambiente
export REGISTRY_USERNAME=myuser
export REGISTRY_PASSWORD=mypassword
```

### O CodeForge suporta Kubernetes?

O suporte a Kaniko (builds em Kubernetes sem Docker daemon) está planejado para FASE 3.

---

## Troubleshooting

### Docker daemon não rodando

**Sintoma:** `error during connect: ConnectionRefusedError`

**Solução:**
```bash
# Linux
sudo systemctl start docker

# macOS
open -a Docker

# Windows
Start Docker Desktop
```

### Permissão negada no Docker

**Sintoma:** `Got permission denied while trying to connect to the Docker daemon socket`

**Solução:**
```bash
# Adicionar usuário ao grupo docker
sudo usermod -aG docker $USER

# Fazer logout e login novamente
# Ou usar newgrp docker
```

### Build context muito grande

**Sintoma:** Build muito lento ou erro de contexto

**Solução:** Crie `.dockerignore`:
```
.git
node_modules
__pycache__
*.pyc
tests/
docs/
.env
*.log
```

### Template vazio gerado

**Sintoma:** `dockerfile == ""`

**Causa:** Linguagem não suportada ou bug no template

**Solução:**
```python
# Verifique se está usando SupportedLanguage
from src.services.dockerfile_generator import SupportedLanguage

dockerfile = generator.generate_dockerfile(
    language=SupportedLanguage.PYTHON  # Use a enum
)
```

### Build timeout

**Sintoma:** `Build timeout after 3600 seconds`

**Solução:**
```python
builder = ContainerBuilder(
    timeout_seconds=7200  # 2 horas
)
```

### "No such file or directory" no build

**Sintoma:** `"/requirements.txt": not found`

**Solução:**
1. Verifique que o arquivo existe no build context
2. Verifique caminho (maiúsculas/minúsculas)
3. Verifique se `.dockerignore` não está excluindo o arquivo

### Validação nunca termina

**Sintoma:** Stage de validation fica travado

**Solução:**
```python
validator = Validator(
    timeout_seconds=300  # 5 minutos máximo
)
```

---

## Performance e Otimização

### Como acelerar o build?

1. **Cache de dependências**: Copie `requirements.txt`/`package.json` antes do código
2. **Minimize context**: Use `.dockerignore`
3. **BuildKit**: Habilitite BuildKit para cache distribuído
4. **Imagens base locais**: Pré-pull imagens base

### Posso fazer builds em paralelo?

Sim:
```python
import asyncio

async def parallel_build():
    tasks = [
        builder.build_container(...) for _ in range(5)
    ]
    results = await asyncio.gather(*tasks)
    return results
```

### Como otimizar para cache do Docker?

```dockerfile
# Copiar dependências primeiro (muda pouco)
COPY requirements.txt .
RUN pip install -r requirements.txt

# Depois copiar código (muda muito)
COPY . .
```

### Qual o impacto das validações no tempo?

- Trivy scan: ~30-60 segundos
- SonarQube analysis: ~1-3 minutos
- Snyk scan: ~30-60 segundos

Total: ~2-5 minutos adicionais.

---

## Erros Comuns

### ValueError: Linguagem não suportada

**Causa:** Usou string em vez da enum

**Solução:**
```python
# ❌ Errado
dockerfile = generator.generate_dockerfile(language="ruby")

# ✅ Certo
dockerfile = generator.generate_dockerfile(
    language=SupportedLanguage.PYTHON
)
```

### AttributeError: 'PipelineResult' object has no attribute 'generated_artifacts'

**Causa:** Atributo incorreto

**Solução:**
```python
# ❌ Errado
artifacts = result.generated_artifacts

# ✅ Certo
artifacts = result.artifacts
```

### TypeError: 'NoneType' object is not callable

**Causa:** Cliente externo não configurado

**Solução:**
```python
validator = Validator(
    trivy_client=TrivyClient(),  # Instanciar clientes
    sonarqube_client=SonarQubeClient(...)
)
```

---

## Boas Práticas

### Devo versionar as imagens?

Sim! Evite usar `latest` em produção:
```python
# ❌ Evitar
image_tag="myapp:latest"

# ✅ Usar
image_tag="myapp:v1.2.3"
```

### Devo usar usuário não-root?

Sim! Todos os templates do CodeForge já criam usuário não-root automaticamente.

### Como lidar com segredos?

NUNCA inclua senhas/tokens no Dockerfile. Use:
- Variáveis de ambiente em runtime
- Kubernetes Secrets
- AWS Secrets Manager
- HashiCorp Vault

### Devo commitar o Dockerfile gerado?

Depende. Se o Dockerfile é gerado automaticamente, geralmente não é necessário. Mas se houver customizações manuais, sim.

---

## Recursos Adicionais

- [Architecture](architecture.md)
- [API Reference](api-reference.md)
- [Examples](examples.md)
- [Troubleshooting](troubleshooting.md)
- [Sequence Diagrams](sequence-diagrams.md)

## Suporte

Para problemas não cobertos aqui:
1. Consulte o [Troubleshooting](troubleshooting.md)
2. Verifique os [Examples](examples.md)
3. Abra uma issue no repositório com logs completos
