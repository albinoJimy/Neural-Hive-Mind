# Spec Summary (Lite)

Tornar a migração de dados J4 real e funcional E2E: uma intenção `J4_MIGRATE` migra dados PostgreSQL
(legacy→moderno) de facto, com `rows_migrated == N` validado por contagem real, desbloqueando o que o
gate "J4/MIGRATE fiável" (Fase 4) provou estar bloqueado. Arquitetura: as activities de migração do
orchestrator passam a ser thin-wrappers HTTP sobre o serviço `data-migration` (fonte de verdade) — a 1ª
cria o job (`POST /migrations`), obtém o `job_id` real e propaga-o (resolve a desconexão job_id
orchestrator↔serviço). Escopo full-stack: corrige o orchestrator (wiring/job_id/db_urls) e o serviço
data-migration (bug da análise de schema `$1`, seed). Prova E2E o caminho negativo (destino
vazio→FAILED) e positivo (migração íntegra→completed). GENERATE em J4, cutover canary e over-commit do
cluster ficam Out-of-Scope.
