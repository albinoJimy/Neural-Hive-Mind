# Checklist de Build de Serviços - Neural Hive-Mind

- **Data de início:** _____________
- **Responsável:** _____________
- **Ambiente:** Kubeadm local (1 master + 2 workers)

## Seção 1: Pré-requisitos
- [ ] Docker instalado e daemon em execução
- [ ] kubectl configurado e conectado ao cluster
- [ ] Espaço em disco ≥ 20GB disponível em `/var/lib/docker`
- [ ] Ferramentas auxiliares instaladas (`yq`, `jq`, `ctr`)
- [ ] Permissões sudo confirmadas para `ctr`/`docker`
- [ ] Arquivo `environments/local/services-build-config.yaml` revisado

## Seção 2: Preparação do Ambiente
- [ ] `docs/manual-deployment/scripts/05-prepare-services-build.sh` executado
- [ ] Variáveis de ambiente exportadas (`echo $VERSION`)
- [ ] Diretórios criados (`logs/`, `/tmp/neural-hive-images/`, `.tmp/services-build/`)
- [ ] Ordem de build gerada (`.tmp/services-build/build-order.txt`)
- [ ] Dockerfiles validados (paths existentes e sintaxe mínima)

## Seção 3: Build de Imagens Base
- [ ] `python-ml-base:1.0.0` construída (~200MB)
- [ ] `python-grpc-base:1.0.0` construída (~280MB)
- [ ] `python-nlp-base:1.0.0` construída (~550MB)
- [ ] Todas as bases também taggeadas como `latest`
- [ ] Modelos spaCy testados (`pt_core_news_sm`, `en_core_web_sm`)

## Seção 4: Build de Serviços de Aplicação
- [ ] `gateway-intencoes:1.0.0` construído (~1.2GB)
- [ ] `semantic-translation-engine:1.0.0` construído (~800MB)
- [ ] `specialist-business:1.0.0` construído (~800MB)
- [ ] `specialist-technical:1.0.0` construído (~800MB)
- [ ] `specialist-behavior:1.0.0` construído (~800MB)
- [ ] `specialist-evolution:1.0.0` construído (~800MB)
- [ ] `specialist-architecture:1.0.0` construído (~800MB)
- [ ] `consensus-engine:1.0.0` construído (~600MB)
- [ ] `orchestrator-dynamic:1.0.0` construído (~600MB)
- [ ] Todas as imagens taggeadas como `latest`

## Seção 5: Validação Local
- [ ] Script `docs/manual-deployment/scripts/06-validate-services-build.sh` executado
- [ ] `docker images | grep neural-hive-mind` lista 12 imagens
- [ ] Labels OCI verificados (version, component, layer)
- [ ] Health checks locais realizados (9/9 serviços)
- [ ] Logs de build revisados (sem erros críticos)
- [ ] Relatório gerado em `logs/services-build-validation-report.txt`

## Seção 6: Exportação para Containerd
- [ ] Diretório `/tmp/neural-hive-images/` preparado
- [ ] 12 imagens exportadas para `.tar`
- [ ] Checksums SHA256 calculados e armazenados
- [ ] Tamanho total dos tars (~8GB) confirmado
- [ ] Espaço nos nós do cluster validado

## Seção 7: Importação no Cluster Kubeadm
- [ ] Tarballs copiados para o nó master
- [ ] Tarballs copiados para o worker 1
- [ ] Tarballs copiados para o worker 2
- [ ] `sudo ctr -n k8s.io images import` executado no master
- [ ] Importação executada no worker 1
- [ ] Importação executada no worker 2
- [ ] `sudo ctr -n k8s.io images ls | grep neural-hive-mind` retorna 12 imagens em cada nó

## Seção 8: Configuração dos Helm Charts
- [ ] `values-local.yaml` do gateway-intencoes com `imagePullPolicy: Never`
- [ ] `values-local.yaml` do semantic-translation-engine atualizado
- [ ] `values-local.yaml` dos 5 specialists atualizados
- [ ] `values-local.yaml` do consensus-engine atualizado
- [ ] `values-local.yaml` do orchestrator-dynamic atualizado
- [ ] Repositórios `neural-hive-mind/<service>` e `tag: "1.0.0"` revisados

## Seção 9: Validação Final
- [ ] `06-validate-services-build.sh --check-containerd` executado
- [ ] Todas as imagens disponíveis em todos os nós
- [ ] Espaço em disco restante > 5GB
- [ ] Guia `04-services-build-manual-guide.md` seguido integralmente
- [ ] Logs finais arquivados (build, validação, importação)

## Seção 10: Próximos Passos
- [ ] Revisar `docs/manual-deployment/05-gateway-deployment-manual-guide.md` (Fluxo A)
- [ ] Preparar integrações com Kafka/Redis (configmaps e secrets)
- [ ] Planejar deploy do gateway-intencoes usando imagens locais

---

### Notas e Observações
- Problemas encontrados e soluções: ______________________________________
- Tempo total gasto: __________________
- Data de conclusão: __________________

### Referências Rápidas
```bash
# Listar imagens locais
docker images | grep neural-hive-mind

# Verificar imagens no containerd
sudo ctr -n k8s.io images ls | grep neural-hive-mind

# Limpar cache do Docker
docker system prune -af

# Verificar espaço em disco
df -h /var/lib/docker

# Logs de build
ls -lh logs/build-*.log
```
