# Spec Tasks — P01 Segurança Crítica

## Tasks

- [ ] 1. Modificar `auth.py` para usar JWT_SECRET do settings
  - [ ] 1.1 Escrever teste para validação de JWT com env var
  - [ ] 1.2 Remover hardcoded "secret" de jwt.decode()
  - [ ] 1.3 Usar settings.jwt_secret_key
  - [ ] 1.4 Verificar que testes passam

- [ ] 2. Modificar `settings.py` para validar configurações
  - [ ] 2.1 Escrever teste para SettingsError se vars faltam
  - [ ] 2.2 Mudar jwt_secret_key para required Field
  - [ ] 2.3 Mudar allowed_origins para required Field
  - [ ] 2.4 Adicionar validator para parsear CORS_ORIGINS string
  - [ ] 2.5 Verificar que testes passam

- [ ] 3. Implementar startup validation
  - [ ] 3.1 Escrever teste para startup com vars faltando
  - [ ] 3.2 Adicionar validação no __init__ do FastAPI app
  - [ ] 3.3 Garantir erro claro se vars faltam
  - [ ] 3.4 Verificar que testes passam

- [ ] 4. Criar .env.example
  - [ ] 4.1 Criar arquivo .env.example no gateway-intencoes
  - [ ] 4.2 Adicionar JWT_SECRET_KEY com placeholder
  - [ ] 4.3 Adicionar CORS_ORIGINS com exemplo
  - [ ] 4.4 Adicionar comentários explicativos

- [ ] 5. Atualizar README
  - [ ] 5.1 Adicionar seção de configuração de segurança
  - [ ] 5.2 Documentar variáveis obrigatórias
  - [ ] 5.3 Adicionar instruções de .env setup

- [ ] 6. Verificação final
  - [ ] 6.1 Rodar todos os testes do gateway
  - [ ] 6.2 Verificar que zero credenciais hardcoded
  - [ ] 6.3 Verificar que CORS está configurado
  - [ ] 6.4 Commit e push
