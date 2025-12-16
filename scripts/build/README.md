# Build CLI Unificado

CLI unificado para build e push de imagens Docker do Neural Hive-Mind.

## Uso

```bash
./scripts/build.sh [OPTIONS]
```

## Targets

| Target | Descrição |
|--------|-----------|
| `local` | Build local apenas (sem push) |
| `ecr` | Build + push para Amazon ECR |
| `registry` | Build + push para registry local |
| `all` | Build + push para ECR e registry local |

## Opções

| Opção | Descrição | Padrão |
|-------|-----------|--------|
| `--target` | Target de build | `local` |
| `--version` | Versão das imagens | `1.0.7` |
| `--parallel` | Jobs paralelos | `4` |
| `--services` | Serviços específicos (separados por vírgula) | Todos |
| `--no-cache` | Build sem cache | - |
| `--skip-base-images` | Pular build de imagens base | - |
| `--env` | Ambiente (dev/staging/prod) | `dev` |
| `--region` | Região AWS | `us-east-1` |
| `--registry` | URL do registry local | `37.60.241.150:30500` |

## Exemplos

### Build Local

```bash
# Build padrão
./scripts/build.sh --target local

# Build com versão específica
./scripts/build.sh --target local --version 1.0.8

# Build com mais paralelização
./scripts/build.sh --target local --parallel 8

# Build sem cache
./scripts/build.sh --target local --no-cache
```

### Build e Push para ECR

```bash
# Build e push padrão
./scripts/build.sh --target ecr

# Build e push com versão específica
./scripts/build.sh --target ecr --version 1.0.8 --env staging

# Build e push para região específica
./scripts/build.sh --target ecr --region us-west-2
```

### Build e Push para Registry Local

```bash
# Build e push para registry padrão
./scripts/build.sh --target registry

# Build e push para registry customizado
./scripts/build.sh --target registry --registry 192.168.1.100:5000
```

### Build Serviços Específicos

```bash
# Build apenas Gateway e Consensus Engine
./scripts/build.sh --target local --services "gateway-intencoes,consensus-engine"

# Build e push apenas specialists
./scripts/build.sh --target ecr --services "specialist-business,specialist-technical"
```

## Arquitetura

```
scripts/
├── build.sh              # CLI principal (orquestrador)
├── build/
│   ├── base-images.sh   # Build de imagens base
│   ├── services.sh      # Build de serviços
│   ├── local.sh         # Build local
│   ├── ecr.sh           # Push para ECR
│   └── registry.sh      # Push para registry local
└── lib/
    ├── common.sh        # Funções comuns
    ├── docker.sh        # Funções Docker
    └── aws.sh           # Funções AWS
```

## Migração de Scripts Antigos

| Script Antigo | Comando Novo |
|---------------|--------------|
| `./scripts/build-local-parallel.sh --version 1.0.8` | `./scripts/build.sh --target local --version 1.0.8` |
| `./scripts/push-to-ecr.sh --version 1.0.8` | `./scripts/build.sh --target ecr --version 1.0.8` |
| `./scripts/build-and-push-to-registry.sh build gateway-intencoes` | `./scripts/build.sh --target registry --services gateway-intencoes` |
| `./scripts/rebuild-all-images.sh` | `./scripts/build.sh --target all --no-cache` |

## Troubleshooting

### Erro: "Docker não está rodando"

```bash
# Verificar status do Docker
docker info

# Iniciar Docker (Linux)
sudo systemctl start docker
```

### Erro: "Credenciais AWS inválidas"

```bash
# Configurar AWS CLI
aws configure

# Verificar credenciais
aws sts get-caller-identity
```

### Erro: "Registry não disponível"

```bash
# Verificar conectividade
curl -sf http://37.60.241.150:30500/v2/

# Deploy registry local
helm install registry helm-charts/docker-registry -n registry --create-namespace
```
