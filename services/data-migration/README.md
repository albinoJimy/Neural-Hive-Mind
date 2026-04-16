# Data Migration Service

Serviço de migração de dados para o Neural Hive-Mind Fluxo H.

## Descrição

Este serviço é responsável por:
- Schema mapping usando LLM (legado → moderno)
- Batch migration de dados históricos
- CDC pipeline usando Debezium
- Data validation usando Great Expectations
- Rollback manager

## Porta

8019

## Stack

- Python 3.12+
- FastAPI
- PostgreSQL (Legacy Database)
- MongoDB (Metadata)
- Redis
- Kafka
- OpenAI/Anthropic (LLM)
- Great Expectations (Data Validation)
