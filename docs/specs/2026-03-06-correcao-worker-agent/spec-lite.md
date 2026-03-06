# Spec Summary (Lite)

Corrigir dois bugs críticos do Worker Agent: (1) ExecutionEngine sempre marca COMPLETED mesmo quando executors retornam success=False, e (2) mismatch de parâmetros entre STE (gera {subject, target, entities}) e Executors (esperam {collection, input_data, policy_path}).

Objetivo: Garantir que tickets falhos sejam marcados como FAILED e que executores recebam parâmetros corretos para execução bem-sucedida.
