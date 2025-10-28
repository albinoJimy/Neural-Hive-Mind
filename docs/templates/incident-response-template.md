# Template de Resposta a Incidentes - Neural Hive-Mind

**Incident ID:** INC-YYYY-MMDD-###
**Date:** [Data/Hora do Incidente]
**Severity:** [1-Critical | 2-High | 3-Medium | 4-Low]
**Status:** [Open | In Progress | Resolved | Closed]
**Incident Commander:** [Nome]

## Resumo do Incidente

**Sistema Afetado:** Neural Hive-Mind
**Componente(s):** [API Gateway | Neural Engine | Database | etc.]
**Impacto:** [Descrição do impacto]
**Usuários Afetados:** [Número/Percentual]

### Descrição Inicial
[Breve descrição do problema observado]

### Sintomas Observados
- [ ] Sistema completamente indisponível
- [ ] Degradação de performance
- [ ] Erros intermitentes
- [ ] Alta latência
- [ ] Falhas de autenticação
- [ ] Problemas de conectividade
- [ ] Outros: [Especificar]

## Timeline do Incidente

| Horário | Evento | Ação Tomada | Responsável |
|---------|--------|-------------|-------------|
| [HH:MM] | Detecção inicial | [Descrição] | [Nome] |
| [HH:MM] | Escalação | [Para quem/onde] | [Nome] |
| [HH:MM] | Investigação iniciada | [Primeiros passos] | [Nome] |
| [HH:MM] | Causa identificada | [Descrição da causa] | [Nome] |
| [HH:MM] | Correção aplicada | [Solução implementada] | [Nome] |
| [HH:MM] | Verificação | [Testes realizados] | [Nome] |
| [HH:MM] | Resolução | [Confirmação da correção] | [Nome] |

## Informações Técnicas

### Ambiente
- **Cluster:** [Nome/ID do cluster]
- **Namespace:** neural-hive-mind
- **Versão da Aplicação:** [Versão]
- **Última Deploy:** [Data/Hora]

### Dados Coletados

#### Logs Relevantes
```
[Colar logs relevantes aqui]
```

#### Métricas no Momento do Incidente
- **CPU Usage:** [%]
- **Memory Usage:** [%]
- **Network Throughput:** [Mbps]
- **Error Rate:** [%]
- **Response Time P95:** [ms]

#### Comandos de Diagnóstico Executados
```bash
# Lista de comandos executados para diagnóstico
kubectl get pods -n neural-hive-mind
kubectl describe pod [pod-name] -n neural-hive-mind
kubectl logs [pod-name] -n neural-hive-mind --since=1h
```

### Análise da Causa Raiz

#### Investigação
[Descrever processo de investigação]

#### Causa Raiz Identificada
[Descrição detalhada da causa raiz]

#### Fatores Contribuintes
1. [Fator 1]
2. [Fator 2]
3. [Fator 3]

## Resolução

### Solução Implementada
[Descrição detalhada da solução]

### Workarounds Aplicados
[Se aplicável, descrever workarounds temporários]

### Comandos de Correção
```bash
# Comandos executados para correção
[Lista de comandos]
```

### Validação da Resolução
- [ ] Testes funcionais executados
- [ ] Métricas retornaram ao normal
- [ ] Logs não mostram mais erros
- [ ] Usuários confirmaram normalização
- [ ] Monitoramento indica sistema estável

```bash
# Comandos de validação executados
./scripts/validation/validate-cluster-health.sh
./scripts/validation/test-mtls-connectivity.sh
```

## Comunicação

### Stakeholders Notificados
- [ ] Equipe de Desenvolvimento
- [ ] Gerência Técnica
- [ ] Usuários Finais
- [ ] Suporte ao Cliente
- [ ] Outros: [Especificar]

### Canais de Comunicação Utilizados
- [ ] Slack (#incident-response)
- [ ] Email
- [ ] Status Page
- [ ] Chat interno
- [ ] Telefone

### Comunicados Enviados
| Horário | Canal | Mensagem | Responsável |
|---------|-------|----------|-------------|
| [HH:MM] | [Canal] | [Resumo da mensagem] | [Nome] |

## Impact Assessment

### Duração Total
**Início:** [Data/Hora]
**Fim:** [Data/Hora]
**Duração:** [X horas Y minutos]

### SLA Impact
- **Availability SLA:** [99.9% target vs actual]
- **Performance SLA:** [Targets vs actual]
- **Recovery Time:** [Target vs actual]

### Métricas de Impacto
- **Requests Falhadas:** [Número]
- **Usuários Afetados:** [Número]
- **Revenue Impact:** [Valor estimado]
- **Downtime Total:** [Minutos]

## Lessons Learned

### O que Funcionou Bem
1. [Item 1]
2. [Item 2]
3. [Item 3]

### O que Pode Ser Melhorado
1. [Item 1]
2. [Item 2]
3. [Item 3]

### Surpresas ou Descobertas
1. [Item 1]
2. [Item 2]

## Action Items

| Item | Descrição | Responsável | Prazo | Status |
|------|-----------|-------------|-------|--------|
| AI-1 | [Ação 1] | [Nome] | [Data] | [Open/In Progress/Done] |
| AI-2 | [Ação 2] | [Nome] | [Data] | [Open/In Progress/Done] |
| AI-3 | [Ação 3] | [Nome] | [Data] | [Open/In Progress/Done] |

### Melhorias de Processo
- [ ] Atualizar runbook
- [ ] Melhorar monitoramento
- [ ] Adicionar alertas
- [ ] Treinar equipe
- [ ] Documentar processo

### Melhorias Técnicas
- [ ] Corrigir bugs identificados
- [ ] Melhorar logging
- [ ] Aumentar resiliência
- [ ] Otimizar performance
- [ ] Implementar circuit breakers

## Prevenção

### Medidas Preventivas Implementadas
1. [Medida 1]
2. [Medida 2]
3. [Medida 3]

### Monitoramento Adicional
- [ ] Novos alertas configurados
- [ ] Dashboards atualizados
- [ ] Métricas adicionais coletadas

### Testes de Validação
- [ ] Teste de regressão
- [ ] Teste de carga
- [ ] Teste de disaster recovery
- [ ] Teste de escalabilidade

## Assinaturas

**Incident Commander:** [Nome] - [Data]
**Technical Lead:** [Nome] - [Data]
**Operations Manager:** [Nome] - [Data]

## Anexos

### Scripts Utilizados
```bash
# Scripts de diagnóstico
./scripts/validation/validate-cluster-health.sh --debug
./scripts/maintenance/collect-diagnostic-info.sh

# Scripts de correção
[Scripts específicos utilizados]
```

### Logs Completos
[Link para logs completos ou anexar arquivo]

### Screenshots/Grafana Dashboards
[Links ou imagens de dashboards relevantes]

### Comunicação Externa
[Cópias de comunicados para clientes/usuários]

---

**Nota:** Este template deve ser preenchido durante e após cada incidente para garantir documentação completa e facilitar a melhoria contínua dos processos.

**Última Atualização:** [Data]
**Versão:** 1.0