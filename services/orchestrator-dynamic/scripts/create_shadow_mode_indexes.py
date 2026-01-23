#!/usr/bin/env python3
"""
Script para criar indexes MongoDB para Shadow Mode.

Cria indexes para otimizar queries na collection 'shadow_mode_comparisons':
- TTL index para expiração automática (30 dias)
- Index composto para queries por modelo
- Index para análise de agreement rate
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Adicionar path das bibliotecas
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config.settings import get_settings
from clients.mongodb_client import MongoDBClient


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


SHADOW_MODE_INDEXES = [
    {
        'name': 'timestamp_ttl',
        'keys': [('timestamp', 1)],
        'options': {
            'expireAfterSeconds': 30 * 24 * 60 * 60,  # 30 dias
            'background': True
        }
    },
    {
        'name': 'model_name_timestamp',
        'keys': [('model_name', 1), ('timestamp', -1)],
        'options': {
            'background': True
        }
    },
    {
        'name': 'model_name_version_agreement',
        'keys': [
            ('model_name', 1),
            ('candidate_version', 1),
            ('agreement', 1)
        ],
        'options': {
            'background': True
        }
    },
    {
        'name': 'predictor_type_timestamp',
        'keys': [('predictor_type', 1), ('timestamp', -1)],
        'options': {
            'background': True
        }
    }
]


async def create_indexes(dry_run: bool = False) -> None:
    """
    Cria indexes na collection shadow_mode_comparisons.

    Args:
        dry_run: Se True, apenas mostra os indexes sem criar
    """
    config = get_settings()

    logger.info(
        'Conectando ao MongoDB',
        extra={'mongodb_database': config.mongodb_database}
    )

    mongodb_client = MongoDBClient(config)
    await mongodb_client.initialize()

    try:
        db = mongodb_client.db
        collection = db['shadow_mode_comparisons']

        # Listar indexes existentes
        existing_indexes = await collection.index_information()
        logger.info(
            'Indexes existentes',
            extra={'count': len(existing_indexes), 'indexes': list(existing_indexes.keys())}
        )

        for index_spec in SHADOW_MODE_INDEXES:
            index_name = index_spec['name']
            keys = index_spec['keys']
            options = index_spec.get('options', {})

            if index_name in existing_indexes:
                logger.info(f'Index {index_name} já existe, pulando')
                continue

            if dry_run:
                logger.info(
                    f'[DRY RUN] Criaria index: {index_name}',
                    extra={'keys': keys, 'options': options}
                )
            else:
                logger.info(f'Criando index: {index_name}')
                await collection.create_index(keys, name=index_name, **options)
                logger.info(f'Index {index_name} criado com sucesso')

        # Verificar indexes finais
        final_indexes = await collection.index_information()
        logger.info(
            'Indexes após criação',
            extra={'count': len(final_indexes), 'indexes': list(final_indexes.keys())}
        )

    finally:
        await mongodb_client.close()


async def drop_indexes(dry_run: bool = False) -> None:
    """
    Remove indexes da collection shadow_mode_comparisons.

    Args:
        dry_run: Se True, apenas mostra os indexes sem remover
    """
    config = get_settings()
    mongodb_client = MongoDBClient(config)
    await mongodb_client.initialize()

    try:
        db = mongodb_client.db
        collection = db['shadow_mode_comparisons']

        existing_indexes = await collection.index_information()

        for index_spec in SHADOW_MODE_INDEXES:
            index_name = index_spec['name']

            if index_name not in existing_indexes:
                logger.info(f'Index {index_name} não existe, pulando')
                continue

            if dry_run:
                logger.info(f'[DRY RUN] Removeria index: {index_name}')
            else:
                logger.info(f'Removendo index: {index_name}')
                await collection.drop_index(index_name)
                logger.info(f'Index {index_name} removido com sucesso')

    finally:
        await mongodb_client.close()


def main():
    parser = argparse.ArgumentParser(
        description='Gerencia indexes MongoDB para Shadow Mode'
    )
    parser.add_argument(
        '--action',
        choices=['create', 'drop'],
        default='create',
        help='Ação a executar (default: create)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Apenas mostra as ações sem executar'
    )

    args = parser.parse_args()

    if args.action == 'create':
        asyncio.run(create_indexes(dry_run=args.dry_run))
    elif args.action == 'drop':
        asyncio.run(drop_indexes(dry_run=args.dry_run))


if __name__ == '__main__':
    main()
