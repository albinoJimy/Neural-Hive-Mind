# Stack Técnico

## Framework de Aplicação
FastAPI 0.104.1+

## Linguagem
Python 3.11+

## Banco de Dados Primário
PostgreSQL 17+ (planejado para dados persistentes)
MongoDB (planejado para contexto operacional)
ClickHouse (planejado para analytics)

## ORM
SQLAlchemy (para PostgreSQL)

## Framework JavaScript
Não aplicável (sistema focado em backend)

## Ferramenta de Build
Docker + Docker Compose

## Estratégia de Import
Imports nativos do Python

## Gerenciador de Pacotes
pip com requirements.txt

## Versão do Node
Não aplicável

## Framework CSS
Não aplicável (sistema focado em backend)

## Componentes de UI
Não aplicável (sistema focado em backend)

## Instalação de UI
Não aplicável

## Provedor de Fontes
Não aplicável

## Carregamento de Fontes
Não aplicável

## Ícones
Não aplicável

## Hospedagem da Aplicação
AWS EKS (Elastic Kubernetes Service) em us-east-1

## Região de Hospedagem
us-east-1 (US East - N. Virginia)

## Hospedagem de Banco de Dados
AWS RDS para PostgreSQL (planejado)
MongoDB auto-gerenciado no EKS (planejado)
ClickHouse auto-gerenciado no EKS (planejado)

## Backups de Banco de Dados
Backups diários automatizados com recuperação point-in-time

## Armazenamento de Assets
Amazon S3

## CDN
Não aplicável (sistema focado em API)

## Acesso a Assets
Privado com políticas IAM

## Plataforma de CI/CD
GitHub Actions

## Trigger de CI/CD
Push para branches develop (deploy dev) e main (deploy prod)

## Testes
pytest com cobertura, executa antes do deployment

## Ambiente de Produção
branch main

## Ambiente de Staging
branch develop

## Componentes Adicionais de Infraestrutura

### Container Registry
Amazon ECR (Elastic Container Registry) com scanning de vulnerabilidades

### Service Mesh
Istio 1.19+ com modo mTLS STRICT

### Fila de Mensagens
Apache Kafka 3.5+ (gerenciado via Strimzi Operator) com semântica exactly-once

### Schema Registry
Confluent Schema Registry 7.4+ para schemas Avro

### Camada de Cache
Redis Cluster 7.0+ com SSL/TLS

### Autenticação
Keycloak 22+ provedor OAuth2/OIDC

### Motor de Políticas
OPA Gatekeeper 3.14+ para imposição de políticas Kubernetes

### Assinatura de Imagens
Sigstore Policy Controller para verificação de imagens de container

### Stack de Observabilidade
- OpenTelemetry Collector 0.88+
- Prometheus 2.47+ (métricas)
- Grafana 10.1+ (dashboards)
- Jaeger 1.50+ (rastreamento distribuído)

### Logging
Logging estruturado com structlog 23.2+ (formato JSON)

### Bibliotecas ML/IA
- OpenAI Whisper 20231117 (ASR - Reconhecimento Automático de Fala)
- spaCy 3.7.2 (NLU - Compreensão de Linguagem Natural)
- Transformers 4.36.2 (modelos Hugging Face)
- PyTorch 2.1.2 (inferência ML)
- NLTK 3.8.1 (utilitários NLP)

### Validação de Dados
Pydantic 2.5.2+ com type hints

### Runtime Assíncrono
uvicorn 0.24+ com ASGI

### Banco de Dados de Grafos
Neo4j 5.x ou JanusGraph (planejado para grafos de conhecimento)

### Event Sourcing
Temporal ou Cadence (planejado para orquestração)

### Infraestrutura como Código
Terraform 1.5+ para recursos AWS
Helm 3.13+ para deployments Kubernetes

### Controle de Versão
Git com GitHub

## URL do Repositório de Código
https://github.com/neural-hive-mind/neural-hive-mind (ou repositório privado da organização)