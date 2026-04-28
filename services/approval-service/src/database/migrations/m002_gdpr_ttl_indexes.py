"""
Migration m002_gdpr_ttl_indexes

Adiciona índices TTL de 2 anos para compliance GDPR/LGPD (Artigo 17 - Retenção)
nas coleções que contêm dados pessoais.

Gap P0-6: Sem TTL Dados PII

Data: 2026-04-28
"""

from motor.motor_asyncio import AsyncIOMotorClient


# 2 anos em segundos (GDPR/LGPD retention máxima recomendada)
TWO_YEARS_SECONDS = 63072000  # 365 * 2 * 24 * 60 * 60


async def create_plan_approvals_ttl_index(
    client: AsyncIOMotorClient, db_name: str
) -> None:
    """
    Cria índice TTL na coleção plan_approvals.

    A coleção plan_approvals contém user_id e decisões de aprovação
    que podem conter dados pessoais sensíveis.
    """
    db = client[db_name]
    collection = db["plan_approvals"]

    # Verificar se índice já existe
    existing_indexes = await collection.index_information()
    if "created_at_ttl" in existing_indexes:
        print("  ✓ Índice created_at_ttl já existe em plan_approvals")
        return

    # Criar índice TTL no campo created_at
    await collection.create_index(
        [("created_at", 1)],
        name="created_at_ttl",
        expireAfterSeconds=TWO_YEARS_SECONDS,
    )
    print("  ✓ Índice TTL criado em plan_approvals (2 anos)")


async def create_specialist_feedback_ttl_index(
    client: AsyncIOMotorClient, db_name: str
) -> None:
    """
    Atualiza índice TTL na coleção specialist_feedback.

    Já existe um índice expires_at de 1 hora, mas adicionamos
    um índice de backup de 2 anos no campo created_at para garantir
    retenção máxima compliance.
    """
    db = client[db_name]
    collection = db["specialist_feedback"]

    # Verificar se índex já existe
    existing_indexes = await collection.index_information()
    if "created_at_ttl" in existing_indexes:
        print("  ✓ Índice created_at_ttl já existe em specialist_feedback")
        return

    # Criar índice TTL no campo created_at
    # Nota: O índice expires_at (1 hora) continua para active learning queue
    await collection.create_index(
        [("created_at", 1)],
        name="created_at_ttl",
        expireAfterSeconds=TWO_YEARS_SECONDS,
    )
    print("  ✓ Índice TTL criado em specialist_feedback (2 anos)")


async def upgrade(client: AsyncIOMotorClient, db_name: str) -> None:
    """
    Executa a migration: cria índices TTL GDPR compliance.
    """
    print("\n=== GDPR TTL Indexes Migration ===")

    await create_plan_approvals_ttl_index(client, db_name)
    await create_specialist_feedback_ttl_index(client, db_name)

    print("\n✓ Migration completa: Índices TTL de 2 anos criados")
    print("  Nota: Documentos serão automaticamente deletados após 2 anos")


async def downgrade(client: AsyncIOMotorClient, db_name: str) -> None:
    """
    Rollback: remove índices TTL.
    """
    print("\n=== Rollback GDPR TTL Indexes ===")

    db = client[db_name]

    # Drop plan_approvals TTL
    plan_approvals = db["plan_approvals"]
    try:
        await plan_approvals.drop_index("created_at_ttl")
        print("  ✓ Índice TTL removido de plan_approvals")
    except Exception:
        print("  ! Índice created_at_ttl não encontrado em plan_approvals")

    # Drop specialist_feedback TTL
    specialist_feedback = db["specialist_feedback"]
    try:
        await specialist_feedback.drop_index("created_at_ttl")
        print("  ✓ Índice TTL removido de specialist_feedback")
    except Exception:
        print("  ! Índice created_at_ttl não encontrado em specialist_feedback")

    print("\n✓ Rollback completo")
