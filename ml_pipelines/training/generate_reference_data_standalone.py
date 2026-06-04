#!/usr/bin/env python3
"""
Gerador de Reference Data para Drift Detector (Standalone)

Versão simplificada que não depende de carregar o modelo ML.
Gera dados sintéticos baseados nas características conhecidas do dataset v7.

Usage:
    python ml_pipelines/training/generate_reference_data_standalone.py
    python ml_pipelines/training/generate_reference_data_standalone.py --samples 100
    python ml_pipelines/training/generate_reference_data_standalone.py --version v8

Version: 1.0.0
Date: 2026-04-24
"""

import argparse
import json
import pickle
import random
from datetime import datetime, timezone
from pathlib import Path


class ReferenceDataGenerator:
    """Gerador de reference data para drift detection (standalone)."""

    # Features esperadas pelo approval_predictor (30 features)
    FEATURE_ORDER = [
        "specialist_confidence",
        "domain_security",
        "domain_performance",
        "domain_database",
        "domain_devops",
        "domain_testing",
        "action_create",
        "action_update",
        "action_delete",
        "action_read",
        "action_deploy",
        "has_backup",
        "has_verification",
        "has_all",
        "text_length_chars",
        "text_length_words",
        "risk_high",
        "risk_medium",
        "risk_low",
        "simple_risk_score",
        "primary_domain_security",
        "primary_domain_performance",
        "primary_domain_database",
        "primary_domain_devops",
        "primary_domain_testing",
        "primary_action_create",
        "primary_action_update",
        "primary_action_delete",
        "primary_action_read",
        "primary_action_deploy",
    ]

    # Domínios e pesos baseados em distribuição típica
    DOMAINS = ["security", "performance", "database", "devops", "testing"]
    DOMAIN_PROBS = [0.25, 0.20, 0.25, 0.15, 0.15]

    # Ações e pesos (menos delete actions)
    ACTIONS = ["create", "update", "delete", "read", "deploy"]
    ACTION_PROBS = [0.30, 0.25, 0.10, 0.25, 0.10]

    def __init__(self, model_version: str = "v7", n_samples: int = 75):
        """
        Inicializa gerador de referência.

        Args:
            model_version: Versão do modelo (ex: v7, v8)
            n_samples: Número de amostras para gerar
        """
        self.model_version = model_version
        self.n_samples = n_samples

    def _random_normal(self, mean: float, std: float) -> float:
        """Gera número aleatório com distribuição normal (aproximação)."""
        # Usar random.gauss que já está disponível
        return random.gauss(mean, std)

    def _generate_sample(self) -> dict:
        """Gera uma amostra de features."""
        # specialist_confidence: distribuição normal em torno de 0.6
        specialist_confidence = max(0.0, min(1.0, self._random_normal(0.6, 0.2)))

        # Domínio primário
        primary_domain = random.choices(self.DOMAINS, weights=self.DOMAIN_PROBS)[0]
        domain_features = {f"domain_{d}": 0.0 for d in self.DOMAINS}
        domain_features[f"domain_{primary_domain}"] = 1.0

        # Ação primária
        primary_action = random.choices(self.ACTIONS, weights=self.ACTION_PROBS)[0]
        action_features = {f"action_{a}": 0.0 for a in self.ACTIONS}
        action_features[f"action_{primary_action}"] = 1.0

        # Possível ação secundária
        if random.random() < 0.2:
            secondary_action = random.choice([a for a in self.ACTIONS if a != primary_action])
            action_features[f"action_{secondary_action}"] = 1.0

        # Palavras-chave
        has_backup = (
            1.0 if primary_action in ["create", "update"] and random.random() < 0.3 else 0.0
        )
        has_verification = 1.0 if random.random() < 0.4 else 0.0
        has_all = 1.0 if primary_action == "delete" and random.random() < 0.15 else 0.0

        # Métricas de texto
        text_length_chars = max(20, min(200, int(random.gauss(80, 40))))
        text_length_words = max(1, text_length_chars // 5)

        # Risco (derivado de ações)
        risk_high = 1.0 if primary_action == "delete" else 0.0
        risk_medium = 1.0 if primary_action == "update" else 0.0
        risk_low = 1.0 if primary_action in ["create", "read", "deploy"] else 0.0

        # Simple risk score
        dangerous_count = (1 if risk_high > 0 else 0) + (0.5 if risk_medium > 0 else 0)
        simple_risk_score = min(1.0, dangerous_count * 0.3)

        # Domínio primário (one-hot)
        primary_domain_features = {f"primary_domain_{d}": 0.0 for d in self.DOMAINS}
        primary_domain_features[f"primary_domain_{primary_domain}"] = 1.0

        # Ação primária (one-hot)
        primary_action_features = {f"primary_action_{a}": 0.0 for a in self.ACTIONS}
        primary_action_features[f"primary_action_{primary_action}"] = 1.0

        # Combinar todas as features
        return {
            "specialist_confidence": specialist_confidence,
            **domain_features,
            **action_features,
            "has_backup": has_backup,
            "has_verification": has_verification,
            "has_all": has_all,
            "text_length_chars": text_length_chars,
            "text_length_words": text_length_words,
            "risk_high": risk_high,
            "risk_medium": risk_medium,
            "risk_low": risk_low,
            "simple_risk_score": simple_risk_score,
            **primary_domain_features,
            **primary_action_features,
        }

    def generate_dataframe(self):
        """
        Gera DataFrame de referência.

        Returns:
            Lista de dicionários com as features
        """
        data = []

        for _ in range(self.n_samples):
            data.append(self._generate_sample())

        return data

    def calculate_statistics(self, data: list) -> dict:
        """Calcula estatísticas das features."""
        stats = {}

        # Inicializar listas por feature
        feature_values = {feature: [] for feature in self.FEATURE_ORDER}

        for row in data:
            for feature in self.FEATURE_ORDER:
                feature_values[feature].append(row[feature])

        # Calcular estatísticas para cada feature
        for feature in self.FEATURE_ORDER:
            values = sorted(feature_values[feature])
            n = len(values)

            stats[feature] = {
                "mean": sum(values) / n,
                "std": (sum((x - sum(values) / n) ** 2 for x in values) / n) ** 0.5,
                "min": values[0],
                "max": values[-1],
                "q25": values[n // 4],
                "q50": values[n // 2],
                "q75": values[3 * n // 4],
            }

        return stats

    def save_reference_data(self, output_path: Path) -> dict:
        """Salva dados de referência."""
        # Gerar dados
        data = self.generate_dataframe()

        # Calcular estatísticas
        feature_stats = self.calculate_statistics(data)

        # Criar metadados
        metadata = {
            "model_name": "approval_predictor",
            "model_version": self.model_version,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "training_samples": self.n_samples,
            "features": self.FEATURE_ORDER,
            "feature_stats": feature_stats,
            "source": "synthetic_generator",
        }

        # Salvar como pickle
        reference_data = {
            "metadata": metadata,
            "data": data,
        }

        with open(output_path, "wb") as f:
            pickle.dump(reference_data, f)

        # Salvar metadados JSON
        metadata_path = output_path.with_suffix(".metadata.json")
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)

        return metadata


def main():
    """Função principal."""
    parser = argparse.ArgumentParser(
        description="Gerar reference data para drift detector (standalone)"
    )
    parser.add_argument(
        "--version",
        type=str,
        default="v7",
        help="Versão do modelo (default: v7)",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=75,
        help="Número de amostras (default: 75)",
    )
    parser.add_argument(
        "--output-path",
        type=Path,
        default=None,
        help="Caminho de saída (auto se não especificado)",
    )
    args = parser.parse_args()

    # Determinar caminho de saída
    if args.output_path is None:
        output_dir = Path("ml_pipelines/training/reference_data")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"approval_{args.version}_reference.pkl"
    else:
        output_path = args.output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("REFERENCE DATA GENERATOR (STANDALONE)")
    print("=" * 60)
    print(f"Model version: {args.version}")
    print(f"Samples: {args.samples}")
    print(f"Output path: {output_path}")
    print("")

    try:
        # Gerar reference data
        generator = ReferenceDataGenerator(model_version=args.version, n_samples=args.samples)
        metadata = generator.save_reference_data(output_path)

        print("=" * 60)
        print("REFERENCE DATA GENERATED SUCCESSFULLY")
        print("=" * 60)
        print(f"Model version: {metadata['model_version']}")
        print(f"Training samples: {metadata['training_samples']}")
        print(f"Features: {len(metadata['features'])}")
        print(f"Output file: {output_path}")
        print("")
        print("To use in orchestrator settings:")
        print(f"  drift_reference_dataset_path: {output_path.absolute()}")

        return 0

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
