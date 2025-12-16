"""
Proto stubs for Neural Hive Integration library.

This package contains pre-compiled protobuf stubs for gRPC services,
ensuring consistent imports across all services that depend on this library.
"""

from . import service_registry_pb2
from . import service_registry_pb2_grpc

__all__ = [
    'service_registry_pb2',
    'service_registry_pb2_grpc',
]
