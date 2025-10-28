#!/usr/bin/env python3
"""
Script de migração para adicionar tenant_id='default' a documentos existentes no ledger.

Este script:
1. Conecta ao MongoDB
2. Busca documentos sem tenant_id
3. Adiciona tenant_id='default' a todos
4. Cria índices compostos para multi-tenancy
5. Valida migração

Uso:
    python scripts/migrate_ledger_add_tenant_id.py \\
        --mongodb-uri mongodb://localhost:27017 \\
        --dry-run

    python scripts/migrate_ledger_add_tenant_id.py \\
        --mongodb-uri mongodb://localhost:27017
"""

import argparse
import sys
import time
from typing import Dict, Any
from pymongo import MongoClient, ASCENDING
import structlog

logger = structlog.get_logger()


def parse_args():
    """Parse argumentos da linha de comando."""
    parser = argparse.ArgumentParser(
        description="Migrar ledger para adicionar tenant_id a documentos existentes"
    )
    parser.add_argument(
        "--mongodb-uri",
        required=True,
        help="URI do MongoDB (ex: mongodb://localhost:27017)"
    )
    parser.add_argument(
        "--database",
        default="neural_hive",
        help="Nome do database (default: neural_hive)"
    )
    parser.add_argument(
        "--collection",
        default="cognitive_ledger",
        help="Nome da collection (default: cognitive_ledger)"
    )
    parser.add_argument(
        "--default-tenant-id",
        default="default",
        help="Tenant ID padrão para documentos existentes (default: default)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simular migração sem modificar dados"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="Tamanho do batch para updates (default: 1000)"
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


def count_documents_without_tenant_id(collection) -> int:
    """
    Conta documentos sem tenant_id.

    Args:
        collection: Collection do MongoDB

    Returns:
        Número de documentos sem tenant_id
    """
    try:
        count = collection.count_documents({'tenant_id': {'$exists': False}})
        logger.info(
            "Documentos sem tenant_id encontrados",
            count=count
        )
        return count

    except Exception as e:
        logger.error(
            "Erro ao contar documentos",
            error=str(e)
        )
        sys.exit(1)


def migrate_documents(
    collection,
    default_tenant_id: str,
    batch_size: int,
    dry_run: bool
) -> Dict[str, Any]:
    """
    Migra documentos adicionando tenant_id.

    Args:
        collection: Collection do MongoDB
        default_tenant_id: Tenant ID padrão
        batch_size: Tamanho do batch
        dry_run: Se True, apenas simula

    Returns:
        Dict com estatísticas da migração
    """
    start_time = time.time()
    total_updated = 0

    try:
        # Query para documentos sem tenant_id
        query = {'tenant_id': {'$exists': False}}

        # Contar total
        total_docs = collection.count_documents(query)

        if total_docs == 0:
            logger.info("Nenhum documento para migrar")
            return {
                'total_documents': 0,
                'documents_updated': 0,
                'duration_seconds': 0.0,
                'dry_run': dry_run
            }

        logger.info(
            "Iniciando migração",
            total_documents=total_docs,
            default_tenant_id=default_tenant_id,
            dry_run=dry_run
        )

        if dry_run:
            logger.info(
                "DRY RUN - Nenhum documento será modificado",
                would_update=total_docs
            )
            return {
                'total_documents': total_docs,
                'documents_updated': 0,
                'duration_seconds': 0.0,
                'dry_run': True
            }

        # Atualizar documentos em batch
        update = {'$set': {'tenant_id': default_tenant_id}}
        result = collection.update_many(query, update)

        total_updated = result.modified_count

        duration = time.time() - start_time

        logger.info(
            "Migração concluída",
            documents_updated=total_updated,
            duration_seconds=round(duration, 2)
        )

        return {
            'total_documents': total_docs,
            'documents_updated': total_updated,
            'duration_seconds': round(duration, 2),
            'dry_run': False
        }

    except Exception as e:
        logger.error(
            "Erro durante migração",
            error=str(e)
        )
        sys.exit(1)


def create_multi_tenancy_indexes(collection, dry_run: bool):
    """
    Cria índices compostos para multi-tenancy.

    Args:
        collection: Collection do MongoDB
        dry_run: Se True, apenas lista índices a criar
    """
    indexes = [
        {
            'name': 'idx_tenant_opinion_id',
            'keys': [('tenant_id', ASCENDING), ('opinion_id', ASCENDING)],
            'unique': True
        },
        {
            'name': 'idx_tenant_plan_id',
            'keys': [('tenant_id', ASCENDING), ('plan_id', ASCENDING)],
            'unique': False
        },
        {
            'name': 'idx_tenant_specialist_evaluated_at',
            'keys': [
                ('tenant_id', ASCENDING),
                ('specialist_type', ASCENDING),
                ('evaluated_at', -1)
            ],
            'unique': False
        }
    ]

    logger.info(
        "Criando índices para multi-tenancy",
        index_count=len(indexes),
        dry_run=dry_run
    )

    if dry_run:
        logger.info("DRY RUN - Índices que seriam criados:")
        for idx in indexes:
            logger.info(
                "  - Índice",
                name=idx['name'],
                keys=idx['keys'],
                unique=idx['unique']
            )
        return

    try:
        for idx in indexes:
            # Verificar se índice já existe
            existing_indexes = collection.list_indexes()
            index_names = [i['name'] for i in existing_indexes]

            if idx['name'] in index_names:
                logger.info(
                    "Índice já existe - pulando",
                    name=idx['name']
                )
                continue

            # Criar índice
            collection.create_index(
                idx['keys'],
                name=idx['name'],
                unique=idx['unique'],
                background=True  # Não bloquear operações
            )

            logger.info(
                "Índice criado",
                name=idx['name']
            )

        logger.info("Índices criados com sucesso")

    except Exception as e:
        logger.error(
            "Erro ao criar índices",
            error=str(e)
        )
        # Não falhar - índices podem ser criados manualmente


def validate_migration(collection, default_tenant_id: str):
    """
    Valida que migração foi bem-sucedida.

    Args:
        collection: Collection do MongoDB
        default_tenant_id: Tenant ID esperado
    """
    logger.info("Validando migração...")

    try:
        # Contar documentos sem tenant_id (deve ser 0)
        without_tenant = collection.count_documents({'tenant_id': {'$exists': False}})

        # Contar documentos com tenant_id padrão
        with_default_tenant = collection.count_documents({'tenant_id': default_tenant_id})

        # Contar total de documentos
        total = collection.count_documents({})

        logger.info(
            "Validação de migração",
            total_documents=total,
            without_tenant_id=without_tenant,
            with_default_tenant_id=with_default_tenant
        )

        if without_tenant > 0:
            logger.warning(
                "Alguns documentos ainda não têm tenant_id",
                count=without_tenant
            )
            return False

        logger.info("✅ Migração validada com sucesso!")
        return True

    except Exception as e:
        logger.error(
            "Erro ao validar migração",
            error=str(e)
        )
        return False


def main():
    """Função principal."""
    args = parse_args()

    print("=" * 80)
    print("Neural Hive Mind - Migração Multi-Tenancy")
    print("=" * 80)
    print()

    # Conectar ao MongoDB
    print("🔍 Conectando ao MongoDB...")
    collection = connect_mongodb(args.mongodb_uri, args.database, args.collection)
    print()

    # Contar documentos sem tenant_id
    print("🔍 Buscando documentos sem tenant_id...")
    count = count_documents_without_tenant_id(collection)
    print(f"   Encontrados: {count:,} documentos")
    print()

    if count == 0:
        print("✅ Nenhum documento precisa ser migrado")
        print()
        return

    # Migrar documentos
    if args.dry_run:
        print("⚠️  DRY RUN - Simulando migração (nenhum dado será modificado)")
        print()

    print("🔄 Migrando documentos...")
    stats = migrate_documents(
        collection,
        args.default_tenant_id,
        args.batch_size,
        args.dry_run
    )
    print(f"   ✅ Migrados: {stats['documents_updated']:,} documentos")
    print(f"   ⏱️  Duração: {stats['duration_seconds']:.2f}s")
    print()

    if args.dry_run:
        print("Para executar migração, remova flag --dry-run")
        return

    # Criar índices
    print("📊 Criando índices para multi-tenancy...")
    create_multi_tenancy_indexes(collection, args.dry_run)
    print()

    # Validar migração
    print("✅ Validando migração...")
    success = validate_migration(collection, args.default_tenant_id)
    print()

    if success:
        print("=" * 80)
        print("✅ Migração concluída com sucesso!")
        print("=" * 80)
    else:
        print("=" * 80)
        print("⚠️  Migração concluída com avisos - verifique logs")
        print("=" * 80)
        sys.exit(1)


if __name__ == "__main__":
    main()
