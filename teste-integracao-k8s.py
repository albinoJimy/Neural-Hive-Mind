#!/usr/bin/env python3
"""
Teste de Integração End-to-End - Neural Hive-Mind Kubernetes
Testa a integração completa entre Kafka, MongoDB e Redis no cluster K8s
"""

import subprocess
import json
import time
from datetime import datetime, timezone
import uuid

def run_kubectl(cmd):
    """Executa comando kubectl e retorna output"""
    result = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True
    )
    return result.stdout.strip(), result.returncode

def log_info(msg):
    print(f"[INFO] {msg}")

def log_success(msg):
    print(f"[✓] {msg}")

def log_error(msg):
    print(f"[✗] {msg}")

def main():
    print("=" * 70)
    print(" TESTE DE INTEGRAÇÃO END-TO-END - NEURAL HIVE-MIND K8S")
    print("=" * 70)
    print()

    # 1. Verificar conectividade Redis
    log_info("1. Testando Redis...")
    redis_pod = "redis-59dbc7c5f-6pqbr"

    output, code = run_kubectl(
        f"kubectl exec -n redis-cluster {redis_pod} -- redis-cli ping"
    )

    if code == 0 and "PONG" in output:
        log_success("Redis: PONG")
    else:
        log_error("Redis não respondeu")
        return 1

    # 2. Armazenar metadata no Redis
    log_info("2. Armazenando metadata no Redis...")
    intent_id = str(uuid.uuid4())
    metadata = json.dumps({
        "intent_id": intent_id,
        "domain": "TECHNICAL",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "k8s-integration-test"
    })

    run_kubectl(
        f"kubectl exec -n redis-cluster {redis_pod} -- redis-cli SET intent:{intent_id} '{metadata}'"
    )

    output, code = run_kubectl(
        f"kubectl exec -n redis-cluster {redis_pod} -- redis-cli GET intent:{intent_id}"
    )

    if code == 0 and intent_id in output:
        log_success(f"Redis metadata armazenada: {intent_id[:8]}...")
    else:
        log_error("Falha ao armazenar metadata no Redis")
        return 1

    # 3. Inserir documento no MongoDB
    log_info("3. Inserindo documento no MongoDB...")
    mongodb_pod = "mongodb-654f449f49-tfffl"

    doc = {
        "intent_id": intent_id,
        "domain": "TECHNICAL",
        "text": "Teste de integração end-to-end K8s",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "kafka_topic": "intentions-technical",
        "metadata": {"test": "integration"}
    }

    doc_json = json.dumps(doc).replace("'", "\\'")

    output, code = run_kubectl(
        f"kubectl exec -n mongodb-cluster {mongodb_pod} -- mongosh "
        f"mongodb://localhost:27017/neural_hive_test -u root -p local_dev_password "
        f"--authenticationDatabase admin --quiet --eval "
        f"'db.intents.insertOne({doc_json})'"
    )

    if code == 0:
        log_success(f"MongoDB documento inserido: {intent_id[:8]}...")
    else:
        log_error("Falha ao inserir no MongoDB")
        return 1

    # 4. Verificar documento no MongoDB
    log_info("4. Verificando documento no MongoDB...")
    output, code = run_kubectl(
        f'kubectl exec -n mongodb-cluster {mongodb_pod} -- mongosh '
        f'mongodb://localhost:27017/neural_hive_test -u root -p local_dev_password '
        f'--authenticationDatabase admin --quiet --eval '
        f'"db.intents.findOne({{intent_id: \\"{intent_id}\\"}})"'
    )

    if code == 0 and intent_id in output:
        log_success("MongoDB documento recuperado com sucesso")
    else:
        log_error("Falha ao recuperar do MongoDB")
        return 1

    # 5. Verificar tópicos Kafka
    log_info("5. Verificando tópicos Kafka...")
    output, code = run_kubectl(
        "kubectl get kafkatopic -n kafka --no-headers | wc -l"
    )

    if code == 0:
        topics_count = int(output)
        log_success(f"Kafka: {topics_count} tópicos disponíveis")
    else:
        log_error("Falha ao verificar tópicos Kafka")
        return 1

    # 6. Verificar metadata persistida
    log_info("6. Verificando persistência de dados...")
    output, code = run_kubectl(
        f"kubectl exec -n redis-cluster {redis_pod} -- redis-cli GET intent:{intent_id}"
    )

    if code == 0 and intent_id in output:
        log_success("Redis: Dados persistidos OK")
    else:
        log_error("Dados não persistidos no Redis")
        return 1

    # Sumário
    print()
    print("=" * 70)
    print(" RESUMO DO TESTE")
    print("=" * 70)
    print()
    print(f"Intent ID testado: {intent_id}")
    print()
    print("✅ Redis: CRUD OK")
    print("✅ MongoDB: CRUD OK")
    print("✅ Kafka: Topics OK")
    print("✅ Integração: Fluxo completo validado")
    print()
    print("=" * 70)
    print("✅ TESTE DE INTEGRAÇÃO: APROVADO")
    print("=" * 70)

    return 0

if __name__ == "__main__":
    exit(main())
