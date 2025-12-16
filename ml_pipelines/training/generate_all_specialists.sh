#!/bin/bash
#
# Script para gerar datasets de treinamento para especialistas
# Uso: ./generate_all_specialists.sh [num_samples] [provider] [model] [specialist]
#
# Exemplos:
#   ./generate_all_specialists.sh                              # 100 samples, todos especialistas
#   ./generate_all_specialists.sh 200                          # 200 samples, todos
#   ./generate_all_specialists.sh 100 deepseek deepseek-chat   # todos com deepseek
#   ./generate_all_specialists.sh 100 deepseek deepseek-chat business    # apenas business
#   ./generate_all_specialists.sh 300 deepseek deepseek-chat technical   # apenas technical
#   ./generate_all_specialists.sh 100 groq llama-3.3-70b-versatile all   # todos explícito
#
# Especialistas disponíveis: technical, business, behavior, evolution, architecture, all
#

set -e

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Diretório do script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Configurar PYTHONPATH para incluir bibliotecas locais
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
export PYTHONPATH="${PROJECT_ROOT}/libraries/python:${PROJECT_ROOT}/ml_pipelines:${PYTHONPATH:-}"
echo -e "${BLUE}PYTHONPATH configurado: ${PYTHONPATH}${NC}"

# Carregar variáveis de ambiente de arquivos .env se existirem
if [ -f ".env.training" ]; then
    echo -e "${BLUE}Carregando configurações de .env.training${NC}"
    set -a
    source .env.training
    set +a
fi

if [ -f ".env" ]; then
    echo -e "${BLUE}Carregando configurações de .env${NC}"
    set -a
    source .env
    set +a
fi

# Parâmetros com valores default (prioriza argumentos da linha de comando)
NUM_SAMPLES="${1:-100}"
LLM_PROVIDER="${2:-${LLM_PROVIDER:-openai}}"
LLM_MODEL="${3:-${LLM_MODEL:-gpt-4}}"
SPECIALIST_FILTER="${4:-all}"

# Validar API key
if [ -z "$LLM_API_KEY" ]; then
    echo -e "${RED}ERRO: LLM_API_KEY não está definida${NC}"
    echo "Defina a variável de ambiente ou adicione em .env.training"
    echo ""
    echo "Opção 1 - Exportar manualmente:"
    echo "  export LLM_API_KEY='sua-api-key'"
    echo "  ./generate_all_specialists.sh"
    echo ""
    echo "Opção 2 - Adicionar em .env.training:"
    echo "  echo 'LLM_API_KEY=sua-api-key' >> .env.training"
    exit 1
fi

# Lista de especialistas disponíveis
ALL_SPECIALISTS=("technical" "business" "behavior" "evolution" "architecture")

# Filtrar especialistas baseado no parâmetro
if [ "$SPECIALIST_FILTER" = "all" ] || [ -z "$SPECIALIST_FILTER" ]; then
    SPECIALISTS=("${ALL_SPECIALISTS[@]}")
else
    # Validar se o especialista existe
    VALID=false
    for s in "${ALL_SPECIALISTS[@]}"; do
        if [ "$s" = "$SPECIALIST_FILTER" ]; then
            VALID=true
            break
        fi
    done

    if [ "$VALID" = false ]; then
        echo -e "${RED}ERRO: Especialista '$SPECIALIST_FILTER' não encontrado${NC}"
        echo "Especialistas disponíveis: ${ALL_SPECIALISTS[*]}"
        echo "Use 'all' para gerar todos"
        exit 1
    fi

    SPECIALISTS=("$SPECIALIST_FILTER")
fi

# Diretório de output
OUTPUT_DIR="${SCRIPT_DIR}/data"
mkdir -p "$OUTPUT_DIR"

# Arquivo de log
LOG_FILE="${SCRIPT_DIR}/logs/generation_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$(dirname "$LOG_FILE")"

# Função para logging
log() {
    echo -e "$1" | tee -a "$LOG_FILE"
}

# Header
log ""
log "=============================================="
log "${BLUE}🧠 Neural Hive Mind - Geração de Datasets${NC}"
log "=============================================="
log ""
log "Configuração:"
log "  • Samples por especialista: ${GREEN}${NUM_SAMPLES}${NC}"
log "  • Provider LLM: ${GREEN}${LLM_PROVIDER}${NC}"
log "  • Modelo: ${GREEN}${LLM_MODEL}${NC}"
log "  • Output: ${GREEN}${OUTPUT_DIR}${NC}"
log "  • Log: ${GREEN}${LOG_FILE}${NC}"
log "  • Filtro: ${GREEN}${SPECIALIST_FILTER}${NC}"
log ""
log "Especialistas a gerar: ${SPECIALISTS[*]}"
log ""
log "=============================================="

# Variáveis para tracking
TOTAL_SUCCESS=0
TOTAL_FAILED=0
START_TIME=$(date +%s)

# Gerar para cada especialista
for specialist in "${SPECIALISTS[@]}"; do
    log ""
    log "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    log "${BLUE}📊 Gerando dataset: specialist-${specialist}${NC}"
    log "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

    OUTPUT_FILE="${OUTPUT_DIR}/specialist_${specialist}_new.parquet"
    SPECIALIST_START=$(date +%s)

    # Executar geração
    if python3 generate_training_datasets.py \
        --specialist-type "$specialist" \
        --num-samples "$NUM_SAMPLES" \
        --output-path "$OUTPUT_FILE" \
        --llm-provider "$LLM_PROVIDER" \
        --llm-model "$LLM_MODEL" \
        --min-quality-score 0.5 \
        2>&1 | tee -a "$LOG_FILE"; then

        SPECIALIST_END=$(date +%s)
        DURATION=$((SPECIALIST_END - SPECIALIST_START))

        # Verificar se arquivo foi criado
        if [ -f "$OUTPUT_FILE" ]; then
            # Contar samples gerados
            SAMPLES=$(python3 -c "import pandas as pd; print(len(pd.read_parquet('$OUTPUT_FILE')))" 2>/dev/null || echo "?")
            log "${GREEN}✓ Sucesso: ${specialist} - ${SAMPLES} samples em ${DURATION}s${NC}"
            ((TOTAL_SUCCESS++))

            # Combinar com dataset existente se houver
            BASE_FILE="${OUTPUT_DIR}/specialist_${specialist}_base.parquet"
            if [ -f "$BASE_FILE" ]; then
                log "  Combinando com dataset existente..."
                python3 -c "
import pandas as pd
existing = pd.read_parquet('$BASE_FILE')
new = pd.read_parquet('$OUTPUT_FILE')
combined = pd.concat([existing, new], ignore_index=True)
combined.to_parquet('$BASE_FILE', index=False)
print(f'  Existente: {len(existing)} | Novos: {len(new)} | Total: {len(combined)}')
" 2>&1 | tee -a "$LOG_FILE"
            else
                # Se não existe base, usar o novo como base
                cp "$OUTPUT_FILE" "$BASE_FILE"
                log "  Criado novo arquivo base: $BASE_FILE"
            fi
        else
            log "${RED}✗ Falha: ${specialist} - arquivo não criado${NC}"
            ((TOTAL_FAILED++))
        fi
    else
        log "${RED}✗ Falha: ${specialist} - erro na execução${NC}"
        ((TOTAL_FAILED++))
    fi
done

# Sumário final
END_TIME=$(date +%s)
TOTAL_DURATION=$((END_TIME - START_TIME))

log ""
log "=============================================="
log "${BLUE}📋 SUMÁRIO FINAL${NC}"
log "=============================================="
log ""
log "Tempo total: ${TOTAL_DURATION}s ($(( TOTAL_DURATION / 60 ))m $(( TOTAL_DURATION % 60 ))s)"
log "Sucesso: ${GREEN}${TOTAL_SUCCESS}${NC} / ${#SPECIALISTS[@]}"
log "Falhas: ${RED}${TOTAL_FAILED}${NC}"
log ""

# Status dos datasets finais
log "Status dos datasets:"
for specialist in "${SPECIALISTS[@]}"; do
    BASE_FILE="${OUTPUT_DIR}/specialist_${specialist}_base.parquet"
    if [ -f "$BASE_FILE" ]; then
        # Obter estatísticas do dataset
        STATS=$(python3 -c "
import pandas as pd
df = pd.read_parquet('$BASE_FILE')
labels = df['label'].value_counts().to_dict()
label_names = {0: 'reject', 1: 'approve', 2: 'review', 3: 'conditional'}
label_str = ', '.join([f'{label_names.get(k, k)}:{v}' for k, v in sorted(labels.items())])
print(f'{len(df)} samples | {label_str}')
" 2>/dev/null || echo "erro ao ler")
        log "  ${GREEN}✓${NC} specialist_${specialist}_base.parquet: ${STATS}"
    else
        log "  ${RED}✗${NC} specialist_${specialist}_base.parquet: não encontrado"
    fi
done

log ""
log "=============================================="
log "${GREEN}Geração finalizada!${NC}"
log "=============================================="
log ""

# Exit code baseado em falhas
if [ "$TOTAL_FAILED" -gt 0 ]; then
    exit 1
fi
exit 0
