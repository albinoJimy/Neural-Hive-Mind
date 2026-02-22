# Índice de Documentos do Teste Manual - 2026-02-21

## 📁 Estrutura de Diretórios

```
docs/
├── TESTE_MANUAL_FLUXO_A_2026-02-21.md           (32KB) - Documentação principal do teste
├── TESTE_MANUAL_FLUXOS_A_B_C_2026-02-21_README.md (3.2KB) - Resumo executivo
├── test_tracking_ids_2026-02-21.txt              (266B) - IDs de rastreabilidade
├── consensus-decision-raw_2026-02-21.txt        (6.1KB) - Decisão bruta do MongoDB
├── intent-response_2026-02-21.json              (510B) - Resposta do Gateway
├── kafka-messages-consumed_2026-02-21.txt       (4.8KB) - Mensagens do Kafka
├── jaeger-traces-consensus_2026-02-21.json     (4.8KB) - Traces do Jaeger
└── test-raw-data/2026-02-21/                   (~75KB) - Todos os dados brutos
    ├── README.md                                (3.2KB) - Índice dos dados brutos
    ├── TESTE_MANUAL_PROFUNDO.md                 (34KB) - Plano original do teste
    ├── gateway/                                 - Dados do Gateway
    ├── kafka/                                   - Dados do Kafka
    ├── mongodb/                                 - Dados do MongoDB
    ├── jaeger/                                  - Dados do Jaeger
    ├── tracking/                                - IDs de rastreabilidade
    └── intents/                                 - Payloads de teste
```

## 📄 Documentos Principais

### 1. TESTE_MANUAL_FLUXO_A_2026-02-21.md (32KB, 959 linhas)

**O QUE É:** Documentação completa e detalhada do teste manual profundo executado no Neural Hive-Mind.

**CONTEÚDO:**
- Seção 1: Fluxo A - Gateway (Captura de Intenção)
  - 1.1 Health Check Gateway
  - 1.2 Submissão de Intenção
  - 1.3 Logs do Gateway
  - 1.4 Cache no Redis
  - 1.5 Mensagem no Kafka
  - 1.6 Conclusão do Fluxo A

- Seção 2: Fluxo B - STE - Structured Thinking Engine
  - 2.1 Geração de Planos
  - 2.2 Plano Gerado (Cognitive Plan)
  - 2.3 Conclusão do Fluxo B

- Seção 3: Fluxo C - Orchestrator & Workers
  - 3.1 Consumo pelo Orchestrator
  - 3.2 Execution Tickets
  - 3.3 Prometheus Metrics
  - 3.4 Jaeger Traces
  - 3.5 Conclusão do Fluxo C

- Seção 4: Resumo Executivo do Teste Completo
  - 4.1 Status Geral
  - 4.2 IDs de Rastreabilidade
  - 4.3 Problemas Críticos Identificados
  - 4.4 Métricas de Performance
  - 4.5 Recomendações Imediatas

- Seção 5: Conclusão Final

**COMO USAR:**
```bash
# Ler documentação completa
cat docs/TESTE_MANUAL_FLUXO_A_2026-02-21.md | less

# Buscar por seção específica
grep -A20 "### 2.1" docs/TESTE_MANUAL_FLUXO_A_2026-02-21.md
```

### 2. TESTE_MANUAL_FLUXOS_A_B_C_2026-02-21_README.md (3.2KB)

**O QUE É:** Resumo executivo e guia rápido de navegação pelos documentos do teste.

**CONTEÚDO:**
- Descrição do teste
- Lista de arquivos gerados
- Resultados resumidos dos Fluxos A, B e C
- Problemas críticos identificados
- IDs de rastreabilidade
- Próximos passos recomendados
- Credenciais usadas

**COMO USAR:**
```bash
# Visão rápida dos resultados
cat docs/TESTE_MANUAL_FLUXOS_A_B_C_2026-02-21_README.md
```

## 📊 Arquivos de Dados

### Dados Capturados

1. **test_tracking_ids_2026-02-21.txt** (266B)
   - IDs de rastreabilidade usados no teste
   - Intent ID, Correlation ID, Trace ID, Plan ID, Decision ID

2. **consensus-decision-raw_2026-02-21.txt** (6.1KB)
   - Documento RAW do MongoDB
   - Decisão completa do consenso
   - Votos dos 5 especialistas

3. **intent-response_2026-02-21.json** (510B)
   - Resposta RAW do Gateway
   - JSON válido com todos os campos

4. **kafka-messages-consumed_2026-02-21.txt** (4.8KB)
   - Mensagens do Kafka topic `plans.consensus`
   - Histórico de 10 mensagens recentes

5. **jaeger-traces-consensus_2026-02-21.json** (4.8KB)
   - Traces do serviço consensus-engine
   - JSON do Jaeger API

## 📁 Dados Brutos (test-raw-data/)

### Diretório: test-raw-data/2026-02-21/

**O QUE É:** Todos os dados brutos capturados durante o teste, organizados por tipo.

**ESTRUTURA:**
- `README.md` - Índice detalhado dos dados brutos
- `TESTE_MANUAL_PROFUNDO.md` - Plano original do teste (34KB)
- `gateway/` - Dados do Gateway (Fluxo A)
- `kafka/` - Dados do Kafka
- `mongodb/` - Dados do MongoDB (Fluxo B)
- `jaeger/` - Dados do Jaeger
- `tracking/` - IDs de rastreabilidade
- `intents/` - 17 payloads de teste diferentes

**TOTAL:** 26 arquivos (~75KB)

### Documentação de Dados Brutos

**Arquivo:** `test-raw-data/2026-02-21/README.md` (3.2KB)

**CONTEÚDO:**
- Descrição de cada arquivo
- IDs de rastreabilidade
- Credenciais usadas
- Formato dos dados (MongoDB, Kafka, Jaeger, Gateway)
- Como usar os dados

**COMO USAR:**
```bash
# Navegar pelos dados brutos
cd docs/test-raw-data/2026-02-21/
cat README.md

# Investigar decisão do consenso
cat mongodb/consensus-decision-raw.txt | grep -A20 "specialist_votes"

# Ver resposta do Gateway
cat gateway/intent-response.json | jq '.'

# Ler traces do Jaeger
cat jaeger/jaeger-traces-consensus.json | jq '.data[0]'
```

## 🔍 Como Investigar o Teste

### 1. Ver Resultados Resumidos
```bash
cat docs/TESTE_MANUAL_FLUXOS_A_B_C_2026-02-21_README.md
```

### 2. Ler Documentação Completa
```bash
cat docs/TESTE_MANUAL_FLUXO_A_2026-02-21.md | less
```

### 3. Navegar pelos Dados Brutos
```bash
cd docs/test-raw-data/2026-02-21/
cat README.md
```

### 4. Investigar Problemas Específicos

#### Ver Decisão do Consenso (Fluxo B)
```bash
cat docs/consensus-decision-raw_2026-02-21.txt | grep -A30 "specialist_votes"
```

#### Ver Mensagens do Kafka
```bash
cat docs/kafka-messages-consumed_2026-02-21.txt | tail -20
```

#### Ver Traces do Jaeger
```bash
cat docs/jaeger-traces-consensus_2026-02-21.json | jq '.data[0].spans[0]'
```

#### Ver Resposta do Gateway
```bash
cat docs/intent-response_2026-02-21.json | jq '.'
```

## 📈 Estatísticas do Teste

### Documentos
- **Total de arquivos:** 32
- **Tamanho total:** ~110KB
- **Linhas de documentação:** 959 linhas

### Dados Capturados
- **MongoDB documents:** 1 (consensus_decisions)
- **Kafka messages:** 10 (histórico)
- **Jaeger traces:** 2 (health checks)
- **Gateway responses:** 1
- **Intent payloads:** 17

### IDs de Rastreabilidade
- **Intent ID:** 327403ce-8292-46cb-a13a-d863de64cc5e
- **Correlation ID:** c3f7e2ca-0d2f-4662-bb9b-58b415c7dad1
- **Trace ID:** 53f92ad9258b95fc0e6e7a1d05e39c86
- **Plan ID:** d7e564dc-8319-41d0-8411-f636b3cbca46
- **Decision ID:** e4457805-4266-49a5-b4d5-f26e72867871

## ⚠️ Problemas Críticos Identificados

1. **Models Degraded (CRÍTICO)**
   - 5 specialists com confiança < 10%
   - Provável causa: modelos não treinados

2. **Baixa Confiança Agregada (CRÍTICO)**
   - Aggregated confidence: 21% (threshold: 50%)

3. **Alta Divergência (CRÍTICO)**
   - Divergence score: 41% (threshold: 35%)

4. **Consensus Method: Fallback (CRÍTICO)**
   - Sistema usando método de fallback

5. **Traces Ausentes (ALERTA)**
   - Jaeger não capturando traces de negócio

6. **Bug no Gateway (ALERTA)**
   - `convert_enum()` com erro de formato

## 🎯 Próximos Passos Recomendados

1. Treinar/re-treinar os 5 models dos specialists
2. Corrigir o bug no `convert_enum()` do Gateway
3. Configurar Jaeger para capturar traces de negócio
4. Implementar monitoramento de health dos models
5. Investigar causa raiz do estado degraded

## 🔗 Links Rápidos

### Documentação Principal
- [TESTE_MANUAL_FLUXO_A_2026-02-21.md](./TESTE_MANUAL_FLUXO_A_2026-02-21.md)
- [TESTE_MANUAL_FLUXOS_A_B_C_2026-02-21_README.md](./TESTE_MANUAL_FLUXOS_A_B_C_2026-02-21_README.md)

### Dados Capturados
- [test_tracking_ids_2026-02-21.txt](./test_tracking_ids_2026-02-21.txt)
- [consensus-decision-raw_2026-02-21.txt](./consensus-decision-raw_2026-02-21.txt)
- [intent-response_2026-02-21.json](./intent-response_2026-02-21.json)
- [kafka-messages-consumed_2026-02-21.txt](./kafka-messages-consumed_2026-02-21.txt)
- [jaeger-traces-consensus_2026-02-21.json](./jaeger-traces-consensus_2026-02-21.json)

### Dados Brutos
- [test-raw-data/2026-02-21/](./test-raw-data/2026-02-21/)
- [test-raw-data/2026-02-21/README.md](./test-raw-data/2026-02-21/README.md)

---
*Teste executado em 2026-02-21*
*Fluxos: A (Gateway), B (STE), C (Orchestrator)*
*Status: ⚠️ PARCIALMENTE FUNCIONAL COM PROBLEMAS CRÍTICOS*
