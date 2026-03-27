# Spec Tasks — P04 Operacional

## Tasks

- [ ] 1. Limpeza de arquivos órfãos
  - [ ] 1.1 Identificar arquivos órfãos (crane, =0.*, etc)
  - [ ] 1.2 Remover binário crane (10MB)
  - [ ] 1.3 Remover arquivos =0.42b0, =0.45.0, =5.27.0
  - [ ] 1.4 Verificar que não há mais arquivos inválidos

- [ ] 2. Arquivamento de documentação histórica
  - [ ] 2.1 Criar diretório docs/archive/
  - [ ] 2.2 Mover relatórios históricos para archive/
  - [ ] 2.3 Criar index.md com lista de arquivos
  - [ ] 2.4 Manter apenas docs recentes em docs/

- [ ] 3. Pinning de dependências
  - [ ] 3.1 Analisar todos os requirements.txt
  - [ ] 3.2 Converter ranges (>=) para versões exatas
  - [ ] 3.3 Criar requirements.frozen para cada serviço
  - [ ] 3.4 Adicionar script de update de dependências

- [ ] 4. Multi-stage build Gateway
  - [ ] 4.1 Analisar Dockerfile atual do gateway
  - [ ] 4.2 Criar Dockerfile.multi-stage
  - [ ] 4.3 Separar build stage e runtime stage
  - [ ] 4.4 Remover ferramentas de build do runtime
  - [ ] 4.5 Validar que image size reduziu

- [ ] 5. CI/CD validation
  - [ ] 5.1 Adicionar check de arquivos órfãos no CI
  - [ ] 5.2 Adicionar check de dependências no CI
  - [ ] 5.3 Adicionar Docker image scan no CI
  - [ ] 5.4 Validar que CI passa

- [ ] 6. Documentação
  - [ ] 6.1 Atualizar README com estrutura de diretórios
  - [ ] 6.2 Documentar processo de update de deps
  - [ ] 6.3 Documentar multi-stage build
  - [ ] 6.4 Commit e push

- [ ] 7. Verificação final
  - [ ] 7.1 Verificar que zero arquivos órfãos
  - [ ] 7.2 Verificar que docs está organizado
  - [ ] 7.3 Verificar que requirements estão pinned
  - [ ] 7.4 Verificar que Docker image é menor
