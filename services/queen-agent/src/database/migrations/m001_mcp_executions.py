# MCP Tool Executions Collection Migration

"""
Migration para criar coleção mcp_tool_executions com TTL.

Executar no MongoDB shell:
  use neural_hive
  db.mcp_tool_executions.createIndex(
    { "timestamp": 1 },
    { "expireAfterSeconds": 2592000, "name": "ttl_30_days" }
  )
"""

from datetime import datetime


def upgrade(mongo):
    """Aplica migration - cria coleção e índices."""
    collection = mongo["mcp_tool_executions"]

    # Índice para TTL (30 dias)
    collection.create_index(
        [("timestamp", 1)],
        expireAfterSeconds=30 * 24 * 60 * 60,  # 30 dias
        name="ttl_30_days",
    )

    # Índices para consultas comuns
    collection.create_index([("server", 1), ("timestamp", -1)])
    collection.create_index([("tool_name", 1), ("timestamp", -1)])
    collection.create_index([("status", 1)])
    collection.create_index("timestamp")

    print(f"[{datetime.now()}] MCP executions collection created with indexes")


def downgrade(mongo):
    """Remove migration - drop coleção."""
    mongo["mcp_tool_executions"].drop()
    print(f"[{datetime.now()}] MCP executions collection dropped")
