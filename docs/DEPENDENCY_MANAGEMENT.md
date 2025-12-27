# Gerenciamento de Dependências - Neural Hive-Mind

## Arquivo Central de Versões

O arquivo `versions.txt` na raiz do projeto contém as versões canônicas de todas as dependências compartilhadas.

### Como Usar

**Opção 1: Referência direta (recomendado)**
```txt
# requirements.txt
-r ../../versions.txt

# Dependências específicas do serviço
custom-library==1.0.0
```

**Opção 2: Copiar versões específicas**
```txt
# requirements.txt
# Core (referência: versions.txt)
fastapi==0.104.1
grpcio==1.75.1
```

## Atualização de Versões

1. Atualizar `versions.txt` primeiro
2. Testar em ambiente de desenvolvimento
3. Atualizar serviços gradualmente
4. Rebuild imagens base se necessário

## Versões Críticas

### gRPC/Protobuf
- **grpcio**: 1.75.1 (OBRIGATÓRIO)
- **protobuf**: 5.27.0 (OBRIGATÓRIO)
- Incompatibilidade causa falhas de serialização

### Kafka
- Usar **confluent-kafka** para Schema Registry
- Usar **aiokafka** apenas para async puro
- **NUNCA** usar ambos no mesmo serviço

## pyproject.toml vs requirements.txt

### Fonte de Verdade

**requirements.txt** é a fonte de verdade para dependências de produção:
- Usado pelos Dockerfiles em todos os builds
- Referencia `versions.txt` para versões canônicas
- Testado em CI/CD

### pyproject.toml

Arquivos `pyproject.toml` são mantidos para:
- Metadados do projeto (nome, versão, descrição, autores)
- Compatibilidade com ferramentas Poetry (uso local opcional)
- Dependências de desenvolvimento (dev-dependencies)

**IMPORTANTE**: pyproject.toml deve ser mantido **sincronizado** com requirements.txt, mas em caso de conflito, requirements.txt prevalece.

### Validação de Sincronização

Para verificar se pyproject.toml está sincronizado com requirements.txt:

```bash
# Verificar manualmente
diff <(grep -E "^[a-z]" services/*/requirements.txt | sort) \
     <(grep -E "^[a-z]" services/*/pyproject.toml | sort)

# Ou usar script de validação (futuro)
./scripts/validate-dependency-sync.sh
```

### Quando Atualizar

1. **Sempre atualizar requirements.txt primeiro**
2. Testar build Docker
3. Atualizar pyproject.toml para manter sincronização
4. Commit ambos os arquivos juntos
