"""Avro serialization/deserialization para mensagens Kafka."""
import io
import json
import os
from pathlib import Path
from typing import Dict, Optional

import structlog

logger = structlog.get_logger()

# Importação condicional de avro (graceful degradation para JSON)
try:
    import avro.io
    import avro.schema
    AVRO_AVAILABLE = True
except ImportError:
    AVRO_AVAILABLE = False
    logger.warning("avro_not_available_using_json_fallback")


class AvroCodec:
    """Codec para serializar/desserializar mensagens Avro com fallback JSON."""

    def __init__(self, schema_registry_path: Optional[str] = None):
        """
        Inicializa codec Avro.

        Args:
            schema_registry_path: Caminho para diretório de schemas (opcional)
        """
        # Calcular caminho para schemas - prioriza variável de ambiente
        if schema_registry_path is None:
            schema_registry_path = os.environ.get('SCHEMAS_DIR')
            if schema_registry_path is None:
                # Fallback: tentar caminhos relativos conhecidos
                try:
                    # Em desenvolvimento (5 níveis acima de src/serialization/avro_codec.py)
                    repo_root = Path(__file__).resolve().parents[4]
                    schema_registry_path = str(repo_root / "schemas")
                    if not Path(schema_registry_path).exists():
                        raise IndexError("Schemas not at repo root")
                except (IndexError, ValueError):
                    # Em container (/app/src/serialization/avro_codec.py) ou se falhar acima
                    if Path("/app/schemas").exists():
                        schema_registry_path = "/app/schemas"
                    else:
                        # Fallback final: assumir schemas no mesmo nível do app
                        schema_registry_path = str(Path(__file__).resolve().parents[2] / "schemas")

        self.schema_registry_path = Path(schema_registry_path)
        self.schemas: Dict[str, any] = {}
        self.avro_enabled = AVRO_AVAILABLE

        if self.avro_enabled:
            self._load_schemas()
        else:
            logger.info("avro_codec_using_json_mode")

    def _load_schemas(self):
        """Carrega schemas Avro do diretório."""
        if not AVRO_AVAILABLE:
            return

        try:
            # Schema de request
            request_schema_path = self.schema_registry_path / "mcp-tool-selection-request" / "mcp-tool-selection-request.avsc"
            if request_schema_path.exists():
                with open(request_schema_path, 'r') as f:
                    self.schemas['request'] = avro.schema.parse(f.read())
                    logger.info("avro_request_schema_loaded", path=str(request_schema_path.absolute()))
            else:
                logger.warning("avro_request_schema_not_found", expected_path=str(request_schema_path.absolute()))

            # Schema de response
            response_schema_path = self.schema_registry_path / "mcp-tool-selection-response" / "mcp-tool-selection-response.avsc"
            if response_schema_path.exists():
                with open(response_schema_path, 'r') as f:
                    self.schemas['response'] = avro.schema.parse(f.read())
                    logger.info("avro_response_schema_loaded", path=str(response_schema_path.absolute()))
            else:
                logger.warning("avro_response_schema_not_found", expected_path=str(response_schema_path.absolute()))

            # Se nenhum schema foi carregado, desabilitar Avro
            if not self.schemas:
                logger.warning("no_avro_schemas_loaded_falling_back_to_json")
                self.avro_enabled = False

        except Exception as e:
            logger.warning("avro_schema_loading_failed_using_json", error=str(e))
            self.avro_enabled = False

    def serialize(self, record: Dict, schema_type: str) -> bytes:
        """
        Serializa record para bytes Avro ou JSON.

        Args:
            record: Dicionário com dados
            schema_type: 'request' ou 'response'

        Returns:
            Bytes serializados
        """
        if not self.avro_enabled or schema_type not in self.schemas:
            # Fallback para JSON
            return json.dumps(record).encode('utf-8')

        try:
            # Serializar com Avro
            schema = self.schemas[schema_type]
            writer = avro.io.DatumWriter(schema)
            bytes_writer = io.BytesIO()
            encoder = avro.io.BinaryEncoder(bytes_writer)
            writer.write(record, encoder)

            return bytes_writer.getvalue()

        except Exception as e:
            logger.error("avro_serialization_failed_using_json", error=str(e), schema_type=schema_type)
            # Fallback para JSON
            return json.dumps(record).encode('utf-8')

    def deserialize(self, data: bytes, schema_type: str) -> Optional[Dict]:
        """
        Desserializa bytes Avro ou JSON para dict.

        Args:
            data: Bytes serializados
            schema_type: 'request' ou 'response'

        Returns:
            Dicionário desserializado ou None se falhar
        """
        # Tentar JSON primeiro (compatibilidade)
        try:
            return json.loads(data.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass

        # Tentar Avro se disponível
        if self.avro_enabled and schema_type in self.schemas:
            try:
                schema = self.schemas[schema_type]
                bytes_reader = io.BytesIO(data)
                decoder = avro.io.BinaryDecoder(bytes_reader)
                reader = avro.io.DatumReader(schema)
                return reader.read(decoder)
            except Exception as e:
                logger.error("avro_deserialization_failed", error=str(e), schema_type=schema_type)

        logger.error("deserialization_failed_all_formats", schema_type=schema_type)
        return None
