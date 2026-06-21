# Spec Summary (Lite)

Elevar o "caminho real" (execução real, ML, NER, OPA) a primeira classe e tornar todos os fallbacks/heurísticas/simulações de lacuna falhas observáveis, eliminando o "verde falso" — `COMPLETED`/`healthy`/`allow` reportados sem trabalho real. Cada degradação emite métrica e marca o resultado; em produção o caminho real indisponível falha (fail-fast) em vez de degradar silenciosamente. Reativa caminhos reais críticos (Fluxo G, deploy/build fail-closed, modelo ML não-descartado, consenso honesto, subject/entities via NER).
