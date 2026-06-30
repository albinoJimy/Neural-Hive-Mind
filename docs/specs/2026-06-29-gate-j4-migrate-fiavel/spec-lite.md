# Spec Summary (Lite)

Estabelecer o gate "J4/MIGRATE fiável": provar E2E que uma intenção de migração de legado
(`journey=J4_MIGRATE`) produz um sistema migrado real e validado, compondo `INGEST → PLAN →
GENERATE → EXECUTE → MIGRATE` em vez de cair na `OrchestrationWorkflow` genérica. Reusa a
`GenerateCapability` (já provada em J3) e des-orfaniza o `DataMigrationWorkflow` (hoje registado mas
sem chamador). Cenário canónico: migração schema+dados PostgreSQL legacy→moderno com `/validate`
fail-closed (perda de dados / validação reprovada / endpoint indisponível → FAILED, sem verde falso).
É a pré-condição para extrair MIGRATE como capacidade autónoma, tal como "J3/BUILD fiável" precedeu a
extração de GENERATE.
