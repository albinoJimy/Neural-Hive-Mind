"""
Smoke Tests E2E - Neural Hive-Mind.

Smoke tests validam rapidamente (<10min) que os serviços core estão operacionais.
Foco: health checks, readiness probes, conectividade básica.

Para executar:
    ./tests/e2e/smoke/run_smoke_tests.sh

Ou com pytest diretamente:
    pytest tests/e2e/smoke/ -m smoke

Variáveis de ambiente:
    GATEWAY_URL      URL do Gateway (default: detecta K8s ou localhost:8000)
    STE_URL          URL do STE (default: detecta K8s ou localhost:8001)
    CONSENSUS_URL    URL do Consensus (default: detecta K8s ou localhost:8002)
"""
