# Spec Summary (Lite)

Extrair GENERATE como capacidade autónoma por **fronteira de contrato** (passo 3 do ADR-0011,
desbloqueado pelo gate "J3/BUILD fiável"). Cria `GenerateRequest → GenerateResult` explícito e
fail-closed, com o `FluxoGWorkflow` (Temporal) a manter-se como implementação por trás da fronteira
(preserva durabilidade e fiabilidade J3/BUILD). O `decision_consumer` passa a invocar a capacidade
em vez de conhecer a classe do workflow. O contrato e a seleção de template/builder ficam
**stack-neutros (multi-linguagem-ready)**: só Python FastAPI é implementado/provado, mas adicionar
uma linguagem depois é registar nova estratégia atrás da mesma fronteira — stack desconhecida falha
fechado (nunca cai silenciosamente para FastAPI). Gate: paridade E2E J3 (Deployment 1/1 + /health
200 via a capacidade) + teste de contrato em bloco.
