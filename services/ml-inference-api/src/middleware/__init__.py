"""
Middleware para suporte a content-type Avro na API.
"""
from .avro_middleware import AvroContentTypeMiddleware

__all__ = ["AvroContentTypeMiddleware"]
