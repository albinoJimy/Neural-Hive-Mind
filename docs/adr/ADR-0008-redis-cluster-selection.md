# ADR-0008: Seleção de Redis Cluster para Camada de Memória

## Status

Aceito

## Contexto

O Neural Hive-Mind necessita de uma camada de memória de curto prazo para cache de intenções com TTL de 5-15 minutos, conforme especificado no documento-03-componentes-e-processos. A solução deve oferecer alta disponibilidade, distribuição multi-zona e integração nativa com Kubernetes e service mesh.

## Decisão

Utilizar Redis Operator para gerenciar Redis Cluster no Kubernetes ao invés de Helm chart oficial ou soluções cloud.

## Justificativa

### Redis Operator vs. Alternativas

**Redis Operator (Escolhido)**
- Gestão automatizada de cluster (scaling, failover)
- Backup/restore integrado com Kubernetes
- Observabilidade nativa com métricas Prometheus
- Integração transparente com service mesh Istio
- Configuração declarativa via CRDs

**Helm Chart Oficial**
- Configuração manual de cluster
- Failover não automatizado
- Gestão de backup externa

**ElastiCache/Azure Cache**
- Vendor lock-in
- Latência adicional de rede
- Custos elevados
- Menor controle operacional

**Hazelcast**
- Complexidade desnecessária
- Overhead de JVM
- Curva de aprendizado

## Configuração

- Cluster: 3 masters + 3 replicas
- Distribuição: multi-zona (HA)
- TTL padrão: 10 minutos
- Persistence: AOF + RDB
- Auth: Redis AUTH + TLS
- Integração: Istio service mesh

## Consequências

### Positivas
- Operação automatizada e confiável
- Integração nativa com stack Kubernetes
- Métricas e observabilidade completas
- Escalabilidade horizontal automática

### Negativas
- Dependência de operator externo
- Complexidade inicial de configuração
- Necessidade de expertise Redis Cluster

## Implementação

- Terraform module para Redis Operator
- Helm chart para configuração específica
- Políticas OPA para governança
- Integração com Gateway de Intenções