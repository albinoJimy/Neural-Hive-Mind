"""
Testes End-to-End (E2E) para Neural Hive-Mind

Este pacote contém testes E2E que validam:
1. Fluxo completo intention → code
2. Propagação de correlation_id em todos os serviços
3. Distributed tracing (W3C traceparent)
4. Compensação Saga em cenários de falha
5. Comportamento sob carga/stress

Execução:
    pytest tests/e2e/ -v --asyncio-mode=auto

Testes individuais:
    pytest tests/e2e/test_full_intent_to_code.py -v
    pytest tests/e2e/test_load_correlation_id.py -v
    pytest tests/e2e/test_workflow_compensation.py -v

Com markers:
    pytest tests/e2e/ -v -m e2e
    pytest tests/e2e/ -v -m stress
    pytest tests/e2e/ -v -m saga
"""
