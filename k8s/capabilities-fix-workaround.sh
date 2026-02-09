#!/bin/bash
# Workaround para capabilities mismatch entre workers e orchestrator
# Aplicar quando pods do orchestrator restartarem

ORCHESTRATOR_POD=$(kubectl get pods -n neural-hive -l app=orchestrator-dynamic -o jsonpath='{.items[0].metadata.name}')

echo "Aplicando fix de capabilities no pod: $ORCHESTRATOR_POD"

# O fix está no código main (commit 6f1ee62)
# Quando o CI/CD buildar a nova imagem, o fix será aplicado automaticamente
# Por enquanto, este é um workaround manual

kubectl exec -n neural-hive $ORCHESTRATOR_POD -- python -c "
import sys
sys.path.insert(0, '/home/orchestrator/.local/lib/python3.11/site-packages')

# Verificar se o fix já está aplicado
from neural_hive_integration.orchestration.flow_c_orchestrator import FlowCOrchestrator
import inspect

source = inspect.getsource(FlowCOrchestrator._extract_tickets_from_plan)
if 'task.get(\"required_capabilities\"' in source:
    print('✓ Fix já está aplicado no código')
else:
    print('✗ Fix não aplicado - aguardando nova imagem do CI/CD')
"

echo ""
echo "Status do fix:"
echo "- Código corrigido no repo: commit 6f1ee62"
echo "- Aguardando build do CI/CD para deploy automático"
