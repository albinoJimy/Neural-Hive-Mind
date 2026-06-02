# Spec Requirements Document

> Spec: Consolidação de Namespaces do Orchestrator-Dynamic
> Created: 2026-06-01
> Status: Planning

## Overview

Consolidar as referências fragmentadas ao serviço `orchestrator-dynamic`, hoje espalhadas por 3 namespaces (um canónico saudável, um legacy quebrado e um inexistente), num único endpoint canónico. O objetivo é alinhar todos os clientes (host, porta, protocolo, TLS), corrigir uma referência morta e desativar com segurança os deployments legacy, eliminando os pods presos e a duplicação operacional.

## User Stories

### Operador elimina ambiguidade do orchestrator

Como operador da plataforma, quero que exista um único `orchestrator-dynamic` canónico e que todos os agentes apontem para ele, para que não haja pods presos, endpoints mortos nem dúvidas sobre qual instância serve tráfego real.

Hoje, ao diagnosticar o orchestrator, encontram-se 3 namespaces (`orchestrator-dynamic`, `neural-hive`, `neural-hive-orchestration`) com estados e portas diferentes; o legacy em `neural-hive` mantém 2 pods presos em `Init` (montagem de socket SPIRE inexistente) e o `self-healing-engine` aponta para um namespace sem deployment. A consolidação remove esta confusão.

### Cliente gRPC reconecta ao orchestrator correto

Como agente cliente (queen-agent, optimizer-agents, self-healing-engine), quero apontar para o host/porta/protocolo corretos do orchestrator canónico, para que as minhas chamadas de orquestração funcionem de forma fiável e não dependam de um deployment legacy em fim de vida.

Atualmente os 3 clientes usam hosts e portas divergentes (`:50051`, `:50053`, `:50052` com TLS) enquanto o canónico expõe apenas `http:8003` — é necessário determinar o contrato correto e alinhar a configuração de cada cliente.

## Spec Scope

1. **Determinação do contrato canónico** - Investigar e decidir o protocolo/porta de comunicação do orchestrator canónico (gRPC vs HTTP), confirmando se o gRPC foi descontinuado ou se o service canónico precisa de expor a porta gRPC.
2. **Alinhamento dos clientes** - Atualizar os ConfigMaps/env de `queen-agent`, `optimizer-agents` e `self-healing-engine` para apontarem para o host, porta, protocolo e TLS corretos do orchestrator canónico.
3. **Correção da referência morta** - Corrigir o `self-healing-engine`, que aponta para `neural-hive-orchestration` (namespace sem deployment nem endpoints).
4. **Desativação segura dos legacy** - Após confirmar que nenhum tráfego depende deles, escalar a zero e remover (via Helm) os deployments/services legacy em `neural-hive` (e qualquer recurso órfão em `neural-hive-orchestration`).
5. **Validação ponta-a-ponta** - Confirmar que os 3 clientes comunicam com o canónico e que não restam pods presos nem endpoints mortos.

## Out of Scope

- Alterações à lógica de negócio do orchestrator ou dos agentes (apenas configuração de conectividade/namespace).
- Reintrodução do SPIRE/SPIFFE no cluster (a montagem do socket SPIRE deixa de ser necessária ao remover o legacy).
- Migração da base image `python-observability-base` (já concluída noutra entrega).
- Alterações ao orchestrator canónico que não sejam a exposição da porta gRPC, caso se confirme necessária.

## Expected Deliverable

1. Os 3 clientes (queen-agent, optimizer-agents, self-healing-engine) ligam-se com sucesso ao orchestrator canónico (verificável por logs de conexão sem erros e health checks dos clientes a passar).
2. Não existem deployments/pods `orchestrator-dynamic` fora do namespace canónico (verificável via `kubectl get deploy,pods -A | grep orchestrator-dynamic`), nem endpoints mortos referenciados.
3. Zero pods presos em `Init` por montagem de socket SPIRE.
