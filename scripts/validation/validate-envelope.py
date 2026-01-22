#!/usr/bin/env python3
"""
Script para validar envelopes de intenção (JSON-LD e Avro)
Utilizado em CI/CD para garantir compatibilidade de schemas
"""

import json
import argparse
import sys
from pathlib import Path
from typing import Dict, List, Any
import jsonschema
import avro.schema
from avro.io import DatumReader, DatumWriter, BinaryEncoder, BinaryDecoder
import io
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class EnvelopeValidator:
    """Validador de envelopes de intenção"""

    def __init__(self, schema_dir: str):
        self.schema_dir = Path(schema_dir)
        self.jsonld_schema = None
        self.avro_schema = None

        self._load_schemas()

    def _load_schemas(self):
        """Carregar schemas JSON-LD e Avro"""
        # JSON-LD Schema
        jsonld_path = self.schema_dir / "intent-envelope.jsonld"
        if jsonld_path.exists():
            with open(jsonld_path, 'r', encoding='utf-8') as f:
                jsonld_data = json.load(f)
                # Extrair JSON Schema do contexto JSON-LD se disponível
                if '@context' in jsonld_data and 'properties' in jsonld_data:
                    self.jsonld_schema = jsonld_data
                else:
                    logger.warning("JSON-LD schema não contém definição JSON Schema válida")

        # Avro Schema
        avro_path = self.schema_dir / "intent-envelope.avsc"
        if avro_path.exists():
            with open(avro_path, 'r', encoding='utf-8') as f:
                avro_data = json.load(f)
                self.avro_schema = avro.schema.parse(json.dumps(avro_data))
        else:
            raise FileNotFoundError(f"Avro schema não encontrado em {avro_path}")

    def validate_json_structure(self, data: Dict[str, Any]) -> List[str]:
        """Validar estrutura básica do JSON"""
        errors = []

        # Campos obrigatórios básicos
        required_fields = ['id', 'actor', 'intent', 'confidence', 'timestamp']

        for field in required_fields:
            if field not in data:
                errors.append(f"Campo obrigatório ausente: {field}")

        # Validar tipos básicos
        if 'id' in data and not isinstance(data['id'], str):
            errors.append("Campo 'id' deve ser string")

        if 'confidence' in data:
            if not isinstance(data['confidence'], (int, float)):
                errors.append("Campo 'confidence' deve ser número")
            elif not (0.0 <= data['confidence'] <= 1.0):
                errors.append("Campo 'confidence' deve estar entre 0.0 e 1.0")

        if 'timestamp' in data and not isinstance(data['timestamp'], (str, int)):
            errors.append("Campo 'timestamp' deve ser string (ISO) ou número (Unix)")

        # Validar estrutura do actor
        if 'actor' in data:
            if not isinstance(data['actor'], dict):
                errors.append("Campo 'actor' deve ser objeto")
            else:
                actor = data['actor']
                if 'id' not in actor:
                    errors.append("Campo 'actor.id' é obrigatório")
                if 'actor_type' not in actor and 'actorType' not in actor:
                    errors.append("Campo 'actor.actor_type' ou 'actor.actorType' é obrigatório")

        # Validar estrutura da intent
        if 'intent' in data:
            if not isinstance(data['intent'], dict):
                errors.append("Campo 'intent' deve ser objeto")
            else:
                intent = data['intent']
                if 'text' not in intent:
                    errors.append("Campo 'intent.text' é obrigatório")
                if 'domain' not in intent:
                    errors.append("Campo 'intent.domain' é obrigatório")

                # Validar domínios válidos (7 domínios unificados)
                if 'domain' in intent:
                    valid_domains = [
                        'BUSINESS', 'TECHNICAL', 'SECURITY', 'INFRASTRUCTURE',
                        'BEHAVIOR', 'OPERATIONAL', 'COMPLIANCE',
                        'business', 'technical', 'security', 'infrastructure',
                        'behavior', 'operational', 'compliance'
                    ]
                    if intent['domain'] not in valid_domains:
                        errors.append(f"Domínio inválido: {intent['domain']}. Domínios válidos: BUSINESS, TECHNICAL, SECURITY, INFRASTRUCTURE, BEHAVIOR, OPERATIONAL, COMPLIANCE")

        return errors

    def validate_jsonld(self, data: Dict[str, Any]) -> List[str]:
        """Validar contra schema JSON-LD"""
        errors = []

        if not self.jsonld_schema:
            logger.warning("Schema JSON-LD não disponível, pulando validação")
            return errors

        try:
            jsonschema.validate(data, self.jsonld_schema)
            logger.info("✅ Validação JSON-LD passou")
        except jsonschema.ValidationError as e:
            errors.append(f"Erro de validação JSON-LD: {e.message}")
        except jsonschema.SchemaError as e:
            errors.append(f"Erro no schema JSON-LD: {e.message}")

        return errors

    def validate_avro(self, data: Dict[str, Any]) -> List[str]:
        """Validar contra schema Avro"""
        errors = []

        if not self.avro_schema:
            errors.append("Schema Avro não carregado")
            return errors

        try:
            # Converter dados para formato compatível com Avro
            avro_data = self._convert_to_avro_format(data)

            # Tentar serializar com Avro
            writer = DatumWriter(self.avro_schema)
            bytes_writer = io.BytesIO()
            encoder = BinaryEncoder(bytes_writer)

            writer.write(avro_data, encoder)

            # Tentar deserializar para verificar integridade
            bytes_reader = io.BytesIO(bytes_writer.getvalue())
            decoder = BinaryDecoder(bytes_reader)
            reader = DatumReader(self.avro_schema)

            deserialized = reader.read(decoder)

            logger.info("✅ Validação Avro passou")

        except Exception as e:
            errors.append(f"Erro de validação Avro: {str(e)}")

        return errors

    def _convert_to_avro_format(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Converter dados para formato compatível com Avro"""
        converted = data.copy()

        # Converter campos específicos
        if 'correlation_id' in converted:
            converted['correlationId'] = converted.pop('correlation_id')

        if 'trace_id' in converted:
            converted['traceId'] = converted.pop('trace_id')

        if 'span_id' in converted:
            converted['spanId'] = converted.pop('span_id')

        # Converter actor
        if 'actor' in converted and isinstance(converted['actor'], dict):
            actor = converted['actor']
            if 'actor_type' in actor:
                # Converter para formato enum esperado pelo Avro
                actor_type_map = {
                    'human': 'HUMAN',
                    'system': 'SYSTEM',
                    'service': 'SERVICE',
                    'bot': 'BOT'
                }
                actor_type = actor.pop('actor_type')
                actor['actorType'] = actor_type_map.get(actor_type.lower(), actor_type.upper())

        # Converter intent
        if 'intent' in converted and isinstance(converted['intent'], dict):
            intent = converted['intent']

            # Converter domain para formato enum (7 domínios unificados)
            if 'domain' in intent:
                domain_map = {
                    'business': 'BUSINESS',
                    'technical': 'TECHNICAL',
                    'infrastructure': 'INFRASTRUCTURE',
                    'security': 'SECURITY',
                    'behavior': 'BEHAVIOR',
                    'operational': 'OPERATIONAL',
                    'compliance': 'COMPLIANCE'
                }
                domain = intent['domain']
                intent['domain'] = domain_map.get(domain.lower(), domain.upper())

            # Converter originalLanguage
            if 'original_language' in intent:
                intent['originalLanguage'] = intent.pop('original_language')

            # Converter processedText
            if 'processed_text' in intent:
                intent['processedText'] = intent.pop('processed_text')

            # Garantir que entities é uma lista
            if 'entities' not in intent:
                intent['entities'] = []
            elif not isinstance(intent['entities'], list):
                intent['entities'] = []

            # Converter entidades
            for entity in intent['entities']:
                if isinstance(entity, dict):
                    if 'entity_type' in entity:
                        entity['entityType'] = entity.pop('entity_type')

        # Converter timestamp
        if 'timestamp' in converted:
            timestamp = converted['timestamp']
            if isinstance(timestamp, str):
                # Tentar converter ISO string para timestamp Unix em ms
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    converted['timestamp'] = int(dt.timestamp() * 1000)
                except:
                    # Se falhar, usar timestamp atual
                    import time
                    converted['timestamp'] = int(time.time() * 1000)
            elif isinstance(timestamp, (int, float)):
                # Se já é timestamp, garantir que está em ms
                if timestamp < 1e12:  # Probably seconds
                    converted['timestamp'] = int(timestamp * 1000)
                else:
                    converted['timestamp'] = int(timestamp)

        # Garantir campos opcionais com valores padrão
        if 'version' not in converted:
            converted['version'] = '1.0.0'

        if 'schemaVersion' not in converted:
            converted['schemaVersion'] = 1

        if 'metadata' not in converted:
            converted['metadata'] = {}

        return converted

    def validate_envelope(self, envelope_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validar envelope completo"""
        result = {
            'valid': True,
            'errors': [],
            'warnings': []
        }

        # Validação estrutural básica
        struct_errors = self.validate_json_structure(envelope_data)
        result['errors'].extend(struct_errors)

        # Validação JSON-LD
        if self.jsonld_schema:
            jsonld_errors = self.validate_jsonld(envelope_data)
            result['errors'].extend(jsonld_errors)
        else:
            result['warnings'].append("Schema JSON-LD não disponível")

        # Validação Avro
        avro_errors = self.validate_avro(envelope_data)
        result['errors'].extend(avro_errors)

        # Determinar se é válido
        result['valid'] = len(result['errors']) == 0

        return result

    def validate_file(self, file_path: str) -> Dict[str, Any]:
        """Validar arquivo de envelope"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            return self.validate_envelope(data)

        except json.JSONDecodeError as e:
            return {
                'valid': False,
                'errors': [f"Erro ao parsear JSON: {str(e)}"],
                'warnings': []
            }
        except Exception as e:
            return {
                'valid': False,
                'errors': [f"Erro ao ler arquivo: {str(e)}"],
                'warnings': []
            }


def create_sample_envelope() -> Dict[str, Any]:
    """Criar envelope de exemplo para teste"""
    from datetime import datetime
    import uuid

    return {
        "id": str(uuid.uuid4()),
        "version": "1.0.0",
        "correlationId": str(uuid.uuid4()),
        "actor": {
            "id": "user-123",
            "actorType": "human",
            "name": "Test User"
        },
        "intent": {
            "text": "Implementar sistema de autenticação OAuth2",
            "domain": "technical",
            "classification": "implementation",
            "originalLanguage": "pt-BR",
            "processedText": "implementar sistema autenticação oauth2",
            "entities": [
                {
                    "entityType": "TECHNOLOGY",
                    "value": "OAuth2",
                    "confidence": 0.95,
                    "start": 35,
                    "end": 41
                }
            ],
            "keywords": ["implementar", "sistema", "autenticação", "oauth2"]
        },
        "confidence": 0.87,
        "context": {
            "userId": "user-123",
            "sessionId": "session-456",
            "tenantId": "tenant-789"
        },
        "timestamp": int(datetime.utcnow().timestamp() * 1000),
        "schemaVersion": 1,
        "metadata": {
            "source": "validation-test",
            "environment": "test"
        }
    }


def main():
    parser = argparse.ArgumentParser(description='Validate Intent Envelope')
    parser.add_argument('--schema-dir', required=True, help='Directory containing schema files')
    parser.add_argument('--file', help='Envelope file to validate')
    parser.add_argument('--create-sample', action='store_true', help='Create sample envelope for testing')
    parser.add_argument('--output', help='Output file for sample envelope')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose logging')

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Criar envelope de exemplo se solicitado
    if args.create_sample:
        sample = create_sample_envelope()

        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(sample, f, indent=2, ensure_ascii=False)
            print(f"Sample envelope created: {args.output}")
        else:
            print(json.dumps(sample, indent=2, ensure_ascii=False))
        return

    # Validar arquivo
    if not args.file:
        parser.error("Either --file or --create-sample is required")

    try:
        validator = EnvelopeValidator(args.schema_dir)
        result = validator.validate_file(args.file)

        print(f"\n=== ENVELOPE VALIDATION RESULTS ===")
        print(f"File: {args.file}")
        print(f"Valid: {'✅ PASS' if result['valid'] else '❌ FAIL'}")

        if result['warnings']:
            print(f"\nWarnings ({len(result['warnings'])}):")
            for warning in result['warnings']:
                print(f"  ⚠️  {warning}")

        if result['errors']:
            print(f"\nErrors ({len(result['errors'])}):")
            for error in result['errors']:
                print(f"  ❌ {error}")

        print("="*40)

        # Exit with error code if validation failed
        sys.exit(0 if result['valid'] else 1)

    except Exception as e:
        logger.error(f"Validation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()