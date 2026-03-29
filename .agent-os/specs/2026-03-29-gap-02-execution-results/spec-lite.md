# Spec Summary (Lite)

Implementar consumer do tópico `execution.results` no Orchestrator Dynamic. Worker Agents publicam resultados mas nenhum serviço consome, deixando workflows Temporal aguardando timeout. Solução: consumer Kafka que envia signal `ticket_completed` para workflow Temporal, completando o feedback loop de execução.

**Status Atual:** Worker Agents publicam, consumo vazio
**Status Alvo:** Consumer processa resultados → signal Temporal → workflow continua
**Risco:** MÉDIO (mudança em schema e novo consumer)
