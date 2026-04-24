"""
Entry point para execução do módulo ml_pipelines.deploy.

Permite executar: python -m ml_pipelines.deploy
"""

from .cli import cli

if __name__ == "__main__":
    cli()
