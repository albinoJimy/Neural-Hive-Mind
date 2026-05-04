"""
gRPC Protocol Buffers para NLU e PII Services.

Este pacote contém as definições de protocolo gRPC para:
- NLUService: Processamento de linguagem natural
- PIIService: Detecção e mascaramento de informações sensíveis

Os arquivos .proto foram compilados para Python usando grpcio-tools.
"""

from . import nlu_pb2
from . import nlu_pb2_grpc
from . import pii_pb2
from . import pii_pb2_grpc

__all__ = [
    "nlu_pb2",
    "nlu_pb2_grpc",
    "pii_pb2",
    "pii_pb2_grpc",
]
