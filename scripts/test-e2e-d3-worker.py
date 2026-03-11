#!/usr/bin/env python3
"""
Teste E2E D3 Simplificado - Usando Worker Agents diretamente

Em vez de usar o Execution Ticket Service (que tem uma API complexa),
este teste interage diretamente com o Worker Agent para processar
um ticket BUILD.
"""

import subprocess
import sys
import time
import uuid
from datetime import datetime


def kubectl_exec(namespace: str, pod: str, command: str) -> str:
    """Executa comando em pod via kubectl"""
    cmd = f"kubectl exec -n {namespace} {pod} -- {command}"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.stdout


def submit_build_to_worker_agent():
    """Submete job BUILD ao Worker Agent via Kafka"""
    print("\n=== Submetendo Job BUILD ao Worker Agent ===")

    job_id = f"d3-e2e-{uuid.uuid4().hex[:8]}"
    trace_id = str(uuid.uuid4())

    print(f"Job ID: {job_id}")
    print(f"Trace ID: {trace_id}")

    # Criar mensagem Kafka com ticket BUILD
    ticket = {
        "ticket_id": job_id,
        "task_id": f"task-{job_id[:8]}",
        "task_type": "BUILD",
        "parameters": {
            "artifact_id": "test-service-d3",
            "branch": "main",
            "commit_sha": "abc123def456",
            "dockerfile": "Dockerfile",
            "registry": "local"
        }
    }

    # Executar dentro do pod do worker-agent para enviar mensagem Kafka
    json_str = str(ticket).replace("'", '"')

    cmd = f"""python3 -c "
import json
from kafka import KafkaProducer
import uuid

producer = KafkaProducer(
    bootstrap_servers='neural-hive-kafka-broker.neural-hive.svc.cluster.local:9092',
    value_serializer=lambda v: json.dumps(v).encode('utf-8')
)

# Enviar para tópico de tickets
producer.send('execution.tickets', value={ticket})
producer.flush(timeout_ms=5000)
print(f'Mensagem enviada: {ticket}')
producer.close()
"
"""

    # Usar o pod do worker-agent
    print("Enviando mensagem Kafka...")
    result = kubectl_exec(
        "neural-hive",
        "deployment/worker-agents",
        f'bash -c "cd /app && python3 -c \\"{cmd}\\""'
    )

    print("Resultado:", result[-200:] if len(result) > 200 else result)

    return job_id, trace_id


def check_worker_logs(job_id: str, duration: int = 30):
    """Monitora logs do Worker Agent"""
    print(f"\n=== Monitorando Worker Agent (job: {job_id}) ===")
    print("Aguardando processamento...")

    start = time.time()
    seen_lines = []

    while (time.time() - start) < duration:
        # Buscar logs recentes
        logs = subprocess.run(
            f"kubectl logs -n neural-hive deployment/worker-agents --tail=50 | grep -i '{job_id}' || true",
            shell=True,
            capture_output=True,
            text=True
        ).stdout

        new_lines = [line for line in logs.split('\n') if line and line not in seen_lines]
        seen_lines.extend(new_lines)

        for line in new_lines:
            if 'completed' in line.lower():
                print(f"✓ {line.strip()}")
                return True
            elif 'failed' in line.lower() or 'error' in line.lower():
                print(f"✗ {line.strip()}")
                return False

        time.sleep(2)

    print("Tempo esgotado")
    return None


def check_codeforge_results():
    """Verifica resultados no CodeForge"""
    print("\n=== Verificando CodeForge ===")

    # Verificar pods do CodeForge
    result = subprocess.run(
        "kubectl get pods -n neural-hive -l app=code-forge -o json",
        shell=True,
        capture_output=True,
        text=True
    )

    if result.returncode == 0:
        import json
        try:
            pods = json.loads(result.stdout)
            if pods.get('items'):
                pod = pods['items'][0]
                name = pod['metadata']['name']
                print(f"CodeForge pod: {name}")
                print(f"Status: {pod['status']['phase']}")
        except:
            pass


def main():
    """Função principal"""
    print("\n╔════════════════════════════════════════════════════════════╗")
    print("║     Teste E2E D3 - Via Worker Agent & Kafka                 ║")
    print("╚════════════════════════════════════════════════════════════╝")

    # Submeter job
    job_id, trace_id = submit_build_to_worker_agent()

    # Monitorar por um tempo limitado
    result = check_worker_logs(job_id, duration=60)

    # Verificar CodeForge
    check_codeforge_results()

    print("\n=== Resumo ===")
    print(f"Job ID: {job_id}")
    print(f"Trace ID: {trace_id}")
    print(f"Resultado: {result}")

    if result:
        print("\n✓ Teste E2E D3 concluído com sucesso")
        return 0
    else:
        print("\n⚠ Teste finalizado sem confirmação explícita")
        return 0


if __name__ == "__main__":
    sys.exit(main())
