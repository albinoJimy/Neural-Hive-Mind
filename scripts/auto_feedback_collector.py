#!/usr/bin/env python3
"""
Coleta Automatizada de Feedback para ML Specialists

Gera feedback baseado em heurísticas simples para criar dataset rotulado.
As regras são:
- Baixa confiança (< 0.3) → review_required
- Alta confiança (> 0.7) → approve (confirma modelo)
- Recomendação "approve" com alta confiança → approve
- Caso contrário → segue recomendação do modelo com rating ajustado
"""

import sys
import subprocess
subprocess.check_call([sys.executable, "-m", "pip", "install", "pymongo", "-q"])

from pymongo import MongoClient
from datetime import datetime
import random
import time

MONGO_URI = "mongodb://root:local_dev_password@mongodb.mongodb-cluster.svc.cluster.local:27017/neural_hive?authSource=admin"
client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
db = client.neural_hive
opinions_col = db.specialist_opinions
feedback_col = db.specialist_feedback

def generate_auto_feedback(opinion):
    """Gera feedback automático baseado em heurísticas."""
    confidence = opinion.get("opinion", {}).get("confidence_score", 0.5)
    model_rec = opinion.get("opinion", {}).get("recommendation", "review_required")
    specialist = opinion.get("specialist_type", "unknown")

    # Heurística 1: Baixa confiança → requer revisão humana (mas vamos marcar como review_required)
    if confidence < 0.3:
        return "review_required", 0.3

    # Heurística 2: Alta confiança → aprovar recomendação do modelo
    elif confidence > 0.7:
        if model_rec == "approve":
            return "approve", 0.9
        elif model_rec == "reject":
            return "reject", 0.85
        else:
            return "review_required", 0.7

    # Heurística 3: Recomendação approve com confiança média → aprovar
    elif model_rec == "approve" and confidence > 0.5:
        return "approve", 0.75

    # Heurística 4: Caso contrário → seguir modelo mas com rating moderado
    elif model_rec in ["approve", "reject", "review_required"]:
        return model_rec, confidence + 0.1

    # Heurística 5: conditional → review_required
    else:
        return "review_required", 0.6

def collect_batch(batch_size=50):
    """Coleta feedback em lote."""
    # Buscar opiniões sem feedback
    query = {"specialist_feedback": {"$exists": False}}

    # Preferir opiniões com maior confiança primeiro (mais fáceis de rotular)
    opinions = list(opinions_col.find(query).sort("evaluated_at", -1).limit(batch_size))

    if not opinions:
        print("Nenhuma opinião pendente encontrada!")
        return 0

    print(f"Processando {len(opinions)} opiniões...")

    collected = 0
    for i, opinion in enumerate(opinions, 1):
        opinion_id = opinion.get("opinion_id")
        specialist = opinion.get("specialist_type")
        confidence = opinion.get("opinion", {}).get("confidence_score", 0.5)
        model_rec = opinion.get("opinion", {}).get("recommendation", "?")

        # Gerar feedback automático
        rec, rating = generate_auto_feedback(opinion)

        feedback_doc = {
            "feedback_id": f"fb-auto-{datetime.utcnow().timestamp()}-{i}",
            "opinion_id": opinion_id,
            "opinion_recommendation": model_rec,
            "human_recommendation": rec,
            "human_rating": rating,
            "feedback_notes": "[AUTO] Feedback gerado por heurística",
            "specialist_type": specialist,
            "auto_generated": True,
            "submitted_at": datetime.utcnow(),
            "trace_id": opinion.get("trace_id")
        }

        try:
            result = feedback_col.insert_one(feedback_doc)
            collected += 1

            # Progresso a cada 10
            if i % 10 == 0:
                print(f"  [{i}/{len(opinions)}] {specialist}: {rec} (conf: {confidence:.2f}→{rating:.2f})")
        except Exception as e:
            print(f"  Erro ao processar {opinion_id}: {e}")

    return collected

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Coleta automática de feedback")
    parser.add_argument("--batch", type=int, default=50, help="Tamanho do lote (default: 50)")
    parser.add_argument("--target", type=int, default=100, help="Target total de feedbacks")
    args = parser.parse_args()

    print(f"Iniciando coleta automática de feedback...")
    print(f"Meta: {args.target} feedbacks")
    print(f"Lote: {args.batch} opiniões por execução")
    print()

    # Verificar estatísticas atuais
    total = opinions_col.count_documents({})
    with_fb = feedback_col.count_documents({})
    pending = total - with_fb

    print(f"Estatísticas atuais: {with_fb}/{total} feedbacks coletados")
    print(f"Pendentes: {pending}")
    print()

    # Coletar em lotes até atingir target
    collected = 0
    while with_fb + collected < args.target and pending > 0:
        batch_collected = collect_batch(min(args.batch, args.target - collected))
        if batch_collected == 0:
            break

        collected += batch_collected
        with_fb = feedback_col.count_documents({})
        pending = total - with_fb

        print(f"Lote concluído! Total: {with_fb}/{total} ({(with_fb/total*100):.1f}%)")
        print()

        if pending > 0:
            time.sleep(1)  # Pequena pausa entre lotes

    print(f"\n✓ Coleta concluída!")
    print(f"  Feedbacks coletados: {with_fb}")
    print(f"  Progresso: {(with_fb/total*100):.1f}%")
