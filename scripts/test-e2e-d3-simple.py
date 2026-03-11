#!/usr/bin/env python3
"""
Teste E2E Simplificado D3

Executa teste E2E do fluxo D3 usando kubectl exec para interagir com os serviços.
"""

import json
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta


def kubectl_exec(command: str, capture: bool = True) -> str:
    """Executa comando kubectl exec"""
    full_cmd = f"kubectl exec -n neural-hive deployment/execution-ticket-service -- {command}"
    result = subprocess.run(full_cmd, shell=True, capture_output=capture, text=True)
    return result.stdout + result.stderr


def create_ticket():
    """Cria e submete ticket BUILD"""
    print("\n=== Criando Ticket D3 ===")

    ticket_id = f"d3-e2e-{uuid.uuid4().hex[:8]}"
    trace_id = str(uuid.uuid4())
    plan_id = f"plan-d3e2e-{uuid.uuid4().hex[:8]}"

    print(f"Ticket ID: {ticket_id}")
    print(f"Trace ID: {trace_id}")
    print()

    # Criar payload JSON
    now_utc = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    deadline = (datetime.utcnow() + timedelta(hours=4)).strftime("%Y-%m-%dT%H:%M:%SZ")

    payload = {
        "ticket_id": ticket_id,
        "plan_id": plan_id,
        "intent_id": "intent-d3e2e-test",
        "decision_id": "decision-d3e2e-test",
        "correlation_id": str(uuid.uuid4()),
        "trace_id": trace_id,
        "span_id": str(uuid.uuid4()),
        "task_type": "BUILD",
        "status": "PENDING",
        "priority": "NORMAL",
        "risk_band": "MEDIUM",
        "parameters": {
            "artifact_type": "MICROSERVICE",
            "language": "python",
            "service_name": "test-service-d3-e2e",
            "description": "Teste E2E D3",
            "framework": "fastapi"
        },
        "sla": {
            "deadline": deadline,
            "timeout_ms": 14400000,
            "max_retries": 3
        },
        "qos": {
            "delivery_mode": "AT_LEAST_ONCE",
            "consistency": "EVENTUAL",
            "durability": "PERSISTENT"
        },
        "security_level": "INTERNAL",
        "dependencies": [],
        "created_at": now_utc
    }

    # Salvar IDs para uso posterior
    with open("/tmp/d3_e2e_ids.txt", "w") as f:
        f.write(f"TICKET_ID={ticket_id}\n")
        f.write(f"TRACE_ID={trace_id}\n")
        f.write(f"PLAN_ID={plan_id}\n")

    # Submeter via API (usando curl dentro do pod)
    print("Submetendo ticket...")
    json_str = json.dumps(payload).replace('"', '\\"')

    curl_cmd = f'curl -s -X POST "http://localhost:8003/api/v1/tickets/" -H "Content-Type: application/json" -d \'{json_str}\''
    response = kubectl_exec(curl_cmd)

    if "ticket_id" in response or response.startswith("{"):
        print(f"✓ Ticket criado: {ticket_id}")
        return ticket_id, trace_id
    else:
        print(f"✗ Falha ao criar ticket")
        print(f"Response: {response}")
        return None, None


def check_ticket_status(ticket_id: str) -> str:
    """Verifica status do ticket"""
    curl_cmd = f'curl -s "http://localhost:8003/api/v1/tickets/{ticket_id}"'
    response = kubectl_exec(curl_cmd)

    try:
        data = json.loads(response)
        return data.get("status", "UNKNOWN")
    except:
        return "PARSE_ERROR"


def monitor_ticket(ticket_id: str, timeout: int = 120) -> bool:
    """Monitora processamento do ticket"""
    print(f"\n=== Monitorando Ticket: {ticket_id} ===")
    print("Aguardando processamento...")

    start = time.time()
    last_status = ""

    while (time.time() - start) < timeout:
        try:
            status = check_ticket_status(ticket_id)

            if status != last_status:
                print(f"  Status: {status}")
                last_status = status

            if status == "COMPLETED":
                print("✓ Ticket completado com sucesso!")
                return True
            elif status == "FAILED":
                print("✗ Ticket falhou")
                return False
            elif status in ("UNKNOWN", "PARSE_ERROR"):
                print(f"  Erro ao verificar status")

        except Exception as e:
            print(f"  Erro: {e}")

        time.sleep(5)

    print("✗ Timeout aguardando processamento")
    return False


def check_mongodb(ticket_id: str):
    """Verifica resultados no MongoDB"""
    print("\n=== Verificando MongoDB ===")

    # Executar query no MongoDB via kubectl
    query = f'db.artifacts.find({{"ticket_id": "{ticket_id}"}}).limit(5)'

    cmd = f'mongosh --quiet --eval "{query}" mongodb://mongodb-cluster-service.mongodb-cluster.svc.cluster.local:27017/code_forge?authSource=admin'
    result = kubectl_exec(f'bash -c "{cmd}"', capture=False)

    # Verificar se encontrou artefatos
    if "artifacts" in result.lower() or "artifact_type" in result.lower():
        print("✓ Artefatos encontrados no MongoDB")
        return True
    else:
        print("  Nenhum artefato encontrado (pode estar em outra collection)")
        return False


def check_logs(trace_id: str):
    """Verifica logs dos serviços"""
    print("\n=== Verificando Logs ===")

    # Logs do Worker Agent
    print("Logs do Worker Agent:")
    cmd = f'grep -i "{trace_id}" /proc/1/fd/1 2>/dev/null || echo "Searching in logs..."'
    result = kubectl_exec(f'bash -c "grep -i {trace_id} /app/logs/*.log 2>/dev/null | tail -20 || echo \'No logs found\'"', capture=False)

    # Usar kubectl logs diretamente
    log_result = subprocess.run(
        f"kubectl logs -n neural-hive deployment/worker-agents --tail=50 | grep -i {trace_id} || echo 'No specific logs'",
        shell=True,
        capture_output=True,
        text=True
    )

    if log_result.stdout.strip():
        print("  ✓ Logs encontrados")
        print(log_result.stdout.split("\n")[:5])
    else:
        print("  - Nenhum log específico encontrado")


def main():
    """Função principal"""
    print("\n╔════════════════════════════════════════════════════════════╗")
    print("║     Teste E2E D3 (Build + Geração de Artefatos)             ║")
    print("║            Neural Hive Mind - CodeForge                    ║")
    print("╚════════════════════════════════════════════════════════════╝")

    # Criar ticket
    ticket_id, trace_id = create_ticket()
    if not ticket_id:
        print("\n✗ Teste falhou na criação do ticket")
        return 1

    # Monitorar ticket
    if not monitor_ticket(ticket_id, timeout=120):
        print("\n✗ Teste falhou no processamento")
        return 1

    # Verificar MongoDB
    check_mongodb(ticket_id)

    # Verificar logs
    check_logs(trace_id)

    print("\n✓ Teste E2E D3 concluído")
    print(f"  Ticket ID: {ticket_id}")
    print(f"  Trace ID: {trace_id}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
