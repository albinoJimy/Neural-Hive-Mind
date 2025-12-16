#!/usr/bin/env python3
"""
Script para popular Neo4j com intents históricos do MongoDB.

Este script:
1. Conecta ao MongoDB (cognitive_ledger collection)
2. Busca documentos de planos cognitivos com informações de intents
3. Conecta ao Neo4j
4. Cria Intent nodes com MERGE (idempotente)
5. Cria índices para queries eficientes
6. Valida o seed

Uso:
    # Simulação (dry-run)
    python scripts/seed_neo4j_intents.py \
        --mongodb-uri mongodb://localhost:27017 \
        --neo4j-uri bolt://localhost:7687 \
        --neo4j-password password \
        --dry-run

    # Execução real
    python scripts/seed_neo4j_intents.py \
        --mongodb-uri mongodb://localhost:27017 \
        --neo4j-uri bolt://localhost:7687 \
        --neo4j-password password

    # Com limite para teste
    python scripts/seed_neo4j_intents.py \
        --mongodb-uri mongodb://localhost:27017 \
        --neo4j-uri bolt://localhost:7687 \
        --neo4j-password password \
        --limit 100
"""

import argparse
import sys
import time
import asyncio
from typing import Dict, List, Any
from pymongo import MongoClient
from neo4j import AsyncGraphDatabase
import structlog

logger = structlog.get_logger()


def parse_args():
    """Parse argumentos da linha de comando."""
    parser = argparse.ArgumentParser(
        description="Popular Neo4j com intents históricos do MongoDB"
    )
    parser.add_argument(
        "--mongodb-uri",
        required=True,
        help="URI do MongoDB (ex: mongodb://localhost:27017)"
    )
    parser.add_argument(
        "--mongodb-database",
        default="neural_hive",
        help="Nome do database MongoDB (default: neural_hive)"
    )
    parser.add_argument(
        "--mongodb-collection",
        default="cognitive_ledger",
        help="Nome da collection MongoDB (default: cognitive_ledger)"
    )
    parser.add_argument(
        "--neo4j-uri",
        required=True,
        help="URI do Neo4j (ex: bolt://localhost:7687)"
    )
    parser.add_argument(
        "--neo4j-user",
        default="neo4j",
        help="Usuário Neo4j (default: neo4j)"
    )
    parser.add_argument(
        "--neo4j-password",
        required=True,
        help="Senha do Neo4j"
    )
    parser.add_argument(
        "--neo4j-database",
        default="neo4j",
        help="Nome do database Neo4j (default: neo4j)"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Tamanho do batch para inserts (default: 100)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limitar número de intents a processar (opcional)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simular sem modificar Neo4j"
    )
    return parser.parse_args()


def connect_mongodb(uri: str, database: str, collection: str):
    """
    Conecta ao MongoDB e retorna collection.

    Args:
        uri: URI do MongoDB
        database: Nome do database
        collection: Nome da collection

    Returns:
        Collection do MongoDB
    """
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        # Testar conexão
        client.server_info()
        db = client[database]
        coll = db[collection]

        logger.info(
            "Conectado ao MongoDB",
            database=database,
            collection=collection
        )

        return coll

    except Exception as e:
        logger.error(
            "Falha ao conectar ao MongoDB",
            uri=uri,
            error=str(e)
        )
        sys.exit(1)


async def connect_neo4j(uri: str, user: str, password: str):
    """
    Conecta ao Neo4j e retorna driver.

    Args:
        uri: URI do Neo4j
        user: Usuário
        password: Senha

    Returns:
        Driver do Neo4j
    """
    try:
        driver = AsyncGraphDatabase.driver(
            uri,
            auth=(user, password),
            connection_timeout=30
        )

        # Verificar conectividade
        await driver.verify_connectivity()

        logger.info(
            "Conectado ao Neo4j",
            uri=uri
        )

        return driver

    except Exception as e:
        logger.error(
            "Falha ao conectar ao Neo4j",
            uri=uri,
            error=str(e)
        )
        sys.exit(1)


def extract_keywords(text: str) -> str:
    """
    Extrai keywords de texto para busca.

    Replica a lógica de Neo4jClient._extract_keywords().

    Args:
        text: Texto de entrada

    Returns:
        Keywords separados por espaço
    """
    if not text:
        return ''

    words = text.lower().split()

    # Filtrar stop words comuns
    stop_words = {'o', 'a', 'de', 'para', 'com', 'em', 'um', 'uma'}
    keywords = [w for w in words if w not in stop_words and len(w) > 2]

    return ' '.join(keywords[:5])  # Top 5 keywords


def fetch_intents_from_mongodb(
    collection,
    limit: int = None
) -> List[Dict[str, Any]]:
    """
    Busca intents do MongoDB cognitive_ledger.

    Args:
        collection: Collection do MongoDB
        limit: Número máximo de documentos

    Returns:
        Lista de intents normalizados
    """
    try:
        # Query para buscar planos com informações de intent
        query = {}
        projection = {
            'intent_id': 1,
            'plan_data.original_domain': 1,
            'plan_data.metadata.original_confidence': 1,
            'plan_data.metadata.original_intent_text': 1,
            'plan_data.original_intent_text': 1,
            'plan_data.intent_text': 1,
            'plan_data.created_at': 1,
            'plan_id': 1,
            'created_at': 1,
            'timestamp': 1
        }

        cursor = collection.find(query, projection).sort('created_at', -1)

        if limit:
            cursor = cursor.limit(limit)

        intents = []
        for doc in cursor:
            # Extrair campos com fallbacks
            plan_data = doc.get('plan_data', {})
            metadata = plan_data.get('metadata', {})

            # Tentar extrair texto do intent de vários campos possíveis
            text = (
                metadata.get('original_intent_text') or
                plan_data.get('original_intent_text') or
                plan_data.get('intent_text') or
                ''
            )

            # Extrair keywords do texto
            keywords = extract_keywords(text)

            intent = {
                'intent_id': doc.get('intent_id'),
                'domain': plan_data.get('original_domain') or 'unknown',
                'confidence': metadata.get('original_confidence', 0.0),
                'timestamp': doc.get('created_at') or doc.get('timestamp'),
                'plan_id': doc.get('plan_id'),
                'outcome': 'success',  # Se está no ledger, foi processado com sucesso
                'text': text,
                'keywords': keywords
            }

            # Pular documentos sem intent_id
            if intent['intent_id']:
                intents.append(intent)

        # Contar intents com e sem texto
        intents_with_text = sum(1 for i in intents if i['text'])
        intents_without_text = len(intents) - intents_with_text

        logger.info(
            "Intents encontrados no MongoDB",
            total=len(intents),
            with_text=intents_with_text,
            without_text=intents_without_text
        )

        return intents

    except Exception as e:
        logger.error(
            "Erro ao buscar intents do MongoDB",
            error=str(e)
        )
        sys.exit(1)


async def seed_intents_to_neo4j(
    driver,
    intents: List[Dict],
    database: str,
    batch_size: int,
    dry_run: bool
) -> Dict[str, int]:
    """
    Popula Neo4j com intents.

    Args:
        driver: Driver do Neo4j
        intents: Lista de intents
        database: Nome do database
        batch_size: Tamanho do batch
        dry_run: Se True, apenas simula

    Returns:
        Estatísticas do seed
    """
    total_processed = 0
    total_created = 0
    total_errors = 0

    query = '''
    MERGE (i:Intent {id: $intent_id})
    SET i.domain = $domain,
        i.confidence = $confidence,
        i.timestamp = $timestamp,
        i.plan_id = $plan_id,
        i.outcome = $outcome,
        i.text = $text,
        i.keywords = $keywords,
        i.seeded_at = datetime()
    RETURN i.id AS id
    '''

    if dry_run:
        logger.info(
            "DRY RUN - Simulando seed de intents",
            total_intents=len(intents)
        )
        for i, intent in enumerate(intents[:5]):
            logger.info(
                f"  Intent {i+1}",
                intent_id=intent['intent_id'],
                domain=intent['domain'],
                has_text=bool(intent.get('text')),
                keywords=intent.get('keywords', '')[:50]
            )
        if len(intents) > 5:
            logger.info(f"  ... e mais {len(intents) - 5} intents")

        return {
            'total_processed': len(intents),
            'total_created': 0,
            'total_errors': 0,
            'dry_run': True
        }

    # Processar em batches
    for i in range(0, len(intents), batch_size):
        batch = intents[i:i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(intents) + batch_size - 1) // batch_size

        async with driver.session(database=database) as session:
            for intent in batch:
                try:
                    result = await session.run(
                        query,
                        intent_id=intent['intent_id'],
                        domain=intent['domain'],
                        confidence=intent['confidence'],
                        timestamp=str(intent['timestamp']) if intent['timestamp'] else None,
                        plan_id=intent['plan_id'],
                        outcome=intent['outcome'],
                        text=intent.get('text', ''),
                        keywords=intent.get('keywords', '')
                    )
                    await result.consume()
                    total_created += 1

                except Exception as e:
                    logger.warning(
                        "Erro ao inserir intent",
                        intent_id=intent['intent_id'],
                        error=str(e)
                    )
                    total_errors += 1

                total_processed += 1

        logger.info(
            f"Progresso: batch {batch_num}/{total_batches}",
            processed=total_processed,
            created=total_created,
            errors=total_errors
        )

    return {
        'total_processed': total_processed,
        'total_created': total_created,
        'total_errors': total_errors,
        'dry_run': False
    }


async def create_indexes(driver, database: str, dry_run: bool):
    """
    Cria índices no Neo4j para queries eficientes.

    Args:
        driver: Driver do Neo4j
        database: Nome do database
        dry_run: Se True, apenas lista índices
    """
    indexes = [
        'CREATE INDEX intent_id_idx IF NOT EXISTS FOR (i:Intent) ON (i.id)',
        'CREATE INDEX intent_domain_idx IF NOT EXISTS FOR (i:Intent) ON (i.domain)',
        'CREATE INDEX intent_timestamp_idx IF NOT EXISTS FOR (i:Intent) ON (i.timestamp)'
    ]

    if dry_run:
        logger.info("DRY RUN - Índices que seriam criados:")
        for idx in indexes:
            logger.info(f"  {idx}")
        return

    async with driver.session(database=database) as session:
        for idx_query in indexes:
            try:
                await session.run(idx_query)
                logger.info(
                    "Índice criado",
                    query=idx_query[:50] + "..."
                )
            except Exception as e:
                logger.warning(
                    "Erro ao criar índice (pode já existir)",
                    query=idx_query[:50] + "...",
                    error=str(e)
                )


async def validate_seed(driver, database: str, expected_count: int) -> bool:
    """
    Valida que o seed foi bem-sucedido.

    Args:
        driver: Driver do Neo4j
        database: Nome do database
        expected_count: Número esperado de intents

    Returns:
        True se validação passou
    """
    query = 'MATCH (i:Intent) RETURN count(i) as total'

    async with driver.session(database=database) as session:
        try:
            result = await session.run(query)
            record = await result.single()
            total = record['total'] if record else 0

            logger.info(
                "Validação de seed",
                total_intent_nodes=total,
                expected=expected_count
            )

            if total >= expected_count:
                return True
            else:
                logger.warning(
                    "Seed incompleto",
                    total=total,
                    expected=expected_count
                )
                return False

        except Exception as e:
            logger.error(
                "Erro ao validar seed",
                error=str(e)
            )
            return False


async def main_async():
    """Função principal assíncrona."""
    args = parse_args()

    # Conectar ao MongoDB
    print("Conectando ao MongoDB...")
    collection = connect_mongodb(
        args.mongodb_uri,
        args.mongodb_database,
        args.mongodb_collection
    )
    print()

    # Buscar intents do MongoDB
    print("Buscando intents do MongoDB...")
    intents = fetch_intents_from_mongodb(collection, args.limit)
    print(f"   Encontrados: {len(intents):,} intents")
    print()

    if not intents:
        print("Nenhum intent encontrado para seed")
        return

    # Conectar ao Neo4j
    print("Conectando ao Neo4j...")
    driver = await connect_neo4j(
        args.neo4j_uri,
        args.neo4j_user,
        args.neo4j_password
    )
    print()

    try:
        if args.dry_run:
            print("DRY RUN - Simulando seed (nenhum dado será modificado)")
            print()

        # Seed intents no Neo4j
        print("Populando Neo4j com intents...")
        stats = await seed_intents_to_neo4j(
            driver,
            intents,
            args.neo4j_database,
            args.batch_size,
            args.dry_run
        )
        print(f"   Processados: {stats['total_processed']:,}")
        print(f"   Criados: {stats['total_created']:,}")
        print(f"   Erros: {stats['total_errors']:,}")
        print()

        if args.dry_run:
            print("Para executar seed, remova flag --dry-run")
            return

        # Criar índices
        print("Criando índices no Neo4j...")
        await create_indexes(driver, args.neo4j_database, args.dry_run)
        print()

        # Validar seed
        print("Validando seed...")
        success = await validate_seed(
            driver,
            args.neo4j_database,
            len(intents)
        )
        print()

        if success:
            print("=" * 80)
            print("Seed concluído com sucesso!")
            print("=" * 80)
        else:
            print("=" * 80)
            print("Seed concluído com avisos - verifique logs")
            print("=" * 80)
            sys.exit(1)

    finally:
        # Fechar conexão Neo4j
        await driver.close()


def main():
    """Função principal."""
    print("=" * 80)
    print("Neural Hive Mind - Neo4j Intent Seed")
    print("=" * 80)
    print()

    asyncio.run(main_async())


if __name__ == "__main__":
    main()
