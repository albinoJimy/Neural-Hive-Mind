#!/usr/bin/env python3
"""
Script para criar reference data inicial para Drift Detection.

Este script:
1. Extrai features de tickets históricos do MongoDB
2. Calcula estatísticas baselines para cada feature
3. Salva o baseline na coleção ml_feature_baselines

Uso:
    python ml_pipelines/training/create_reference_data.py [--samples N]

FASE 0 - IA/ML Integration (TICKET 2.3)
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import numpy as np
from pymongo import MongoClient


def extract_features_from_ticket(ticket: dict) -> dict:
    """
    Extrai features de um ticket para baseline.

    Features do modelo approval v7:
    - complexity: complexidade do ticket (1-5)
    - has_backup: tem backup? (0/1)
    - has_verification: tem verificação? (0/1)
    - has_all: campos todos preenchidos? (0/1)
    - priority: prioridade (1-5)
    - estimated_hours: horas estimadas
    - actual_hours: horas reais (se disponível)
    """
    try:
        # Campos básicos
        priority_map = {"low": 1, "medium": 2, "high": 3, "critical": 4, "urgent": 5}

        features = {
            "complexity": float(ticket.get("complexity", 3)),
            "has_backup": float(int(ticket.get("has_backup", False))),
            "has_verification": float(int(ticket.get("has_verification", False))),
            "has_all": float(int(ticket.get("has_all", False))),
            "priority": float(priority_map.get(ticket.get("priority", "medium"), 2)),
            "estimated_hours": float(ticket.get("estimated_hours", 8.0)),
        }

        # Actual hours se disponível
        if "actual_hours" in ticket and ticket["actual_hours"] is not None:
            features["actual_hours"] = float(ticket["actual_hours"])
        else:
            features["actual_hours"] = features["estimated_hours"]

        return features

    except Exception as e:
        print(f"Error extracting features from ticket {ticket.get('_id')}: {e}")
        return None


def create_baseline_from_tickets(tickets: list, model_version: str = "v7") -> dict:
    """
    Cria baseline de features a partir de tickets.

    Args:
        tickets: Lista de tickets do MongoDB
        model_version: Versão do modelo

    Returns:
        Dict com baseline para salvar no MongoDB
    """
    # Extrair features de todos os tickets
    all_features = []
    for ticket in tickets:
        features = extract_features_from_ticket(ticket)
        if features:
            all_features.append(features)

    if not all_features:
        raise ValueError("No valid features extracted from tickets")

    print(f"Extracted features from {len(all_features)} tickets")

    # Criar baseline para cada feature
    baseline_features = {}

    for feature_name in all_features[0].keys():
        values = [f[feature_name] for f in all_features if feature_name in f]

        if not values:
            continue

        values_array = np.array(values)

        baseline_features[feature_name] = {
            "values": values,
            "count": len(values),
            "mean": float(np.mean(values_array)),
            "std": float(np.std(values_array)),
            "min": float(np.min(values_array)),
            "max": float(np.max(values_array)),
            "percentiles": {
                "p25": float(np.percentile(values_array, 25)),
                "p50": float(np.percentile(values_array, 50)),
                "p75": float(np.percentile(values_array, 75)),
                "p90": float(np.percentile(values_array, 90)),
                "p95": float(np.percentile(values_array, 95)),
            },
        }

        print(f"  {feature_name}: n={len(values)}, mean={baseline_features[feature_name]['mean']:.3f}")

    # Criar documento de baseline
    baseline = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model_version": model_version,
        "sample_count": len(all_features),
        "features": baseline_features,
        "metadata": {
            "created_by": "create_reference_data.py",
            "description": f"Reference baseline for {model_version} approval model",
        },
    }

    return baseline


def generate_synthetic_baseline(samples: int = 1000) -> dict:
    """
    Gera baseline sintético para quando não há dados suficientes no MongoDB.

    Args:
        samples: Número de amostras sintéticas

    Returns:
        Dict com baseline sintético
    """
    print(f"Generating synthetic baseline with {samples} samples")

    np.random.seed(42)  # Reproduzibilidade

    # Gerar features sintéticos baseados em distribuições realistas
    synthetic_features = {
        "complexity": {
            "values": np.random.randint(1, 6, samples).tolist(),
            "count": samples,
            "mean": 3.0,
            "std": 1.2,
            "min": 1.0,
            "max": 5.0,
            "percentiles": {
                "p25": 2.0,
                "p50": 3.0,
                "p75": 4.0,
                "p90": 5.0,
                "p95": 5.0,
            },
        },
        "has_backup": {
            "values": np.random.binomial(1, 0.3, samples).astype(float).tolist(),
            "count": samples,
            "mean": 0.3,
            "std": 0.46,
            "min": 0.0,
            "max": 1.0,
            "percentiles": {"p25": 0.0, "p50": 0.0, "p75": 1.0, "p90": 1.0, "p95": 1.0},
        },
        "has_verification": {
            "values": np.random.binomial(1, 0.5, samples).astype(float).tolist(),
            "count": samples,
            "mean": 0.5,
            "std": 0.5,
            "min": 0.0,
            "max": 1.0,
            "percentiles": {"p25": 0.0, "p50": 0.5, "p75": 1.0, "p90": 1.0, "p95": 1.0},
        },
        "has_all": {
            "values": np.random.binomial(1, 0.6, samples).astype(float).tolist(),
            "count": samples,
            "mean": 0.6,
            "std": 0.49,
            "min": 0.0,
            "max": 1.0,
            "percentiles": {"p25": 0.0, "p50": 1.0, "p75": 1.0, "p90": 1.0, "p95": 1.0},
        },
        "priority": {
            "values": np.random.randint(1, 6, samples).tolist(),
            "count": samples,
            "mean": 2.5,
            "std": 1.1,
            "min": 1.0,
            "max": 5.0,
            "percentiles": {
                "p25": 2.0,
                "p50": 2.0,
                "p75": 3.0,
                "p90": 4.0,
                "p95": 5.0,
            },
        },
        "estimated_hours": {
            "values": np.random.lognormal(2, 0.5, samples).tolist(),
            "count": samples,
            "mean": 8.5,
            "std": 4.5,
            "min": 1.0,
            "max": 30.0,
            "percentiles": {
                "p25": 5.0,
                "p50": 7.5,
                "p75": 11.0,
                "p90": 14.0,
                "p95": 18.0,
            },
        },
        "actual_hours": {
            "values": np.random.lognormal(2.1, 0.6, samples).tolist(),
            "count": samples,
            "mean": 9.2,
            "std": 5.5,
            "min": 1.0,
            "max": 35.0,
            "percentiles": {
                "p25": 5.5,
                "p50": 8.0,
                "p75": 12.0,
                "p90": 16.0,
                "p95": 20.0,
            },
        },
    }

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model_version": "v7",
        "sample_count": samples,
        "features": synthetic_features,
        "metadata": {
            "created_by": "create_reference_data.py",
            "description": "Synthetic reference baseline for v7 approval model",
            "synthetic": True,
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Create reference data for drift detection")
    parser.add_argument(
        "--samples", type=int, default=1000, help="Number of synthetic samples (default: 1000)"
    )
    parser.add_argument(
        "--mongo-uri",
        type=str,
        default=os.getenv("MONGODB_URL", "mongodb://localhost:27017"),
        help="MongoDB URI",
    )
    parser.add_argument(
        "--db-name", type=str, default="nhm", help="Database name"
    )
    parser.add_argument(
        "--synthetic", action="store_true", help="Generate synthetic baseline instead of querying DB"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print baseline instead of saving"
    )
    parser.add_argument(
        "--output", type=str, help="Output file path (pkl or json). If not provided, saves to MongoDB"
    )

    args = parser.parse_args()

    print("=" * 60)
    print("Creating Reference Data for Drift Detection")
    print("=" * 60)

    baseline = None

    if args.synthetic:
        # Gerar baseline sintético
        baseline = generate_synthetic_baseline(args.samples)
    else:
        # Tentar conectar ao MongoDB e extrair dados reais
        try:
            client = MongoClient(args.mongo_uri, serverSelectionTimeoutMS=5000)
            db = client[args.db_name]
            collection = db["execution_tickets"]

            # Contar tickets disponíveis
            total_tickets = collection.count_documents({"status": "completed"})
            print(f"Found {total_tickets} completed tickets in database")

            if total_tickets < 100:
                print("Not enough tickets for reliable baseline, using synthetic data")
                baseline = generate_synthetic_baseline(args.samples)
            else:
                # Extrair amostra de tickets
                tickets = list(
                    collection.find({"status": "completed"})
                    .limit(min(args.samples, 10000))
                    .sort([("created_at", -1)])
                )

                baseline = create_baseline_from_tickets(tickets)

            client.close()

        except Exception as e:
            print(f"Error connecting to MongoDB: {e}")
            print("Falling back to synthetic baseline")
            baseline = generate_synthetic_baseline(args.samples)

    if baseline is None:
        print("Error: Could not create baseline")
        return 1

    print("\n" + "=" * 60)
    print("Baseline Summary")
    print("=" * 60)
    print(f"Model version: {baseline['model_version']}")
    print(f"Sample count: {baseline['sample_count']}")
    print(f"Features: {list(baseline['features'].keys())}")

    if args.dry_run:
        print("\n" + "=" * 60)
        print("BASELINE JSON (dry-run mode)")
        print("=" * 60)
        print(json.dumps(baseline, indent=2, default=str))
        return 0

    # Salvar em arquivo se especificado
    if args.output:
        output_path = args.output

        if output_path.endswith(".pkl"):
            import pickle

            with open(output_path, "wb") as f:
                pickle.dump(baseline, f)
            print(f"\n✅ Baseline saved to pickle: {output_path}")
            return 0

        elif output_path.endswith(".json"):
            with open(output_path, "w") as f:
                json.dump(baseline, f, indent=2, default=str)
            print(f"\n✅ Baseline saved to JSON: {output_path}")
            return 0

        else:
            print(f"Error: Unsupported output format. Use .pkl or .json")
            return 1

    # Salvar no MongoDB (padrão)
    try:
        client = MongoClient(args.mongo_uri, serverSelectionTimeoutMS=5000)
        db = client[args.db_name]
        collection = db["ml_feature_baselines"]

        # Inserir baseline
        result = collection.insert_one(baseline)

        print(f"\nBaseline saved with _id: {result.inserted_id}")

        # Verificar inserção
        saved = collection.find_one({"_id": result.inserted_id})
        print(f"Confirmed {len(saved['features'])} features in database")

        client.close()

        print("\n✅ Reference data created successfully!")
        return 0

    except Exception as e:
        print(f"Error saving to MongoDB: {e}")
        print("\nTip: Use --output baseline.pkl to save to file instead")
        return 1


if __name__ == "__main__":
    sys.exit(main())
