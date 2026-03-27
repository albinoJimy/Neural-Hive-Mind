# Multi-Stage Docker Build - Gateway de Intenções

## Overview

O `Dockerfile.multi-stage` é uma versão otimizada do Dockerfile original que usa o padrão multi-stage build para reduzir o tamanho final da imagem Docker.

## Arquitetura

### Builder Stage
- **Propósito**: Compilar dependências que precisam de gcc/g++
- **Ferramentas incluídas**: gcc, g++, libasound2-dev, portaudio19-dev, ffmpeg, git, curl
- **Resultado**: Site-packages Python com todas as dependências instaladas

### Runtime Stage
- **Propósito**: Imagem mínima para executar a aplicação
- **Apenas runtime**: ffmpeg, curl, ca-certificates (sem gcc, g++, headers de dev)
- **Resultado**: Imagem significativamente menor

## Diferenças para Dockerfile Original

| Aspecto | Dockerfile | Dockerfile.multi-stage |
|---------|-----------|------------------------|
| Tamanho estimado | ~1.2 GB | ~850 MB |
| Build time | ~5 min | ~5 min |
| Ferramentas de build | Incluídas na final | Removidas na final |
| Segurança | Mais superfície de ataque | Menos ferramentas = mais seguro |

## Como Usar

### Build com multi-stage:
```bash
docker build -f services/gateway-intencoes/Dockerfile.multi-stage -t ghcr.io/albinojimy/neural-hive-mind/gateway-intencoes:multi-stage .
```

### Build com Dockerfile original:
```bash
docker build -f services/gateway-intencoes/Dockerfile -t ghcr.io/albinojimy/neural-hive-mind/gateway-intencoes:latest .
```

## Comparação de Tamanhos

Após build, compare os tamanhos:

```bash
docker images | grep gateway-intencoes
```

Esperado:
- `latest`: ~1.2 GB
- `multi-stage`: ~850 MB (redução de ~30%)

## Vantagens

1. **Menor tamanho da imagem**: ~30% de redução
2. **Menor superfície de ataque**: Sem gcc/g++ na imagem final
3. **Builds mais rápidos no CI**: Cache do builder stage é reutilizável
4. **Mesma funcionalidade**: Comportamento idêntico ao original

## Migração

Para migrar para o multi-stage build:

1. Atualizar scripts de deploy para usar `Dockerfile.multi-stage`
2. Atualizar helm charts para referenciar a nova tag
3. Validar funcionamento em ambiente de staging

## Notas

- O Dockerfile original continua disponível como fallback
- Ambas as versões produzem imagens funcionalmente idênticas
- A escolha entre elas depende de prioridades (tamanho vs compatibilidade)
