# Guia de Autenticação MongoDB - Neural Hive-Mind

## Problemas Comuns de Autenticação

### Erro: "Authentication failed"

Se você encontrar este erro ao tentar conectar ao MongoDB:

```
MongoServerError: Authentication failed.
```

## Solução Correta

### Usando mongosh (Recomendado)

**String de conexão correta:**
```
mongodb://root:local_dev_password@mongodb.mongodb-cluster.svc.cluster.local:27017/neural_hive?authSource=admin
```

**Exemplo de comando:**
```bash
kubectl exec -n mongodb-cluster mongodb-677c7746c4-rwwsb -- mongosh \
  "mongodb://root:local_dev_password@localhost:27017/neural_hive?authSource=admin" \
  --eval "db.cognitive_ledger.findOne({}, {_id: 0}).pretty()" --quiet
```

**Exemplo com query específica:**
```bash
kubectl exec -n mongodb-cluster mongodb-677c7746c4-rwwsb -- mongosh \
  "mongodb://root:local_dev_password@localhost:27017/neural_hive?authSource=admin" \
  --eval "db.cognitive_ledger.findOne({plan_id: 'SEU_PLAN_ID_AQUI'}, {_id: 0, plan_id: 1, intent_id: 1}).pretty()" --quiet
```

### Usando mongo (Legado - NÃO RECOMENDADO)

**String de conexão correta:**
```
mongodb://root:local_dev_password@mongodb.mongodb-cluster.svc.cluster.local:27017/neural_hive?authSource=admin
```

**Exemplo de comando:**
```bash
kubectl run mongo-shell --image=mongo:7.0 --restart=Never -i --tty --rm -- \
  mongo "mongodb://root:local_dev_password@mongodb.mongodb-cluster.svc.cluster.local:27017/neural_hive?authSource=admin" \
  --eval "db.cognitive_ledger.findOne({}, {_id: 0}).pretty()"
```

⚠️ **NOTA:** O comando `mongo` está obsoleto. Sempre prefira `mongosh`.

## Por que o parâmetro authSource=admin é necessário?

O parâmetro `authSource=admin` especifica o banco de dados de autenticação do MongoDB. No ambiente do Neural Hive-Mind:

- Usuário: `root`
- Senha: `local_dev_password`
- Banco de autenticação: `admin`
- Banco de dados de trabalho: `neural_hive`

Sem especificar `authSource=admin`, o MongoDB tenta autenticar no banco de dados `neural_hive`, onde o usuário root não está configurado, resultando em falha de autenticação.

## Collections Disponíveis

As principais collections no banco `neural_hive` são:

| Collection | Descrição | Documentos Relevantes |
|------------|-----------|------------------------|
| `cognitive_ledger` | Planos cognitivos gerados pelo STE | plan_id, intent_id, tasks |
| `consensus_decisions` | Decisões do consenso engine | decision_id, plan_id, final_decision |
| `specialist_opinions` | Opiniões dos especialistas | opinion_id, specialist_type, recommendation |
| `execution_tickets` | Tickets de execução | ticket_id, task_id, status |
| `plan_approvals` | Aprovações de planos | approval_id, plan_id, status |
| `telemetry_buffer` | Eventos de telemetria | event_id, plan_id, event_type |
| `insights` | Insights gerados | insight_id, domain, confidence |
| `incidents` | Incidentes reportados | incident_id, severity, status |

## Comandos Úteis

### Listar todas as collections
```bash
kubectl exec -n mongodb-cluster mongodb-677c7746c4-rwwsb -- mongosh \
  "mongodb://root:local_dev_password@localhost:27017/neural_hive?authSource=admin" \
  --eval "db.getCollectionNames()" --quiet
```

### Contar documentos em uma collection
```bash
kubectl exec -n mongodb-cluster mongodb-677c7746c4-rwwsb -- mongosh \
  "mongodb://root:local_dev_password@localhost:27017/neural_hive?authSource=admin" \
  --eval "db.cognitive_ledger.countDocuments({})" --quiet
```

### Buscar por plan_id
```bash
kubectl exec -n mongodb-cluster mongodb-677c7746c4-rwwsb -- mongosh \
  "mongodb://root:local_dev_password@localhost:27017/neural_hive?authSource=admin" \
  --eval "db.cognitive_ledger.findOne({plan_id: 'SEU_PLAN_ID'})" --quiet
```

### Buscar por intent_id
```bash
kubectl exec -n mongodb-cluster mongodb-677c7746c4-rwwsb -- mongosh \
  "mongodb://root:local_dev_password@localhost:27017/neural_hive?authSource=admin" \
  --eval "db.cognitive_ledger.findOne({intent_id: 'SEU_INTENT_ID'})" --quiet
```

### Buscar por decision_id
```bash
kubectl exec -n mongodb-cluster mongodb-677c7746c4-rwwsb -- mongosh \
  "mongodb://root:local_dev_password@localhost:27017/neural_hive?authSource=admin" \
  --eval "db.consensus_decisions.findOne({decision_id: 'SEU_DECISION_ID'})" --quiet
```

### Buscar últimos N documentos
```bash
kubectl exec -n mongodb-cluster mongodb-677c7746c4-rwwsb -- mongosh \
  "mongodb://root:local_dev_password@localhost:27017/neural_hive?authSource=admin" \
  --eval "db.cognitive_ledger.find({}, {_id: 0, plan_id: 1, created_at: 1}).sort({created_at: -1}).limit(5).toArray()" --quiet
```

## Troubleshooting

### Erro: "Defaulted container... out of: mongodb, metrics, log-dir (init)"

Este erro é apenas informativo e indica que o contêiner padrão `mongodb` foi selecionado automaticamente. Não afeta a execução do comando.

### Verificar se o pod está rodando
```bash
kubectl get pod -n mongodb-cluster mongodb-677c7746c4-rwwsb
```

Deve mostrar `STATUS: Running` e `READY: 2/2`.

### Verificar credenciais
```bash
kubectl get secret -n mongodb-cluster mongodb -o yaml
```

A senha está codificada em base64 no campo `mongodb-root-password`.

### Testar conexão sem execução
```bash
kubectl exec -n mongodb-cluster mongodb-677c7746c4-rwwsb -- mongosh \
  "mongodb://root:local_dev_password@localhost:27017/neural_hive?authSource=admin" \
  --eval "db.getName()" --quiet
```

Deve retornar: `neural_hive`

## Recursos Adicionais

- [Documentação MongoDB Shell (mongosh)](https://www.mongodb.com/docs/mongodb-shell/)
- [Documentação MongoDB Connection String](https://www.mongodb.com/docs/manual/reference/connection-string/)
- [Modelo de Teste Completo](./MODELO_TESTE_PIPELINE_COMPLETO.md)

## Suporte

Em caso de problemas persistentes, verifique os logs do pod MongoDB:
```bash
kubectl logs -n mongodb-cluster mongodb-677c7746c4-rwwsb
```
