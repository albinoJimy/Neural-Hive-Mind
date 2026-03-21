"""
Migrations do MongoDB para Explainability API.

Migrations para criar/atualizar schema do database.
"""

from .m004_seniority_history import upgrade as m004_upgrade

MIGRATIONS = [m004_upgrade]
