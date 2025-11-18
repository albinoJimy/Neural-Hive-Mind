#!/usr/bin/env python3
"""
Test specialist-business metadata fix.
Publica mensagem no Kafka e monitora logs do specialist-business.
"""

import json
import time
import subprocess
from datetime import datetime
from kafka import KafkaProducer

def publish_test_message():
    """Publica mensagem de teste no tópico planos-cognitivos."""

    producer = KafkaProducer(
        bootstrap_servers=['localhost:30092'],
        value_serializer=lambda v: json.dumps(v).encode('utf-8'),
        key_serializer=lambda k: k.encode('utf-8') if k else None,
        acks='all',
        retries=3
    )

    message = {
        "plan_id": "test-metadata-fix-001",
        "version": "1.0.0",
        "intent_id": "test-intent-metadata-fix",
        "correlation_id": "corr-metadata-fix-001",
        "trace_id": "trace-metadata-fix-001",
        "span_id": "span-metadata-fix-001",
        "tasks": [
            {
                "task_id": "task-1",
                "task_type": "data_analysis",
                "description": "Analyze business metrics",
                "dependencies": [],
                "estimated_duration_ms": 5000,
                "required_capabilities": ["analytics"],
                "parameters": {"metric": "revenue"},
                "metadata": {"priority": "high"}
            }
        ],
        "execution_order": ["task-1"],
        "risk_score": 0.25,
        "risk_band": "low",
        "risk_factors": {"complexity": 0.2, "impact": 0.3},
        "explainability_token": "exp-metadata-fix-001",
        "reasoning_summary": "Simple business analysis task",
        "status": "draft",
        "created_at": int(time.time() * 1000),
        "valid_until": None,
        "estimated_total_duration_ms": 5000,
        "complexity_score": 0.3,
        "original_domain": "business",
        "original_priority": "high",
        "original_security_level": "standard",
        "metadata": {
            "test": "metadata-fix",
            "timestamp": datetime.now().isoformat()
        },
        "schema_version": 1
    }

    print(f"[{datetime.now().isoformat()}] Publicando mensagem test-metadata-fix-001...")

    future = producer.send(
        topic='planos-cognitivos',
        key='test-metadata-fix-001',
        value=message
    )

    result = future.get(timeout=10)
    print(f"[{datetime.now().isoformat()}] Mensagem publicada: offset={result.offset}")

    producer.flush()
    producer.close()

    return message

def monitor_specialist_logs(duration=30):
    """Monitora logs do specialist-business por N segundos."""

    print(f"\n[{datetime.now().isoformat()}] Monitorando logs por {duration}s...")
    print("=" * 80)

    cmd = [
        "kubectl", "logs",
        "-f", "-l", "app.kubernetes.io/name=specialist-business",
        "-n", "specialist-business",
        "--tail=20"
    ]

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    start_time = time.time()

    try:
        while time.time() - start_time < duration:
            line = process.stdout.readline()
            if not line:
                break

            # Destacar linhas relevantes
            line = line.rstrip()
            if any(keyword in line.lower() for keyword in ['test-metadata-fix', 'error', 'exception', 'metadata', 'evaluated plan']):
                print(f">>> {line}")
            else:
                print(line)

    except KeyboardInterrupt:
        print("\n[!] Monitoramento interrompido")
    finally:
        process.terminate()
        process.wait()

    print("=" * 80)

def check_consensus_engine_logs():
    """Verifica logs do consensus-engine."""

    print(f"\n[{datetime.now().isoformat()}] Verificando logs do consensus-engine...")
    print("=" * 80)

    cmd = [
        "kubectl", "logs",
        "-l", "app=consensus-engine",
        "-n", "consensus-engine",
        "--tail=30"
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    for line in result.stdout.split('\n'):
        if any(keyword in line.lower() for keyword in ['test-metadata-fix', 'specialist-business', 'error', 'success']):
            print(f">>> {line}")
        elif line.strip():
            print(line)

    print("=" * 80)

if __name__ == '__main__':
    print("=" * 80)
    print("TESTE: specialist-business metadata fix")
    print("=" * 80)

    # Publicar mensagem
    message = publish_test_message()

    # Aguardar processamento
    print(f"\n[{datetime.now().isoformat()}] Aguardando 3s para processamento...")
    time.sleep(3)

    # Monitorar logs specialist-business
    monitor_specialist_logs(duration=25)

    # Verificar logs consensus-engine
    check_consensus_engine_logs()

    print(f"\n[{datetime.now().isoformat()}] Teste concluído!")
    print("\nVerifique se specialist-business processou sem TypeError de metadata.")
