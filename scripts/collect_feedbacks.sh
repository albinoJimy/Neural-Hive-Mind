#!/bin/bash
# Script para coletar e analisar feedbacks para retraining do modelo ML v7
# Objetivo: Coletar 50 feedbacks com intent_raw_text (15 approve, 15 reject, 20 review_required)

set -e

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configurações
MONGODB_URI="${MONGODB_URI:-mongodb://localhost:27017}"
DB_NAME="${DB_NAME:-neural_hive}"
OUTPUT_DIR="/home/jimy/NHM/Neural-Hive-Mind/docs/ml-training/feedbacks-$(date +%Y%m%d)"

# Metas de coleta
GOAL_APPROVE=15
GOAL_REJECT=15
GOAL_REVIEW=20
GOAL_TOTAL=50

echo -e "${BLUE}=== Coletor de Feedbacks para Retraining ML v7 ===${NC}"
echo ""

# Criar diretório de output
mkdir -p "$OUTPUT_DIR"

# Função para conectar ao MongoDB e coletar dados
collect_feedbacks() {
    echo -e "${YELLOW}Conectando ao MongoDB...${NC}"
    
    # Usar Python para processamento mais robusto
    python3 << PYTHON_EOF
import os
import sys
from datetime import datetime
from pymongo import MongoClient
import json

# Configuração
MONGODB_URI = os.environ.get('MONGODB_URI', 'mongodb://localhost:27017')
DB_NAME = os.environ.get('DB_NAME', 'neural_hive')
OUTPUT_DIR = "$OUTPUT_DIR"

try:
    client = MongoClient(MONGODB_URI)
    db = client[DB_NAME]
    
    # Contar feedbacks por tipo
    pipeline = [
        {"$match": {"intent_raw_text": {"$exists": True, "$ne": None}}},
        {"$group": {"_id": "$decision", "count": {"$sum": 1}}}
    ]
    
    results = list(db.specialist_feedback.aggregate(pipeline))
    
    counts = {"approve": 0, "reject": 0, "review_required": 0}
    for r in results:
        if r['_id'] in counts:
            counts[r['_id']] = r['count']
    
    total = sum(counts.values())
    
    # Calcular progresso
    goals = {"approve": $GOAL_APPROVE, "reject": $GOAL_REJECT, "review_required": $GOAL_REVIEW}
    
    print("\n=== Progresso Atual ===")
    print(f"{'Tipo':<15} {'Atual':<10} {'Meta':<10} {'Progresso':<15}")
    print("-" * 55)
    
    for decision, goal in goals.items():
        current = counts.get(decision, 0)
        pct = min(100, int(current / goal * 100)) if goal > 0 else 0
        bar = "█" * (pct // 2) + "░" * (50 - pct // 2)
        status = "✅" if current >= goal else "⏳"
        print(f"{decision:<15} {current:<10} {goal:<10} [{bar}] {pct}% {status}")
    
    print("-" * 55)
    print(f"{'TOTAL':<15} {total:<10} $GOAL_TOTAL<10}")
    
    # Coletar amostras para análise
    if total > 0:
        print(f"\n=== Coletando amostras para análise ===")
        
        feedbacks = list(db.specialist_feedback.find(
            {"intent_raw_text": {"$exists": True, "$ne": None}},
            {"_id": 0, "specialist_type": 1, "decision": 1, "confidence": 1, 
             "risk_score": 1, "intent_raw_text": 1, "reasoning_factors": 1,
             "nlp_features": 1, "timestamp": 1}
        ).limit($GOAL_TOTAL))
        
        # Exportar para JSON
        output_file = f"{OUTPUT_DIR}/feedbacks_raw.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(feedbacks, f, indent=2, default=str)
        print(f"✅ Exportados {len(feedbacks)} feedbacks para {output_file}")
        
        # Gerar relatório markdown
        report_file = f"{OUTPUT_DIR}/relatorio_feedbacks.md"
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(f"# Relatório de Coleta de Feedbacks\n\n")
            f.write(f"**Data:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write(f"## Resumo\n\n")
            f.write(f"| Tipo | Atual | Meta | Status |\n")
            f.write(f"|------|-------|------|--------|\n")
            
            for decision, goal in goals.items():
                current = counts.get(decision, 0)
                status = "✅ Completo" if current >= goal else "⏳ Em andamento"
                f.write(f"| {decision} | {current} | {goal} | {status} |\n")
            
            f.write(f"| **TOTAL** | **{total}** | **$GOAL_TOTAL** | **{int(total/$GOAL_TOTAL*100)}%** |\n\n")
            
            # Verificar NLP features
            has_nlp = sum(1 for fb in feedbacks if fb.get('nlp_features'))
            f.write(f"## Qualidade dos Dados\n\n")
            f.write(f"- Feedbacks com NLP features: {has_nlp}/{len(feedbacks)} ({int(has_nlp/len(feedbacks)*100) if feedbacks else 0}%)\n")
            f.write(f"- Feedbacks com reasoning_factors: {sum(1 for fb in feedbacks if fb.get('reasoning_factors'))}/{len(feedbacks)}\n\n")
            
            # Amostras por tipo
            f.write(f"## Amostras por Tipo\n\n")
            for decision in ["approve", "reject", "review_required"]:
                samples = [fb for fb in feedbacks if fb.get('decision') == decision][:3]
                f.write(f"### {decision.upper()}\n\n")
                for sample in samples:
                    intent = sample.get('intent_raw_text', 'N/A')[:100]
                    f.write(f"- **{intent}...**\n")
                    f.write(f"  - Confidence: {sample.get('confidence', 'N/A')}\n")
                    f.write(f"  - Risk: {sample.get('risk_score', 'N/A')}\n")
                    f.write(f"  - NLP Features: {'Sim' if sample.get('nlp_features') else 'Não'}\n\n")
        
        print(f"✅ Relatório gerado: {report_file}")
        
        # Verificar se atingiu a meta
        if total >= $GOAL_TOTAL and all(counts.get(d, 0) >= goals[d] for d in goals):
            print("\n🎉 META ATINGIDA! Pronto para retraining!")
            return 0
        else:
            missing = sum(max(0, goals[d] - counts.get(d, 0)) for d in goals)
            print(f"\n⚠️  Ainda faltam {missing} feedbacks para atingir a meta.")
            return 1
    
    else:
        print("⚠️  Nenhum feedback com intent_raw_text encontrado.")
        return 2

except Exception as e:
    print(f"❌ Erro: {e}")
    sys.exit(1)
PYTHON_EOF
}

# Executar coleta
collect_feedbacks

echo ""
echo -e "${BLUE}=== Próximos Passos ===${NC}"
echo "1. Gerar mais intenções de teste: python scripts/generate_test_intents.py"
echo "2. Enviar intenções para aprovação: python scripts/test_intents_created.json"
echo "3. Coletar feedbacks novamente: ./scripts/collect_feedbacks.sh"
echo "4. Retraining com dados coletados: python ml_pipelines/training/retrain_v5_semantic_features.py"
