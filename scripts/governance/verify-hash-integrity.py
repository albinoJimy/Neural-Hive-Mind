#!/usr/bin/env python3

"""
Script: verify-hash-integrity.py
Descrição: Script Python para recálculo e verificação de hashes SHA-256 do ledger cognitivo
Autor: Neural Hive-Mind Team
Data: 2025-11-12
Versão: 1.0.0

Referências:
- services/consensus-engine/src/models/consolidated_decision.py (calculate_hash linhas 95-108)
"""

import sys
import json
import hashlib
import argparse
from datetime import datetime
from typing import Dict, Any, List, Optional

try:
    from pymongo import MongoClient
except ImportError:
    print("ERROR: pymongo não instalado. Execute: pip install pymongo", file=sys.stderr)
    sys.exit(1)


def calculate_decision_hash(decision_doc: Dict[str, Any]) -> str:
    """
    Recalcula hash de uma decisão usando o mesmo algoritmo do ConsolidatedDecision.

    Referência: services/consensus-engine/src/models/consolidated_decision.py linhas 95-108
    """
    # Extrair campos relevantes para o hash
    data = {
        "decision_id": decision_doc.get("decision_id", ""),
        "plan_id": decision_doc.get("plan_id", ""),
        "final_decision": decision_doc.get("final_decision", ""),
        "aggregated_confidence": decision_doc.get("aggregated_confidence", 0.0),
        "aggregated_risk": decision_doc.get("aggregated_risk", 0.0),
        "specialist_votes": decision_doc.get("specialist_votes", []),
        "created_at": decision_doc.get("created_at", ""),
    }

    # Converter created_at para ISO format se for datetime
    if isinstance(data["created_at"], datetime):
        data["created_at"] = data["created_at"].isoformat()

    # Serializar com sort_keys=True para garantir ordem consistente
    json_str = json.dumps(data, sort_keys=True, ensure_ascii=False)

    # Calcular hash SHA-256
    hash_value = hashlib.sha256(json_str.encode("utf-8")).hexdigest()

    return hash_value


def verify_collection(
    mongo_uri: str, database: str, collection: str, sample_size: int
) -> Dict[str, Any]:
    """
    Verifica integridade de hashes em uma collection MongoDB.
    """
    try:
        # Conectar ao MongoDB
        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)

        # Verificar conexão
        client.admin.command("ping")

        # Selecionar database e collection
        db = client[database]
        coll = db[collection]

        # Buscar registros com hash
        cursor = coll.find({"hash": {"$exists": True, "$ne": ""}}).limit(sample_size)

        results = []
        valid_count = 0
        invalid_count = 0

        for doc in cursor:
            stored_hash = doc.get("hash", "")

            # Remover campo hash do documento para recálculo
            doc_copy = doc.copy()
            if "hash" in doc_copy:
                del doc_copy["hash"]
            if "_id" in doc_copy:
                del doc_copy["_id"]

            # Recalcular hash
            calculated_hash = calculate_decision_hash(doc_copy)

            # Comparar hashes
            is_valid = calculated_hash == stored_hash

            if is_valid:
                valid_count += 1
            else:
                invalid_count += 1

            results.append(
                {
                    "decision_id": doc.get("decision_id", "unknown"),
                    "stored_hash": stored_hash,
                    "calculated_hash": calculated_hash,
                    "valid": is_valid,
                }
            )

        # Fechar conexão
        client.close()

        return {
            "total": len(results),
            "valid": valid_count,
            "invalid": invalid_count,
            "results": results,
        }

    except Exception as e:
        return {"error": str(e), "total": 0, "valid": 0, "invalid": 0, "results": []}


def main():
    """
    Main execution.
    """
    parser = argparse.ArgumentParser(
        description="Verificar integridade de hashes SHA-256 no ledger cognitivo"
    )
    parser.add_argument(
        "--mongo-uri",
        required=True,
        help="MongoDB URI (ex: mongodb://user:pass@host:port/db?authSource=admin)",
    )
    parser.add_argument(
        "--database", required=True, help="Nome do database (ex: neural_hive)"
    )
    parser.add_argument(
        "--collection",
        required=True,
        help="Nome da collection (ex: consensus_decisions)",
    )
    parser.add_argument(
        "--sample-size", type=int, default=10, help="Tamanho da amostra (default: 10)"
    )

    args = parser.parse_args()

    # Executar verificação
    result = verify_collection(
        args.mongo_uri, args.database, args.collection, args.sample_size
    )

    # Imprimir resultado em JSON
    print(json.dumps(result, indent=2, ensure_ascii=False))

    # Exit code
    if result.get("invalid", 0) > 0:
        sys.exit(1)  # Falha se houver hashes inválidos
    elif result.get("error"):
        sys.exit(2)  # Erro na execução
    else:
        sys.exit(0)  # Sucesso


if __name__ == "__main__":
    main()
