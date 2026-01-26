# Protocol Buffers Setup

Este documento explica como compilar os arquivos `.proto` para gerar o código Python do gRPC server.

## Pré-requisitos

```bash
pip install grpcio-tools
```

## Compilação

### Opção 1: Usando Makefile (Recomendado)

```bash
make proto
```

### Opção 2: Manual

```bash
python -m grpc_tools.protoc \
  -I./protos \
  --python_out=./src/proto_gen \
  --grpc_python_out=./src/proto_gen \
  --pyi_out=./src/proto_gen \
  ./protos/ticket_service.proto
```

## Arquivos Gerados

Após compilação, serão criados em `src/proto_gen/`:

- `ticket_service_pb2.py` - Mensagens Protocol Buffers
- `ticket_service_pb2_grpc.py` - Stubs gRPC (client e server)
- `ticket_service_pb2.pyi` - Type hints para Python

## Habilitando gRPC Server

Após compilar os protos, descomente o código em:

1. **`src/grpc_service/ticket_servicer.py`**:
   - Descomentar imports: `import grpc`, `ticket_service_pb2`, `ticket_service_pb2_grpc`
   - Descomentar herança: `class TicketServiceServicer(ticket_service_pb2_grpc.TicketServiceServicer)`
   - Descomentar implementação `_pydantic_to_proto()`

2. **`src/grpc_service/server.py`**:
   - Descomentar imports
   - Descomentar código de `start_grpc_server()`
   - Remover `return None` e log de warning

3. **Reiniciar o serviço** para ativar gRPC server na porta 50052

## Testando gRPC

### Usando grpcurl

```bash
# Listar serviços
grpcurl -plaintext localhost:50052 list

# Listar métodos
grpcurl -plaintext localhost:50052 list ticket_service.TicketService

# Chamar GetTicket
grpcurl -plaintext -d '{"ticket_id": "test-123"}' localhost:50052 ticket_service.TicketService/GetTicket
```

### Usando Python Client

```python
import grpc
from src.grpc_service import ticket_service_pb2, ticket_service_pb2_grpc

channel = grpc.insecure_channel('localhost:50052')
stub = ticket_service_pb2_grpc.TicketServiceStub(channel)

request = ticket_service_pb2.GetTicketRequest(ticket_id='test-123')
response = stub.GetTicket(request)
print(response)
```

## Troubleshooting

### Erro: "No module named 'grpc_tools'"

```bash
pip install grpcio-tools
```

### Erro: Import não funciona

Verifique que os arquivos `*_pb2.py` foram gerados em `src/grpc_service/` e que o `__init__.py` está correto.

### gRPC server não inicia

Verifique logs do serviço. Se aparecer mensagem "gRPC server not started - proto compilation required", compile os protos conforme instruções acima.

## Atualizando Proto

Sempre que modificar `protos/ticket_service.proto`:

1. Recompilar: `make proto`
2. Verificar código gerado
3. Atualizar `ticket_servicer.py` se necessário
4. Rebuild imagem Docker
5. Redeploy serviço

## Integração CI/CD

No CI/CD pipeline, adicionar step de compilação:

```yaml
- name: Compile protos
  run: |
    pip install grpcio-tools
    make proto
```
