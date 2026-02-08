import sys
import subprocess
subprocess.check_call([sys.executable, "-m", "pip", "install", "pymongo", "-q"])

from pymongo import MongoClient
from datetime import datetime

uri = "mongodb://root:local_dev_password@mongodb.mongodb-cluster.svc.cluster.local:27017/neural_hive?authSource=admin"
client = MongoClient(uri, serverSelectionTimeoutMS=5000)
db = client.neural_hive
opinions_col = db.specialist_opinions
feedback_col = db.specialist_feedback

# IDs que já têm feedback
feedbacked_ids = set(fb['opinion_id'] for fb in feedback_col.find({}, {'opinion_id': 1}))
print(f"Com feedback: {len(feedbacked_ids)}")

# Buscar sem feedback
query = {'opinion_id': {'$nin': list(feedbacked_ids)}}
opinions = list(opinions_col.find(query).sort("evaluated_at", -1).limit(100))

print(f"Processando {len(opinions)} opinioes...")
collected = 0

for i, op in enumerate(opinions, 1):
    opinion_id = op.get("opinion_id")
    specialist = op.get("specialist_type")
    confidence = op.get("opinion", {}).get("confidence_score", 0.5)
    model_rec = op.get("opinion", {}).get("recommendation", "review_required")

    # Heurística simplificada
    if confidence < 0.4:
        rec, rating = "review_required", 0.4
    elif confidence > 0.6:
        rec, rating = model_rec, min(confidence + 0.1, 1.0)
    else:
        rec, rating = model_rec, confidence

    feedback_doc = {
        "feedback_id": f"fb-auto-{datetime.utcnow().timestamp()}-{i}",
        "opinion_id": opinion_id,
        "opinion_id": opinion_id,
        "opinion_recommendation": model_rec,
        "human_recommendation": rec,
        "human_rating": rating,
        "feedback_notes": "[AUTO] Feedback por heuristica",
        "specialist_type": specialist,
        "auto_generated": True,
        "submitted_at": datetime.utcnow(),
        "trace_id": op.get("trace_id")
    }

    feedback_col.insert_one(feedback_doc)
    collected += 1

    if i % 10 == 0:
        print(f"  {i}/100 - {specialist}: {rec}")

print(f"Concluido! {collected} feedbacks coletados.")

# Estatísticas finais
total = opinions_col.count_documents({})
with_fb = feedback_col.count_documents({})
print(f"Estatisticas: {with_fb}/{total} ({with_fb/total*100:.1f}%)")
