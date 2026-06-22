// 10-migrate-corpus.js — Fase 1 da convergencia-dbs
//
// Migracao ADITIVA, IDEMPOTENTE e NAO-DESTRUTIVA do corpus de treino valido
// neural_hive -> neural_hive_dev. COPIA (nao move): neural_hive fica intacta
// como fallback vivo ate ao corte (Fase 4). Aplica o principio de desenho do
// technical-spec.md: "migrar dados antes de repontar".
//
// Coleccoes migradas (mapa de migracao do technical-spec.md):
//   specialist_feedback, specialist_opinions (de-dup), plan_approvals,
//   plan_features, explainability_ledger.
// NOTA: nenhuma destas 5 coleccoes tem filtro de degenerados — os degenerados
// vivem em cognitive_ledger, que NAO migra (0 candidatos validos, ver
// 03-identify-degenerate.js). O "menos degenerados" do DoD aplica-se via a
// exclusao integral de cognitive_ledger, nao por filtro dentro destas 5.
//
// SEMANTICA: INSERT-IF-ABSENT pela CHAVE UNICA NATURAL de cada coleccao.
//   - Nunca faz replace -> nao clobra documentos frescos ja presentes no alvo.
//   - Preserva o _id de origem -> re-execucao re-deteta os mesmos docs e nao duplica.
//   - specialist_opinions: de-dup LOGICA adicional (plan_id+specialist_type+created_at)
//     para nao introduzir duplicados logicos sob outro opinion_id/_id.
//   - Concorrencia: o cluster esta vivo. Um DuplicateKey (cod. 11000) no insert
//     (chave inserida pelo pipeline entre o snapshot e o flush) e BENIGNO —
//     conta como salto, nao reprova a migracao (o indice unico ja garante 0 dup).
//
// INDICES: recria todos os indices da origem no alvo (excepto _id_) e garante
// o indice TTL GDPR de 2 anos (m002_gdpr_ttl_indexes.py) em plan_approvals e
// specialist_feedback no alvo. createIndex e idempotente (conflitos de indice
// equivalente, cod. 85/86, sao benignos).
//   AVISO conhecido: o m002 cria o TTL de specialist_feedback no campo
//   `created_at`, mas esses docs usam `submitted_at` -> o indice fica INERTE
//   (TTL sobre campo ausente nunca expira). Replicamos o m002 fielmente (e o
//   contrato nomeado no DoD; divergir criaria conflito quando o approval-service
//   correr o m002 no alvo) mas SINALIZAMOS o quirk em `ttl_warnings` em vez de
//   o mascarar. A correccao do campo do m002 e um ticket proprio do approval-service.
//
// INTEGRIDADE (DoD 2.4): em modo APPLY, alem de provar a presenca de cada chave
// de origem no alvo (missing==0), faz AMOSTRAGEM de conteudo: para ate SAMPLE_N
// docs de origem copiados (mesmo _id no alvo), compara o payload integral
// (igualdade canonica). content_mismatches>0 reprova a migracao.
//
// MODOS:
//   globalThis.APPLY === true  -> escreve no alvo (indices + copia).
//   APPLY ausente/false        -> DRY-RUN: so conta o que faria, zero escrita.
//   globalThis.SRC_DB (default "neural_hive"), globalThis.DST_DB (default "neural_hive_dev").
//   globalThis.SAMPLE_N (default 25) -> tamanho da amostra de integridade por coleccao.
//
// Uso (via wrapper 10-migrate-corpus.sh; ou manual):
//   mongosh ... --eval "globalThis.APPLY=true; load('/tmp/10-migrate-corpus.js')"
//
// Saida: bloco JSON "=== MIGRATION RESULT (JSON) ===" parseavel pelo wrapper,
// com contagens por coleccao e o veredicto de completude.

(function () {
  var APPLY = typeof globalThis.APPLY !== "undefined" ? !!globalThis.APPLY : false;
  var SRC_DB = typeof globalThis.SRC_DB !== "undefined" ? globalThis.SRC_DB : "neural_hive";
  var DST_DB = typeof globalThis.DST_DB !== "undefined" ? globalThis.DST_DB : "neural_hive_dev";
  var SAMPLE_N = typeof globalThis.SAMPLE_N !== "undefined" ? globalThis.SAMPLE_N : 25;
  var BATCH = 500;
  var TWO_YEARS_SECONDS = 63072000; // == m002_gdpr_ttl_indexes.TWO_YEARS_SECONDS

  var src = db.getSiblingDB(SRC_DB);
  var dst = db.getSiblingDB(DST_DB);

  // Mapa de migracao: coleccao -> chave unica natural (skip-if-absent) +
  // de-dup logica opcional. As chaves unicas vieram de getIndexes() na origem.
  var COLLECTIONS = [
    { name: "specialist_feedback", key: "feedback_id" },
    {
      name: "specialist_opinions",
      key: "opinion_id",
      logicalKey: ["plan_id", "specialist_type", "created_at"],
    },
    { name: "plan_approvals", key: "plan_id" },
    { name: "plan_features", key: "plan_id" },
    { name: "explainability_ledger", key: "_id" },
  ];

  // Coleccoes que recebem o indice TTL GDPR (m002), com o campo de expiracao.
  var GDPR_TTL = [
    { coll: "plan_approvals", field: "created_at" },
    { coll: "specialist_feedback", field: "created_at" },
  ];

  // --- Helper: serializa um valor de chave para comparacao em memoria ---
  function ser(v) {
    if (v === null || typeof v === "undefined") return " null";
    if (v instanceof ObjectId) return "oid:" + v.toString();
    if (v instanceof Date) return "dt:" + v.toISOString();
    if (typeof v === "string") {
      // Normaliza strings que parecem timestamps ISO (created_at heterogeneo:
      // Date numa DB, string ISO noutra) para nao falhar a de-dup logica.
      // UUIDs/ids nao casam o regex -> ficam intactos (sem falsos positivos).
      if (/^\d{4}-\d{2}-\d{2}[T ]/.test(v)) {
        var t = Date.parse(v);
        if (!isNaN(t)) return "dt:" + new Date(t).toISOString();
      }
      return "v:" + v;
    }
    return "v:" + String(v);
  }
  function serLogical(doc, fields) {
    return fields.map(function (f) { return ser(doc[f]); }).join("|");
  }

  // --- Helper: forma canonica do doc para comparacao de conteudo ---
  function canon(doc) {
    try { return EJSON.stringify(doc); } catch (e) { return JSON.stringify(doc); }
  }

  // Codigos de erro Mongo tratados como benignos (nao reprovam):
  //   11000 DuplicateKey | 85 IndexOptionsConflict | 86 IndexKeySpecsConflict
  function errCode(e) {
    if (!e) return undefined;
    if (typeof e.code !== "undefined") return e.code;
    if (e.err && typeof e.err.code !== "undefined") return e.err.code;
    return undefined;
  }

  // --- 1) Recriar indices da origem no alvo (idempotente) ---
  function recreateIndexes(name) {
    var created = [], errors = [];
    src[name].getIndexes().forEach(function (ix) {
      if (ix.name === "_id_") return;
      var opts = { name: ix.name };
      if (ix.unique) opts.unique = true;
      if (typeof ix.expireAfterSeconds !== "undefined") opts.expireAfterSeconds = ix.expireAfterSeconds;
      if (ix.partialFilterExpression) opts.partialFilterExpression = ix.partialFilterExpression;
      if (ix.sparse) opts.sparse = true;
      if (!APPLY) { created.push(ix.name + " (dry-run)"); return; }
      try {
        dst[name].createIndex(ix.key, opts);
        created.push(ix.name);
      } catch (e) {
        var c = errCode(e);
        if (c === 85 || c === 86) { created.push(ix.name + " (equivalente ja existe)"); }
        else { errors.push(ix.name + ": " + (e.message || e.errmsg || c)); }
      }
    });
    return { created: created, errors: errors };
  }

  // --- 2) Garantir indice TTL GDPR (m002) no alvo + verificar cobertura real ---
  function ensureGdprTtl() {
    var out = [], warnings = [];
    GDPR_TTL.forEach(function (g) {
      var present = dst[g.coll].getIndexes().some(function (i) { return i.name === "created_at_ttl"; });
      if (!present) {
        if (!APPLY) { out.push(g.coll + ": criaria created_at_ttl (dry-run)"); }
        else {
          var keySpec = {}; keySpec[g.field] = 1;
          try {
            dst[g.coll].createIndex(keySpec, { name: "created_at_ttl", expireAfterSeconds: TWO_YEARS_SECONDS });
            out.push(g.coll + ": created_at_ttl criado (2 anos, campo " + g.field + ")");
          } catch (e) {
            out.push(g.coll + ": ERRO created_at_ttl: " + (e.message || errCode(e)));
          }
        }
      } else {
        out.push(g.coll + ": created_at_ttl ja existe");
      }
      // Cobertura real: o campo TTL existe como Date nos docs? Se nao, o indice
      // e inerte (nunca expira) -> aviso honesto, sem mascarar como sucesso.
      var total = dst[g.coll].countDocuments({});
      var withField = dst[g.coll].countDocuments((function () { var q = {}; q[g.field] = { $type: "date" }; return q; })());
      if (total > 0 && withField === 0) {
        warnings.push(g.coll + ": TTL em '" + g.field + "' INERTE — 0/" + total +
          " docs tem o campo como Date (quirk do m002; docs usam outro campo de timestamp). Indice criado mas nao expira.");
      }
    });
    return { results: out, warnings: warnings };
  }

  // --- 3) Migrar uma coleccao (insert-if-absent + de-dup logica) ---
  function migrateCollection(cfg) {
    var name = cfg.name, key = cfg.key;
    var srcCount = src[name].countDocuments({});
    var dstBefore = dst[name].countDocuments({});

    // Snapshot em memoria das chaves ja presentes no alvo (1 varredura).
    var existingKeys = new Set();
    var keyProj = {}; keyProj[key] = 1; if (key !== "_id") keyProj._id = 0;
    dst[name].find({}, keyProj).forEach(function (d) { existingKeys.add(ser(d[key])); });

    var existingLogical = null;
    if (cfg.logicalKey) {
      existingLogical = new Set();
      var lProj = { _id: 0 }; cfg.logicalKey.forEach(function (f) { lProj[f] = 1; });
      dst[name].find({}, lProj).forEach(function (d) { existingLogical.add(serLogical(d, cfg.logicalKey)); });
    }

    var skippedExisting = 0, skippedLogical = 0, candidates = 0;
    var inserted = 0, dupKeySkipped = 0, writeErrors = 0;
    var batch = [];

    function flush() {
      if (!batch.length) return;
      try {
        var res = dst[name].insertMany(batch, { ordered: false });
        inserted += (res && (res.insertedCount ||
          (res.insertedIds && Object.keys(res.insertedIds).length))) || 0;
      } catch (e) {
        // insertMany ordered:false: insere os nao-duplicados e lanca BulkWriteError.
        var r = e.result;
        if (r) {
          inserted += (typeof r.insertedCount !== "undefined") ? r.insertedCount
                    : (typeof r.nInserted !== "undefined") ? r.nInserted : 0;
        }
        var we = [];
        if (e.writeErrors && e.writeErrors.length) we = e.writeErrors;
        else if (r && typeof r.getWriteErrors === "function") we = r.getWriteErrors();
        else if (r && r.writeErrors) we = r.writeErrors;
        else if (typeof errCode(e) !== "undefined") we = [e];
        we.forEach(function (w) {
          if (errCode(w) === 11000) dupKeySkipped++; // benigno: corrida com o pipeline
          else writeErrors++;
        });
      }
      batch = [];
    }

    var cursor = src[name].find({});
    while (cursor.hasNext()) {
      var doc = cursor.next();
      var sk = ser(doc[key]);
      if (existingKeys.has(sk)) { skippedExisting++; continue; }
      if (cfg.logicalKey) {
        var lk = serLogical(doc, cfg.logicalKey);
        if (existingLogical.has(lk)) { skippedLogical++; continue; }
        existingLogical.add(lk); // evita duplicados logicos dentro do proprio lote
      }
      existingKeys.add(sk); // evita reprocessar a mesma chave na mesma execucao
      candidates++;
      if (APPLY) {
        batch.push(doc); // preserva _id de origem
        if (batch.length >= BATCH) flush();
      }
    }
    if (APPLY) flush();

    var dstAfter = dst[name].countDocuments({});

    // --- Completude da copia: toda a chave de origem presente no alvo? ---
    var missing = 0;
    var sampled = 0, sampleNotCopied = 0, contentMismatches = 0;
    if (APPLY) {
      var dstKeys = new Set();
      dst[name].find({}, keyProj).forEach(function (d) { dstKeys.add(ser(d[key])); });
      var dstLogical = null;
      if (cfg.logicalKey) {
        dstLogical = new Set();
        var lp = { _id: 0 }; cfg.logicalKey.forEach(function (f) { lp[f] = 1; });
        dst[name].find({}, lp).forEach(function (d) { dstLogical.add(serLogical(d, cfg.logicalKey)); });
      }
      var c2 = src[name].find({});
      while (c2.hasNext()) {
        var sdoc = c2.next();
        if (dstKeys.has(ser(sdoc[key]))) continue;
        if (cfg.logicalKey && dstLogical.has(serLogical(sdoc, cfg.logicalKey))) continue;
        missing++;
      }

      // --- Amostragem de integridade de conteudo (DoD 2.4) ---
      // Compara o payload integral de ate SAMPLE_N docs de origem que foram
      // copiados (mesmo _id presente no alvo). Docs saltados por de-dup logica
      // (mesmo conteudo logico sob outro _id) nao sao copia nossa -> nao contam.
      var sampleDocs = src[name].find({}).limit(SAMPLE_N).toArray();
      sampleDocs.forEach(function (sdoc) {
        var t = dst[name].findOne({ _id: sdoc._id });
        if (!t) { sampleNotCopied++; return; }
        sampled++;
        if (canon(sdoc) !== canon(t)) contentMismatches++;
      });
    }

    return {
      collection: name,
      key: key,
      logicalKey: cfg.logicalKey || null,
      src_count: srcCount,
      dst_before: dstBefore,
      candidates: candidates,
      skipped_existing_key: skippedExisting,
      skipped_logical_dup: skippedLogical,
      inserted: inserted,
      dup_key_skipped: dupKeySkipped,
      write_errors: writeErrors,
      dst_after: dstAfter,
      missing_after: APPLY ? missing : "(dry-run)",
      sampled_compared: APPLY ? sampled : "(dry-run)",
      sample_not_copied: APPLY ? sampleNotCopied : "(dry-run)",
      content_mismatches: APPLY ? contentMismatches : "(dry-run)",
      copy_complete: APPLY ? (missing === 0 && contentMismatches === 0) : "(dry-run)",
    };
  }

  // ---- Execucao ----
  print("=== Fase 1 — migracao corpus " + SRC_DB + " -> " + DST_DB +
        " (APPLY=" + APPLY + ") ===");

  var indexReport = {}, results = [];

  COLLECTIONS.forEach(function (cfg) {
    indexReport[cfg.name] = recreateIndexes(cfg.name);
  });
  var ttl = ensureGdprTtl();

  COLLECTIONS.forEach(function (cfg) {
    results.push(migrateCollection(cfg));
  });

  var indexErrors = 0;
  Object.keys(indexReport).forEach(function (k) { indexErrors += indexReport[k].errors.length; });
  var anyMissing = results.some(function (r) { return r.copy_complete === false; });
  var anyWriteErr = results.some(function (r) { return r.write_errors > 0; });
  var anyContentMismatch = results.some(function (r) { return r.content_mismatches > 0; });

  print("\n--- indices recriados ---");
  print(JSON.stringify(indexReport, null, 2));
  print("\n--- TTL GDPR (m002) ---");
  print(JSON.stringify(ttl.results, null, 2));
  if (ttl.warnings.length) {
    print("\n--- AVISOS TTL (quirk m002, nao-fatal) ---");
    ttl.warnings.forEach(function (w) { print("  ! " + w); });
  }

  var summary = {
    apply: APPLY,
    src_db: SRC_DB,
    dst_db: DST_DB,
    index_errors: indexErrors,
    write_errors_total: results.reduce(function (a, r) { return a + r.write_errors; }, 0),
    dup_key_skipped_total: results.reduce(function (a, r) { return a + r.dup_key_skipped; }, 0),
    ttl_warnings: ttl.warnings,
    all_copies_complete: APPLY ? !anyMissing && !anyContentMismatch : "(dry-run)",
    collections: results,
  };

  print("\n=== MIGRATION RESULT (JSON) ===");
  print(JSON.stringify(summary, null, 2));
  print("=== END MIGRATION RESULT ===");

  // Veredicto fail-fast: em modo APPLY, qualquer copia incompleta, mismatch de
  // conteudo, erro de escrita (nao-11000) ou erro de indice e falha honesta.
  // DuplicateKey (11000) e conflitos de indice equivalente (85/86) sao benignos.
  if (APPLY && (anyMissing || anyWriteErr || anyContentMismatch || indexErrors > 0)) {
    print("MIGRATION_VERDICT=FAIL");
  } else {
    print("MIGRATION_VERDICT=OK");
  }
})();
