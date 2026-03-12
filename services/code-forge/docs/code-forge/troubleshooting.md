# Guia de Troubleshooting - CodeForge Container Builds

## Problemas Comuns e Soluções

## Dockerfile Generator

### Problema: Linguagem não suportada

**Sintoma:**
```python
ValueError: Linguagem não suportada: ruby
Suportadas: [SupportedLanguage.PYTHON, SupportedLanguage.NODEJS, ...]
```

**Solução:**
Use uma linguagem suportada:
- Python, Node.js, Go, Java, TypeScript, C#

### Problema: Template vazio gerado

**Sintoma:**
```python
dockerfile = generator.generate_dockerfile(language=SupportedLanguage.PYTHON)
# dockerfile == ""
```

**Causa Possível:** Bug na implementação do template

**Solução:**
1. Verifique se o método `_get_<language>_template` existe
2. Verifique se retorna uma string não-vazia
3. Abra issue no repositório

### Problema: Framework não reconhecido

**Sintoma:** Dockerfile gerado usa configurações genéricas em vez de específicas do framework

**Solução:**
O framework é ignorado silenciosamente. Use um dos frameworks suportados:
- Python: fastapi, flask
- Node.js: express, nest
- TypeScript: nestjs, express
- Go: gin, echo
- Java: spring-boot
- C#: aspnet, webapi

## Container Builder

### Problema: Docker daemon não rodando

**Sintoma:**
```
error during connect: ConnectionRefusedError
```

**Diagnóstico:**
```bash
docker --version
docker info
```

**Solução:**
```bash
# Iniciar Docker daemon
sudo systemctl start docker

# Ou no macOS/Windows: iniciar Docker Desktop
```

### Problema: Permissão negada

**Sintoma:**
```
Got permission denied while trying to connect to the Docker daemon socket
```

**Solução:**
```bash
# Adicionar usuário ao grupo docker
sudo usermod -aG docker $USER

# Fazer logout e login novamente
# Ou executar: newgrp docker
```

**Alternativa sem sudo:**
```bash
# Adicionar ao ~/.bashrc ou ~/.zshrc
export DOCKER_HOST=unix:///run/user/1000/docker.sock
```

### Problema: Contexto de build muito grande

**Sintoma:**
- Build muito lento
- Erro "context too large"

**Solução:**
1. Criar `.dockerignore`:
```
.git
.gitignore
__pycache__
*.pyc
node_modules
.env
.env.*
*.log
tests/
docs/
.vscode/
.idea/
*.md
```

2. Mover arquivos desnecessários para fora do context

### Problema: Build timeout

**Sintoma:**
```
ContainerBuildResult(success=False, error_message="Build timeout after 3600 seconds")
```

**Solução:**
```python
builder = ContainerBuilder(
    timeout_seconds=7200  # Aumentar para 2 horas
)
```

### Problema: Build falha com "no such file or directory"

**Sintoma:**
```
ERROR: failed to compute cache key: failed to calculate checksum of ref...
"/requirements.txt": not found
```

**Causa:** Arquivo não existe no build context

**Solução:**
1. Verifique que o arquivo existe no build context
2. Verifique se o caminho está correto (maiúsculas/minúsculas)
3. Para Docker compose, verifique o volume mount

## PipelineEngine

### Problema: enable_container_build=False não funciona

**Sintoma:** Stages `dockerfile_generation` e `container_build` ainda executam

**Causa:** `enable_container_build` só controla a execução do build, não a geração do Dockerfile

**Solução:** Esta é a funcionalidade esperada. O Dockerfile é sempre gerado para documentação, mas o build é pulado quando `enable_container_build=False`.

### Problema: Imagem não é criada

**Sintoma:**
```python
result = await engine.execute_pipeline(ticket)
# result.metadata["container_image"] está vazio
```

**Diagnóstico:**
1. Verifique logs para erros de build
2. Verifique se `enable_container_build=True`
3. Verifique se Docker daemon está rodando

**Solução:**
```python
# Verifique configuração
engine = PipelineEngine(
    # ...
    enable_container_build=True  # Deve ser True
)

# Verifique logs
logger.info("container_build_completed", **result.metadata.get("container_image", {}))
```

## Integração com Registry

### Problema: Push falha com "unauthorized"

**Sintoma:**
```
error saving artifact: unauthorized: authentication required
```

**Solução:**
1. Fazer login no registry:
```bash
docker login registry.example.com
```

2. Ou configurar credenciais:
```python
# Via environment variables
import os
os.environ["REGISTRY_USERNAME"] = "myuser"
os.environ["REGISTRY_PASSWORD"] = "mypassword"
```

### Problema: Tag de imagem rejeitada

**Sintoma:**
```
Error: invalid reference format
```

**Solução:**
Use formato válido de tag:
- `nome:versão` ✅
- `nome/namespace:versão` ✅
- `latest` (evitar em produção) ⚠️

## Testes

### Problema: Testes E2E falham com "Build failed"

**Sintoma:**
```
FAILED test_container_build_e2e.py::test_python_container_build_e2e
assert result.success is True: Build failed
```

**Causa:** Testes E2E de builds reais requerem Docker daemon

**Solução 1 - Habilitar Docker:**
```bash
# Verificar Docker
docker --version

# Se não tiver, instalar Docker Desktop ou Docker daemon
```

**Solução 2 - Pular testes de build:**
```bash
# Rodar apenas testes unitários
pytest tests/unit/

# Ou marcar testes E2E de build para pular
pytest tests/e2e/test_container_build_e2e.py -k "not test_python_container_build"
```

## Performance

### Problema: Build muito lento

**Diagnóstico:**
```python
result = await builder.build_container(...)
print(f"Duração: {result.duration_ms}ms")
```

**Soluções:**

1. **Usar cache de dependências:**
```dockerfile
# Copiar requirements primeiro
COPY requirements.txt .
RUN pip install -r requirements.txt
# Depois copiar código
COPY . .
```

2. **Minimizar context:** Usar .dockerignore

3. **Usar imagens base locais:** Pré-pull imagens base

4. **Parallelizar builds:** Build múltiplas imagens simultaneamente

### Problema: Imagem final muito grande

**Diagnóstico:**
```python
result = await builder.build_container(...)
print(f"Tamanho: {result.size_bytes / 1024 / 1024:.1f} MB")
```

**Soluções:**

1. **Usar alpine em vez de slim:**
```dockerfile
FROM python:3.11-alpine  # Menor que slim
```

2. **Remover dependências desnecessárias:** Limpe requirements.txt/package.json

3. **Multi-stage otimizado:** Copie apenas arquivos necessários

4. **`.dockerignore` no build context:** Exclua arquivos temporários

## Logs e Debug

### Habilitar Debug Logging

```python
import structlog

# Configurar logging nível DEBUG
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.dev.ConsoleRenderer()
    ],
    context_class=dict,
    log_level=logging.DEBUG
)

logger = structlog.get_logger()
logger.debug("dockerfile_content", dockerfile=dockerfile)
```

### Logs do Docker

```bash
# Ver logs do container
docker logs <container_id>

# Ver logs do build
docker build --progress=plain -t test .
```

## Erros Específicos

### "No space left on device"

**Causa:** Disco cheio

**Solução:**
```bash
# Limpar imagens unused
docker image prune -a

# Limpar containers parados
docker container prune

# Limpar tudo (cuidado!)
docker system prune -a
```

### "failed to solve: failed to compute cache key"

**Causa:** Arquivo referenciado no COPY não existe

**Solução:** Verifique:
1. Se o arquivo existe no build context
2. Se o caminho está correto (case sensitive)
3. Se .dockerignore não está excluindo o arquivo

### "Cannot connect to Docker daemon"

**Causa:** Docker daemon não está rodando

**Solução:**
```bash
# Linux
sudo systemctl start docker

# macOS
open -a Docker

# Windows
Start Docker Desktop
```

## Checklist de Diagnóstico

Antes de pedir ajuda, verifique:

### Docker
- [ ] Docker daemon está rodando (`docker info`)
- [ ] Usuário tem permissão do Docker (`groups | grep docker`)
- [ ] Docker CLI funciona (`docker --version`)

### Build Context
- [ ] Dockerfile existe no caminho especificado
- [ ] Build context contém arquivos necessários
- [ ] .dockerignore configurado corretamente
- [ ] Não há segredos no context

### Imagem
- [ ] Tag da imagem está em formato válido
- [ ] Imagem base pode ser baixada
- [ ] Espaço em disco suficiente (>1GB livre)

### Código
- [ ] Linguagem é suportada
- [ ] Framework é reconhecido
- [ ] Arquivos de dependência existem (requirements.txt, package.json)

## Contato e Suporte

Se o problema persistir:

1. **Coletar informações:**
   - Mensagem de erro completa
   - Versão do Docker (`docker version`)
   - Comando executado
   - Conteúdo do Dockerfile (sem segredos)

2. **Verificar logs:**
   - Logs do PipelineEngine
   - Logs do Docker daemon
   - Logs do ContainerBuilder

3. **Abrir issue:**
   - Repository: neural-hive-mind
   - Tag: bug, container-build, ou help-wanted
   - Incluir informações coletadas acima
