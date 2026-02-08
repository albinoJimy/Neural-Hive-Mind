# Resumo: Coleta de Feedback e Retreinamento ML

## Data: 2026-02-08

## ✅ Coleta de Feedback - COMPLETA

### Estatísticas Finais

| Métrica | Valor |
|---------|-------|
| Total de feedbacks coletados | 1002 |
| Cobertura | 22.3% (1002/4490) |
| Rodadas de coleta automática | 9 |

### Distribuição por Especialista

| Especialista | Feedbacks | Status Retreinamento |
|--------------|-----------|---------------------|
| architecture | 201 | READY |
| business | 201 | READY |
| technical | 200 | READY |
| behavior | 200 | READY |
| evolution | 200 | READY |

### Distribuição de Feedbacks

| Recomendação | Quantidade | % |
|--------------|-----------|---|
| review_required | 995 | 99.3% |
| approve | 2 | 0.2% |
| conditional | 5 | 0.5% |

## ⚠️ Desafios de Retreinamento

### Problema 1: Dados Desbalanceados

**Causa raiz**: Todos os feedbacks automáticos são "review_required" porque:
- Modelos foram treinados com dados sintéticos
- Confiança dos modelos é ~50% (baixa)
- Heurística marca baixa confiança como "review_required"

**Impacto**: Sem exemplos positivos ("approve"), o modelo treinado apenas prevê a classe negativa.

### Problema 2: API MLflow

**Erro**: `mlflow.sklearn.log_model()` falhou com 404 ao tentar registrar modelo.

**Possível causa**: Versão incompatível do MLflow ou endpoint diferente na configuração do cluster.

## 🔧 Abordagens para Resolver

### Opção 1: Coleta de Feedback Humano Real

**Objetivo**: Ter feedbacks diversificados (approve/reject/review_required)

**Implementação**:
1. Usar interface web: `http://37.60.241.150:30080`
2. Revisar manualmente opiniões e fornecer feedback variado
3. Meta: 100+ feedbacks "approve" e 100+ "reject"

### Opção 2: Ajustar Heurística de Feedback

**Atual**: Baixa confiança → review_required

**Proposta**:
- Se confiança > 0.7 → seguir recomendação do modelo
- Adicionar aleatoriedade controlada para diversificar

### Opção 3: Retreinar com Dados Sintéticos Melhorados

Gerar novos dados sintéticos com:
- Maior variedade de cenários
- Exemplos explícitos de approve/reject
- Confiança variada

## 📊 Serviços e Arquivos Criados

### Kubernetes Jobs

1. **`k8s/auto-feedback-job.yaml`**
   - Coleta 100 feedbacks por execução
   - Heurística baseada em confiança

2. **`k8s/check_retraining_status.yaml`**
   - Verifica contagem de feedbacks por especialista

3. **`k8s/retrain-model-job.yaml`**
   - Job de retreinamento (em desenvolvimento)

### Serviços HTTP

- **Feedback Collection**: `http://37.60.241.150:30080`
  - GET `/api/v1/feedback/stats` - Estatísticas
  - GET `/api/v1/opinions/pending` - Opiniões pendentes
  - POST `/api/v1/feedback` - Submeter feedback

### Documentos

- **`docs/FEEDBACK_SERVICE.md`** - Documentação do serviço
- **`docs/RETRAINING_STATUS_2026-02-08.md`** - Status de retreinamento

## 🚀 Próximos Passos Recomendados

### Curto Prazo

1. **Coletar feedback humano manual**
   - Usar interface web
   - Revisar ~50-100 opiniões
   - Fornecer feedback diversificado

2. **Validação de dados**
   - Verificar qualidade dos feedbacks automáticos
   - Criar dataset de validação

3. **Testar retreinamento pequeno**
   - 100-200 amostras balanceadas
   - Métricas de validação

### Médio Prazo

1. **Criar imagem Docker de treinamento**
   - Com todo o código de pipeline
   - Dependências pré-instaladas

2. **Configurar CI/CD de modelos**
   - Automatizar retreinamento
   - Validação automática
   - Deploy de novos modelos

3. **Monitoramento de performance**
   - Métricas em produção
   - Comparação base vs novo modelo

## 📝 Comandos Úteis

```bash
# Verificar status dos feedbacks
kubectl apply -f k8s/check_retraining_status.yaml

# Coletar mais feedbacks
kubectl apply -f k8s/auto-feedback-job.yaml

# Ver estatísticas via API
curl http://37.60.241.150:30080/api/v1/feedback/stats

# Interface web de feedback
# http://37.60.241.150:30080
```

## 🎯 Conclusão

A coleta automatizada de feedback foi **bem-sucedida**, atingindo 1002 feedbacks (22.3% de cobertura). Todos os 5 especialistas atingiram o threshold de 100 feedbacks.

O retreinamento requer **dados mais diversificados** para ser eficaz. A próxima etapa prioritária é **coletar feedback humano real** através da interface web para criar um dataset balanceado.

---

**Gerado**: 2026-02-08
**Status**: Coleta completa, Retreinamento pendente dados balanceados
