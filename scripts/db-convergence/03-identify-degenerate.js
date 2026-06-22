// 03-identify-degenerate.js — Fase 0 da convergencia-dbs
//
// Script mongosh READ-ONLY que IDENTIFICA (nao apaga) registos degenerados
// na colecao cognitive_ledger da DB neural_hive. Estes registos sao ruido de
// CRUD/smoke-test E2E e planos com "labels circulares" (rotulo de dominio
// derivado das mesmas keyword-rules que depois servem de label de treino),
// que poluem o corpus de migracao para neural_hive_dev (ver technical-spec.md:
// "manter dev; nao migrar legado degenerado").
//
// ZERO DELECAO: o script apenas conta e mostra amostras. A exclusao real e
// feita pelo filtro de migracao na Fase 1, nao aqui.
//
// Uso (via kubectl exec, read-only):
//   kubectl exec -n mongodb-cluster <mongo-pod> -c mongodb -- \
//     mongosh --quiet -u root -p "$MONGO_PASSWORD" --authenticationDatabase admin \
//     neural_hive --file /tmp/03-identify-degenerate.js
//   (copiar este ficheiro para /tmp do pod com kubectl cp, ou passar via --eval)
//
// CRITERIOS DE DEGENERACAO (explicitos, baseados em evidencia medida em
// 2026-06-21 sobre 10246 docs de cognitive_ledger em neural_hive):
//
//   C1 — CRUD/smoke genérico: o plano tem objetivo num conjunto CRUD
//        ({create, read, update, delete}). Estes nascem do CRUD E2E smoke,
//        nao de intencoes reais. (~3656 docs)
//
//   C2 — Plano trivial de tarefa unica: execution_order == ["task_0"]
//        (uma so tarefa generica), tipico de smoke-test. (~9903 docs)
//
//   C3 — Sem contexto de rastreio: trace_id e correlation_id ambos null
//        (planos gerados fora de um fluxo real rastreado). (~9637 docs)
//
//   C4 — Labels circulares / NER ausente: todas as entidades com
//        original_type e canonical_type a null — sinal de que o dominio/labels
//        vieram das keyword-rules e nao de extracao real (circularidade de
//        treino documentada em MEMORY: "labels circulares do keyword classifier").
//        (~3852 docs)
//
// CLASSIFICACAO:
//   - DEGENERADO (smoke CRUD): C1 AND C2 AND C3  -> exclusao certa da migracao.
//   - SUSPEITO (label circular): C4 isolado       -> rever antes de migrar.
//   - VALIDO (candidato a migracao): objetivo NAO-CRUD e com rastreio.

(function () {
  const c = db.cognitive_ledger;
  const total = c.countDocuments({});

  const CRUD = ["create", "read", "update", "delete"];

  // --- Filtros por criterio ---
  const fC1 = { "plan_data.tasks.parameters.objective": { $in: CRUD } };
  const fC2 = { "plan_data.execution_order": ["task_0"] };
  const fC3 = { "plan_data.trace_id": null, "plan_data.correlation_id": null };
  const fC4 = {
    "plan_data.tasks.parameters.entities.original_type": null,
    "plan_data.tasks.parameters.entities.canonical_type": null,
  };

  // --- Combinacoes de classificacao ---
  const fDegenerate = { $and: [fC1, fC2, fC3] }; // smoke CRUD certo
  const fSuspect = fC4; // label circular / NER ausente
  const fValid = {
    "plan_data.tasks.parameters.objective": { $nin: CRUD },
    "plan_data.trace_id": { $ne: null },
  };

  const counts = {
    total: total,
    C1_crud_objective: c.countDocuments(fC1),
    C2_single_task: c.countDocuments(fC2),
    C3_no_trace: c.countDocuments(fC3),
    C4_circular_labels: c.countDocuments(fC4),
    DEGENERATE_smoke_crud: c.countDocuments(fDegenerate),
    SUSPECT_circular_only: c.countDocuments(fSuspect),
    VALID_migration_candidate: c.countDocuments(fValid),
  };

  print("=== cognitive_ledger @ neural_hive — identificacao de degenerados (READ-ONLY) ===");
  print(JSON.stringify(counts, null, 2));

  // --- Amostras (sem dados sensiveis: so chaves identificadoras) ---
  function sample(filter, label, n) {
    print("\n--- amostra " + label + " (ate " + n + ") ---");
    c.find(filter)
      .limit(n)
      .forEach(function (d) {
        const td = d.plan_data || {};
        const t0 = (td.tasks && td.tasks[0]) || {};
        const p0 = (t0.parameters || {});
        print(
          JSON.stringify({
            plan_id: d.plan_id,
            objective: p0.objective,
            task_type: t0.task_type,
            execution_order: td.execution_order,
            trace_id: td.trace_id,
            original_domain: td.original_domain,
          })
        );
      });
  }

  sample(fDegenerate, "DEGENERATE_smoke_crud", 3);
  sample(fSuspect, "SUSPECT_circular_only", 3);
  sample(fValid, "VALID_migration_candidate", 3);

  print(
    "\nNOTA: este script NAO apaga nada. A exclusao dos degenerados e aplicada" +
      " como filtro no script de migracao da Fase 1."
  );
})();
