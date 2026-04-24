#!/usr/bin/env python3
"""
CLI para Pipeline de Promoção de Modelos ML

Interface de linha de comando para promover modelos entre ambientes
com validação, backup e rollback.

Usage:
    python -m ml_pipelines.deploy.cli promote \
        --model-path models/approval_v8.pkl \
        --to-stage production

    python -m ml_pipelines.deploy.cli rollback \
        --backup-path models/backups/nhm_approval_model_backup_20240316_143022.pkl

    python -m ml_pipelines.deploy.cli list-backups
"""

import json
import sys
from pathlib import Path

import click
import structlog

from .promote_model import (
    DEFAULT_BACKUP_DIR,
    DEFAULT_MAX_DRIFT_SCORE,
    DEFAULT_MIN_ACCURACY,
    DEFAULT_MIN_F1_SCORE,
    DEFAULT_MODELS_DIR,
    Stage,
    backup_current_model,
    get_current_model_info,
    list_backups,
    promote_model,
    rollback_model,
    validate_model,
)

logger = structlog.get_logger(__name__)


@click.group()
@click.option(
    "--models-dir",
    type=click.Path(exists=True, path_type=Path),
    default=DEFAULT_MODELS_DIR,
    help="Diretório onde estão os modelos",
)
@click.option(
    "--backup-dir",
    type=click.Path(path_type=Path),
    default=DEFAULT_BACKUP_DIR,
    help="Diretório para armazenar backups",
)
@click.option("--verbose", "-v", is_flag=True, help="Logging detalhado")
@click.pass_context
def cli(ctx: click.Context, models_dir: Path, backup_dir: Path, verbose: bool):
    """
    Pipeline de Promoção de Modelos ML Neural Hive Mind.

    Gerencia promoção de modelos entre ambientes com validação,
    backup automático e rollback.
    """
    ctx.ensure_object(dict)
    ctx.obj["models_dir"] = models_dir
    ctx.obj["backup_dir"] = backup_dir

    if verbose:
        structlog.configure(
            processors=[
                structlog.stdlib.add_log_level,
                structlog.stdlib.add_logger_name,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.dev.ConsoleRenderer(colors=True),
            ],
            wrapper_class=structlog.stdlib.BoundLogger,
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )


@cli.command()
@click.argument("model-path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--from-stage",
    type=click.Choice([Stage.STAGING, Stage.SHADOW]),
    default=Stage.STAGING,
    help="Ambiente de origem",
)
@click.option(
    "--to-stage",
    type=click.Choice([Stage.PRODUCTION, Stage.STAGING]),
    default=Stage.PRODUCTION,
    help="Ambiente de destino",
)
@click.option(
    "--min-accuracy",
    type=float,
    default=DEFAULT_MIN_ACCURACY,
    help="Acurácia mínima exigida",
)
@click.option(
    "--max-drift",
    type=float,
    default=DEFAULT_MAX_DRIFT_SCORE,
    help="Score máximo de drift permitido",
)
@click.option(
    "--min-f1",
    type=float,
    default=DEFAULT_MIN_F1_SCORE,
    help="F1-score mínimo exigido",
)
@click.option("--dry-run", is_flag=True, help="Simular promoção sem aplicar mudanças")
@click.pass_context
def promote(
    ctx: click.Context,
    model_path: Path,
    from_stage: str,
    to_stage: str,
    min_accuracy: float,
    max_drift: float,
    min_f1: float,
    dry_run: bool,
):
    """
    Promove modelo para ambiente de produção.

    Valida o modelo, cria backup do atual e promove a nova versão.
    """
    models_dir = ctx.obj["models_dir"]
    backup_dir = ctx.obj["backup_dir"]

    click.echo(f"\n{'='*60}")
    click.echo(f"PROMOÇÃO DE MODELO: {from_stage} → {to_stage}")
    click.echo(f"{'='*60}\n")

    try:
        result = promote_model(
            model_path=model_path,
            from_stage=from_stage,
            to_stage=to_stage,
            models_dir=models_dir,
            backup_dir=backup_dir,
            min_accuracy=min_accuracy,
            max_drift_score=max_drift,
            min_f1_score=min_f1,
            dry_run=dry_run,
        )

        if result["status"] == "success":
            click.echo(click.style("✓ PROMOÇÃO BEM-SUCEDIDA", fg="green", bold=True))
            click.echo("\nMétricas:")
            metrics = result.get("metrics", {})
            click.echo(f"  - Versão: {metrics.get('model_version', 'N/A')}")
            click.echo(f"  - Acurácia: {metrics.get('accuracy', 0):.2%}")
            click.echo(f"  - F1-Score: {metrics.get('f1_score', 0):.2%}")
            click.echo(f"  - Drift Score: {metrics.get('drift_score', 0):.3f}")
            click.echo(f"  - Amostras: {metrics.get('training_samples', 0)}")
            click.echo(f"\nBackup: {result.get('backup_path', 'N/A')}")

        elif result["status"] == "dry_run_success":
            click.echo(click.style("✓ DRY-RUN BEM-SUCEDIDO", fg="blue", bold=True))
            click.echo("\nMétricas do modelo:")
            metrics = result.get("metrics", {})
            click.echo(f"  - Versão: {metrics.get('model_version', 'N/A')}")
            click.echo(f"  - Acurácia: {metrics.get('accuracy', 0):.2%}")
            click.echo(f"  - F1-Score: {metrics.get('f1_score', 0):.2%}")
            click.echo("\nNenhuma alteração foi aplicada (--dry-run)")

        sys.exit(0)

    except Exception as e:
        click.echo(click.style(f"✗ ERRO NA PROMOÇÃO: {e}", fg="red", bold=True), err=True)
        sys.exit(1)


@cli.command()
@click.option(
    "--backup-path",
    type=click.Path(exists=True, path_type=Path),
    help="Caminho específico para backup (usa o mais recente se não especificado)",
)
@click.option(
    "--list-backups",
    is_flag=True,
    help="Listar backups disponíveis antes de fazer rollback",
)
@click.pass_context
def rollback(ctx: click.Context, backup_path: Path, list_backups_flag: bool):
    """
    Reverte para versão anterior do modelo.

    Se --backup-path não for especificado, usa o backup mais recente.
    """
    models_dir = ctx.obj["models_dir"]
    backup_dir = ctx.obj["backup_dir"]

    click.echo(f"\n{'='*60}")
    click.echo("ROLLBACK DE MODELO")
    click.echo(f"{'='*60}\n")

    # Listar backups se solicitado
    if list_backups_flag or backup_path is None:
        backups = list_backups(backup_dir=backup_dir)

        if not backups:
            click.echo(click.style("Nenhum backup encontrado", fg="yellow"))
            sys.exit(1)

        click.echo("Backups disponíveis:")
        for i, b in enumerate(backups, 1):
            click.echo(f"  {i}. {Path(b['path']).name}")
            click.echo(f"     Versão: {b['version']}")
            click.echo(f"     Criado em: {b['created_at']}")
            click.echo(f"     Tamanho: {b['size_bytes']:,} bytes")
            click.echo()

        if backup_path is None:
            # Usar o mais recente
            backup_path = Path(backups[0]["path"])
            click.echo(f"Usando backup mais recente: {backup_path.name}\n")

    try:
        result = rollback_model(
            backup_path=backup_path,
            models_dir=models_dir,
            backup_dir=backup_dir,
        )

        if result["status"] == "success":
            click.echo(click.style("✓ ROLLBACK BEM-SUCEDIDO", fg="green", bold=True))
            click.echo(f"\nVersão restaurada: {result.get('backup_version', 'N/A')}")
            click.echo(f"Backup usado: {result.get('backup_path', 'N/A')}")

        sys.exit(0)

    except Exception as e:
        click.echo(click.style(f"✗ ERRO NO ROLLBACK: {e}", fg="red", bold=True), err=True)
        sys.exit(1)


@cli.command("list-backups")
@click.option(
    "--limit",
    type=int,
    default=10,
    help="Número máximo de backups a listar",
)
@click.pass_context
def list_backups_cmd(ctx: click.Context, limit: int):
    """Lista backups disponíveis."""
    backup_dir = ctx.obj["backup_dir"]

    backups = list_backups(backup_dir=backup_dir, limit=limit)

    if not backups:
        click.echo("Nenhum backup encontrado")
        return

    click.echo(f"\n{'='*60}")
    click.echo(f"BACKUPS DISPONÍVEIS ({len(backups)})")
    click.echo(f"{'='*60}\n")

    for i, b in enumerate(backups, 1):
        click.echo(f"{i}. {Path(b['path']).name}")
        click.echo(f"   Versão: {b['version']}")
        click.echo(f"   Criado: {b['created_at']}")
        click.echo(f"   Tamanho: {b['size_bytes']:,} bytes")
        click.echo()


@cli.command()
@click.argument("model-path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--min-accuracy",
    type=float,
    default=DEFAULT_MIN_ACCURACY,
    help="Acurácia mínima exigida",
)
@click.option(
    "--max-drift",
    type=float,
    default=DEFAULT_MAX_DRIFT_SCORE,
    help="Score máximo de drift permitido",
)
@click.option(
    "--min-f1",
    type=float,
    default=DEFAULT_MIN_F1_SCORE,
    help="F1-score mínimo exigido",
)
def validate(model_path: Path, min_accuracy: float, max_drift: float, min_f1: float):
    """
    Valida modelo treinado verificando arquivo e métricas.
    """
    click.echo(f"\n{'='*60}")
    click.echo("VALIDAÇÃO DE MODELO")
    click.echo(f"{'='*60}\n")

    try:
        metrics = validate_model(
            model_path=model_path,
            min_accuracy=min_accuracy,
            max_drift_score=max_drift,
            min_f1_score=min_f1,
        )

        click.echo(click.style("✓ MODELO VÁLIDO", fg="green", bold=True))
        click.echo("\nMétricas:")
        click.echo(f"  - Versão: {metrics.model_version}")
        click.echo(f"  - Acurácia: {metrics.accuracy:.2%}")
        click.echo(f"  - Precisão: {metrics.precision:.2%}")
        click.echo(f"  - Recall: {metrics.recall:.2%}")
        click.echo(f"  - F1-Score: {metrics.f1_score:.2%}")
        click.echo(f"  - Drift Score: {metrics.drift_score:.3f}")
        click.echo(f"  - Amostras: {metrics.training_samples}")

        sys.exit(0)

    except Exception as e:
        click.echo(click.style(f"✗ VALIDAÇÃO FALHOU: {e}", fg="red", bold=True), err=True)
        sys.exit(1)


@cli.command()
@click.option("--json", "as_json", is_flag=True, help="Saída em formato JSON")
@click.pass_context
def info(ctx: click.Context, as_json: bool):
    """
    Exibe informações sobre o modelo atual em produção.
    """
    models_dir = ctx.obj["models_dir"]

    info = get_current_model_info(models_dir=models_dir)

    if as_json:
        click.echo(json.dumps(info, indent=2))
    else:
        click.echo(f"\n{'='*60}")
        click.echo("MODELO ATUAL EM PRODUÇÃO")
        click.echo(f"{'='*60}\n")

        if not info or info.get("error"):
            click.echo(click.style("Nenhum modelo encontrado em produção", fg="yellow"))
            return

        click.echo(f"Versão: {info.get('model_version', 'N/A')}")
        click.echo(f"Treinado em: {info.get('trained_at', 'N/A')}")

        metrics = info.get("metrics", {})
        if metrics:
            click.echo("\nMétricas:")
            click.echo(f"  - F1-Score: {metrics.get('f1_score', 0):.2%}")
            click.echo(f"  - Precisão: {metrics.get('precision', 0):.2%}")
            click.echo(f"  - Recall: {metrics.get('recall', 0):.2%}")

        click.echo(f"\nArquivo: {info.get('file_path', 'N/A')}")
        click.echo(f"Tamanho: {info.get('file_size_bytes', 0):,} bytes")


@cli.command()
@click.option(
    "--backup-dir",
    type=click.Path(path_type=Path),
    default=DEFAULT_BACKUP_DIR,
    help="Diretório para armazenar backup",
)
@click.pass_context
def backup(ctx: click.Context, backup_dir: Path):
    """
    Cria backup do modelo atual.
    """
    models_dir = ctx.obj["models_dir"]

    click.echo(f"\n{'='*60}")
    click.echo("CRIANDO BACKUP DO MODELO ATUAL")
    click.echo(f"{'='*60}\n")

    try:
        backup_path = backup_current_model(
            models_dir=models_dir,
            backup_dir=backup_dir,
        )

        if "no_backup_needed" in str(backup_path):
            click.echo(click.style("Nenhum modelo atual encontrado para backup", fg="yellow"))
        else:
            click.echo(click.style("✓ BACKUP CRIADO", fg="green", bold=True))
            click.echo(f"\nCaminho: {backup_path}")

        sys.exit(0)

    except Exception as e:
        click.echo(click.style(f"✗ ERRO NO BACKUP: {e}", fg="red", bold=True), err=True)
        sys.exit(1)


if __name__ == "__main__":
    cli(obj={})
