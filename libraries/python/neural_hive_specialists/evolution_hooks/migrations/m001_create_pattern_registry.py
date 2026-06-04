"""
Migration m001: Create evolution_pattern_registry collection.

Esta migração cria a coleção e os índices necessários para o
funcionamento do sistema Evolution Hooks.
"""


def upgrade(mongo_client):
    """
    Criar coleção e índices para evolution_pattern_registry.

    Args:
        mongo_client: Cliente MongoDB (sync ou async)
    """
    db = mongo_client["neural_hive"]
    collection_name = "evolution_pattern_registry"

    # Verificar se coleção já existe
    existing_collections = db.list_collection_names()
    if collection_name in existing_collections:
        print(f"Collection {collection_name} already exists, skipping creation")
    else:
        # Criar coleção
        db.create_collection(collection_name)
        print(f"Created collection: {collection_name}")

    collection = db[collection_name]

    # Índice 1: Matching rápido (domain + complexity_signature prefix)
    existing_indexes = collection.list_indexes()
    index_names = [idx.get("name") for idx in existing_indexes]

    if "idx_domain_signature" not in index_names:
        collection.create_index(
            [("fingerprint.domain", 1), ("fingerprint.complexity_signature", 1)],
            name="idx_domain_signature",
        )
        print("Created index: idx_domain_signature")
    else:
        print("Index idx_domain_signature already exists")

    # Índice 2: Analytics por outcome
    if "idx_outcome_created" not in index_names:
        collection.create_index(
            [("feedback.outcome", 1), ("created_at", -1)], name="idx_outcome_created"
        )
        print("Created index: idx_outcome_created")
    else:
        print("Index idx_outcome_created already exists")

    # Índice 3: Popularidade de padrões
    if "idx_times_matched" not in index_names:
        collection.create_index([("metrics.times_matched", -1)], name="idx_times_matched")
        print("Created index: idx_times_matched")
    else:
        print("Index idx_times_matched already exists")

    # Índice 4: TTL - remove registros antigos após 90 dias
    if "idx_ttl" not in index_names:
        collection.create_index(
            [("created_at", 1)], expireAfterSeconds=90 * 24 * 3600, name="idx_ttl"
        )
        print("Created index: idx_ttl (TTL 90 days)")
    else:
        print("Index idx_ttl already exists")

    print(f"Migration m001 complete: {collection_name} ready with indexes")


def downgrade(mongo_client):
    """
    Remove coleção e índices.

    Args:
        mongo_client: Cliente MongoDB
    """
    db = mongo_client["neural_hive"]
    collection_name = "evolution_pattern_registry"

    # Drop coleção
    if collection_name in db.list_collection_names():
        db.drop_collection(collection_name)
        print(f"Migration m001 downgrade: dropped {collection_name}")
    else:
        print(f"Collection {collection_name} does not exist, nothing to drop")


def run_migration(mongo_uri: str = "mongodb://localhost:27017"):
    """
    Executa migração com URI de conexão.

    Args:
        mongo_uri: URI de conexão MongoDB
    """
    from pymongo import MongoClient

    client = MongoClient(mongo_uri)

    try:
        # Testar conexão
        client.admin.command("ping")
        print(f"Connected to MongoDB at {mongo_uri}")

        # Executar upgrade
        upgrade(client)

    except Exception as e:
        print(f"Error running migration: {e}")
        raise
    finally:
        client.close()


if __name__ == "__main__":
    import sys

    # Executar migração
    mongo_uri = sys.argv[1] if len(sys.argv) > 1 else "mongodb://localhost:27017"
    run_migration(mongo_uri)
