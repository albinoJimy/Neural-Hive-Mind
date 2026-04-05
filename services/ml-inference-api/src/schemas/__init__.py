"""
Schemas Avro para serialização de mensagens do ML Inference API.
"""
from .avro_schemas import (
    BATCH_INFERENCE_REQUEST_AVRO_SCHEMA,
    BATCH_INFERENCE_RESPONSE_AVRO_SCHEMA,
    INFERENCE_REQUEST_AVRO_SCHEMA,
    INFERENCE_RESPONSE_AVRO_SCHEMA,
    AvroSchemaRegistry,
    avro_to_pydantic,
    avro_to_pydantic_response,
    batch_avro_to_pydantic_response,
    batch_pydantic_to_avro,
    create_inference_request,
    create_inference_response,
    get_schema_registry,
    pydantic_response_to_avro,
    pydantic_to_avro,
)

__all__ = [
    "INFERENCE_REQUEST_AVRO_SCHEMA",
    "INFERENCE_RESPONSE_AVRO_SCHEMA",
    "BATCH_INFERENCE_REQUEST_AVRO_SCHEMA",
    "BATCH_INFERENCE_RESPONSE_AVRO_SCHEMA",
    "AvroSchemaRegistry",
    "pydantic_to_avro",
    "avro_to_pydantic",
    "pydantic_response_to_avro",
    "avro_to_pydantic_response",
    "batch_pydantic_to_avro",
    "batch_avro_to_pydantic_response",
    "create_inference_request",
    "create_inference_response",
    "get_schema_registry",
]
