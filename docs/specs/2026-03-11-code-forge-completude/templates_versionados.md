# Templates Versionados - Guia de Uso

## Visão Geral

O CodeForge agora suporta versionamento de templates usando Git tags. Isso permite usar versões específicas de templates, garantindo reprodutibilidade e controle sobre mudanças.

## Como Usar

### 1. Listar Versões Disponíveis

Para verificar quais versões de templates estão disponíveis:

```python
from src.clients.git_client import GitClient

git_client = GitClient(
    templates_repo='https://github.com/minha-org/templates',
    templates_branch='main',
    local_path='/tmp/templates'
)

# Clone repositório
await git_client.clone_templates_repo()

# Listar tags disponíveis
tags = await git_client.list_tags()
# Exemplo: [{'name': 'v2.0.0', 'commit': 'abc123'}, ...]
```

### 2. Usar Versão Específica

Para usar uma versão específica de template em um Execution Ticket:

```python
from src.models.execution_ticket import ExecutionTicket

ticket = ExecutionTicket(
    ticket_id=str(uuid.uuid4()),
    task_type=TaskType.GENERATE,
    # ... outros campos ...
    parameters={
        'language': 'python',
        'artifact_type': 'MICROSERVICE',
        'template_version': 'v1.5.0'  # <- Versão específica do template
    }
)
```

### 3. Verificar Versão Atual

Para verificar qual versão está atualmente em uso:

```python
current_tag = await git_client.get_current_tag()
print(f"Versão atual: {current_tag}")  # 'v1.5.0' ou None
```

### 4. Fazer Checkout Manual de Versão

Para trocar manualmente entre versões:

```python
# Fazer checkout de tag específica
success = await git_client.checkout_tag('v1.0.0')
if success:
    print("Checkout realizado com sucesso")
```

## Convenções de Versionamento

Recomendamos usar [Semantic Versioning](https://semver.org/) para tags:

- `v1.0.0` - Versão estável inicial
- `v1.1.0` - Novas funcionalidades (backwards compatible)
- `v1.0.1` - Bug fixes
- `v2.0.0` - Mudanças breaking

## Comportamento do Cache

Quando uma versão específica é solicitada via `template_version`:

1. O CodeForge faz checkout da tag antes de carregar templates
2. O cache Redis usa a chave `type:language` (ignorando versão)
3. Para cache de versão específica, implemente cache key customizada

## Exemplo Completo

```python
from src.clients.git_client import GitClient
from src.services.template_selector import TemplateSelector
from src.models.pipeline_context import PipelineContext
from src.models.execution_ticket import ExecutionTicket, TaskType

# 1. Configurar GitClient
git_client = GitClient(
    templates_repo='https://github.com/minha-org/code-forge-templates',
    templates_branch='main',
    local_path='/opt/code-forge/templates'
)

# 2. Criar ticket com versão específica
ticket = ExecutionTicket(
    ticket_id='my-ticket-123',
    task_type=TaskType.GENERATE,
    status=TicketStatus.PENDING,
    priority=Priority.NORMAL,
    risk_band=RiskBand.MEDIUM,
    parameters={
        'language': 'python',
        'artifact_type': 'MICROSERVICE',
        'template_version': 'v1.5.0',  # Usa templates marcados com v1.5.0
        'service_name': 'user-api'
    },
    sla=SLA(...),
    qos=QoS(...),
    security_level=SecurityLevel.INTERNAL,
    created_at=datetime.now()
)

# 3. Executar seleção de template
context = PipelineContext(ticket=ticket)
selector = TemplateSelector(git_client=git_client, redis_client=redis_client)
template = await selector.select(context)

# O template v1.5.0 será usado
```

## Solução de Problemas

### Tag Não Encontrada

Se a tag solicitada não existir, o CodeForge registrará um warning e usará a versão mais recente do branch principal.

```
WARNING: template_version_not_found requested=v1.5.0 available=['v2.0.0', 'v1.0.0']
```

### Ver Tags Disponíveis

Use o método `list_tags()` para ver todas as versões disponíveis antes de especificar uma versão.
