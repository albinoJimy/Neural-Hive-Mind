# DEPENDENCY_AUDIT

## 1. Visão Geral da Auditoria

- **Metodologia:** execução do `pipdeptree` para mapear dependências transitivas, `pip-audit`/`safety` para identificar vulnerabilidades e análise estática de imports (`rg` + AST) para confrontar uso real vs. requirements.txt.
- **Escopo:** todos os 23 serviços e 4 bibliotecas Python do Neural Hive Mind (gateway, consensus, specialists, agents, APIs e camadas compartilhadas).
- **Data:** 2025-02-14 — baseline preparada após consolidação protobuf/grpc e segregação de requirements-prod/dev.
- **Biblioteca `neural_hive_specialists`:** `requirements-dev.txt` referencia `requirements.txt` (linha `-r`) e concentra dependências apenas de testes/DR (`pytest*`, `testcontainers`, `faker`, `grpcio-testing`, `boto3`, `google-cloud-storage`), mantendo o arquivo principal apenas com pacotes de runtime.

## 2. Matriz de Versões Consolidadas

| Dependência                          | Versão Recomendada | Observações                                                                                    |
|-------------------------------------|--------------------|------------------------------------------------------------------------------------------------|
| grpcio / grpcio-tools               | >= 1.75.1          | Compatível com protobuf 5.x e protoc 6.x; já usada por queen-agent e guard-agents.            |
| protobuf                            | >= 5.27.0          | Mesmo runtime da biblioteca `neural_hive_specialists`; evita incompatibilidades wire-format.  |
| fastapi                             | >= 0.104.1         | Versão consolidada, explainability-api pode permanecer em 0.109.0 (superset).                 |
| pydantic                            | >= 2.5.2           | Versão estável com correções críticas e compatível com FastAPI 0.104.1+.                      |
| aiokafka                            | >= 0.10.0          | Mesma versão utilizada pelos serviços Kafka mais recentes; depreca APIs antigas.              |
| motor                               | == 3.3.2           | Driver Mongo já validado em produção; manter fixo para consistência.                          |
| redis[hiredis]                      | >= 5.0.1           | Client consolidado para conexões Redis; incorpora hiredis para baixa latência.                |
| structlog                           | >= 23.2.0          | Alinha formatação de logs em serviços HTTP/gRPC.                                              |
| opentelemetry-* (api/sdk/exporters) | >= 1.21.0 / 0.42b0 | Instrumentação uniforme para FASTAPI e gRPC.                                                  |
| prometheus-client                   | >= 0.19.0          | Evita regressões em métricas e permite coleta em Python 3.11.                                 |

## 3. Dependências Não Utilizadas por Serviço

Resultado consolidado do `scripts/scan-unused-imports.py`:

- **Specialists (business/technical/behavior/evolution/architecture):** validar uso real de `pm4py`, `prophet`, `statsmodels`, `pulp`. Não foram encontrados imports diretos; manter somente se módulos forem carregados dinamicamente.
- **gateway-intencoes:** revisar `asyncio-mqtt` (nenhum import detectado). Preferir remoção caso não exista callback MQTTS.
- **Serviços HTTP leves:** revisar uso paralelo de `requests` quando `httpx` já cobre os fluxos.

## 4. Dependências Transitivas Redundantes

- `openai-whisper`: depende implicitamente de `torch`/`torchaudio`. Instalar manualmente `torch`/`torchaudio` antes e usar `pip install --no-deps openai-whisper==20231117` para impedir reinstalações redundantes.
- `numpy`: já instalado por `pandas/scipy`. Para libs de ML secundárias, utilizar `--no-deps` sempre que apropriado.
- `torch`/`torchaudio`: não reinstalar quando derivados de imagens base com CUDA.

## 5. Dependências Críticas e Justificativas

- **gateway-intencoes:** `openai-whisper` (pipeline ASR), `spacy` (NLU), `torch`/`torchaudio` (runtime do Whisper).
- **analyst-agents:** `sentence-transformers` (embeddings semânticos), `faiss-cpu` (busca vetorial), `scikit-learn`/`pandas`/`numpy` (análises).
- **specialist-*:** `spacy`, `pandas`, `scikit-learn` para análises; dependências pesadas (`pm4py`, `prophet`, `statsmodels`, `pulp`) exigem validação de uso real antes de manter.
- **consensus-engine:** `numpy`/`scipy` para algoritmos de consenso matemático.
- **consensus/orchestrator/worker/service-registry:** `opentelemetry-*` e `prometheus-client` garantem observabilidade consistente.

## 6. Plano de Migração de Versões

1. **Fase 1 – Serviços críticos (gateway-intencoes, queen-agent, consensus-engine, service-registry):** atualizar `grpcio/grpcio-tools` para >=1.75.1 e `protobuf` >=5.27.0; executar testes e2e de gRPC (`test-grpc-specialists.py`, `test-grpc-specialists.sh`).
2. **Fase 2 – Specialists:** aplicar requirements idênticos para os cinco serviços e validar se dependências pesadas são necessárias via `scripts/scan-unused-imports.py`.
3. **Fase 3 – Serviços auxiliares (orchestrator, SLA, semantic-translation, mcp-tool-catalog, code-forge, worker, scout, optimizer, execution-ticket):** alinhar Kafka/observabilidade.
4. **Comandos de teste por fase:**
   - `pytest tests/e2e/test_grpc_communication.py`
   - `python test-specialists-simple.py`
   - `pytest services/*/tests` conforme escopo.

## 7. Impacto Estimado

- **Tamanho de imagens:** redução de ~15–20% removendo dependências não utilizadas e segregando requirements-dev.
- **Tempo de build:** redução de ~10–15% por instalar menos pacotes durante docker build.
- **Confiabilidade:** eliminação de conflitos de versão e melhoria na segurança (pacotes atualizados).
- **Operação:** documentação e scripts de auditoria permitem repetição consistente e identificação rápida de regressões.
