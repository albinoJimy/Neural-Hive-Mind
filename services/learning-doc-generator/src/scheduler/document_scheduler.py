"""Scheduler para geração automática de documentos de aprendizado

Implementa geração periódica (diária, semanal, mensal) usando APScheduler.
Publica eventos em Kafka quando documentos são gerados.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from src.config import get_settings
from src.models import (
    DocumentFormat,
    DocumentStatus,
    DocumentType,
    LearningDocument,
)
from src.services import (
    DocumentRepository,
    ExperimentInsightExtractor,
    MarkdownReportGenerator,
)

logger = structlog.get_logger()


class DocumentScheduler:
    """Scheduler para geração periódica de documentos"""

    def __init__(
        self,
        repository: DocumentRepository,
        insight_extractor: ExperimentInsightExtractor,
        report_generator: MarkdownReportGenerator,
    ):
        """Inicializa o scheduler

        Args:
            repository: Repositório MongoDB
            insight_extractor: Extrator de insights do MLflow
            report_generator: Gerador de relatórios Markdown
        """
        self.settings = get_settings()
        self.repository = repository
        self.insight_extractor = insight_extractor
        self.report_generator = report_generator

        self.scheduler: Optional[AsyncIOScheduler] = None
        self._running = False

    async def start(self) -> None:
        """Inicia o scheduler com jobs agendados"""
        if not self.settings.scheduler_enabled:
            logger.info("Scheduler desabilitado nas configurações")
            return

        if self._running:
            logger.warning("Scheduler já está em execução")
            return

        try:
            # Criar scheduler
            self.scheduler = AsyncIOScheduler(
                timezone="UTC",
                job_defaults={
                    "coalesce": True,  # Consolidar jobs atrasados
                    "max_instances": 1,  # Apenas uma instância por job
                    "misfire_grace_time": 3600,  # 1 hora de tolerância
                },
            )

            # Adicionar jobs
            await self._setup_jobs()

            # Iniciar scheduler
            self.scheduler.start()
            self._running = True

            logger.info(
                "scheduler_started",
                daily_hour=self.settings.scheduler_daily_hour,
                weekly_day=self.settings.scheduler_weekly_day,
                monthly_day=self.settings.scheduler_monthly_day,
            )

        except Exception as e:
            logger.error("erro_ao_iniciar_scheduler", error=str(e), exc_info=True)
            raise

    async def _setup_jobs(self) -> None:
        """Configura os jobs agendados"""

        # Job diário - relatório consolidado do dia anterior
        self.scheduler.add_job(
            self._generate_daily_report,
            trigger=CronTrigger(
                hour=self.settings.scheduler_daily_hour,
                minute=self.settings.scheduler_daily_minute,
            ),
            id="daily_report",
            name="Daily Learning Report",
            replace_existing=True,
        )

        # Job semanal - relatório consolidado da semana anterior
        self.scheduler.add_job(
            self._generate_weekly_report,
            trigger=CronTrigger(
                day_of_week=self.settings.scheduler_weekly_day,
                hour=self.settings.scheduler_daily_hour,
                minute=self.settings.scheduler_daily_minute,
            ),
            id="weekly_report",
            name="Weekly Learning Report",
            replace_existing=True,
        )

        # Job mensal - relatório consolidado do mês anterior
        self.scheduler.add_job(
            self._generate_monthly_report,
            trigger=CronTrigger(
                day=self.settings.scheduler_monthly_day,
                hour=self.settings.scheduler_daily_hour,
                minute=self.settings.scheduler_daily_minute,
            ),
            id="monthly_report",
            name="Monthly Learning Report",
            replace_existing=True,
        )

        logger.info("scheduler_jobs_configured", jobs_count=3)

    async def _generate_daily_report(self) -> None:
        """Gera relatório diário de aprendizado"""
        logger.info("generating_daily_report")

        try:
            # Período: dia anterior (UTC)
            today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            yesterday = today - timedelta(days=1)

            # Buscar experimentos do período
            experiment_runs = await self.insight_extractor.get_runs_by_period(
                start_time=yesterday, end_time=today, limit=self.settings.max_experiments_per_doc
            )

            if not experiment_runs:
                logger.info("no_experiments_for_daily_report", date=yesterday.strftime("%Y-%m-%d"))
                return

            # Extrair insights
            insights = await self.insight_extractor.extract_insights_from_runs(experiment_runs)

            # Criar documento
            title = f"Relatório de Aprendizado Diário - {yesterday.strftime('%Y-%m-%d')}"
            summary = self._generate_period_summary(experiment_runs, insights, "diário")

            document = LearningDocument(
                title=title,
                type=DocumentType.DAILY_SUMMARY,
                status=DocumentStatus.COMPLETED,
                format=DocumentFormat.MARKDOWN,
                period_start=yesterday,
                period_end=today,
                summary=summary,
                insights=insights,
                experiment_runs=experiment_runs,
                recommendations=self._generate_recommendations(insights),
                metadata={"generated_by": "scheduler", "period_type": "daily"},
                generated_at=datetime.now(timezone.utc),
            )

            # Salvar no MongoDB
            doc_id = await self.repository.save(document)
            logger.info("daily_report_saved", doc_id=doc_id, experiments_count=len(experiment_runs))

        except Exception as e:
            logger.error("erro_ao_gerar_relatorio_diario", error=str(e), exc_info=True)

    async def _generate_weekly_report(self) -> None:
        """Gera relatório semanal de aprendizado"""
        logger.info("generating_weekly_report")

        try:
            # Período: semana anterior (7 dias)
            today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            week_start = today - timedelta(days=7)

            # Buscar experimentos do período
            experiment_runs = await self.insight_extractor.get_runs_by_period(
                start_time=week_start,
                end_time=today,
                limit=self.settings.max_experiments_per_doc,
            )

            if not experiment_runs:
                logger.info(
                    "no_experiments_for_weekly_report",
                    start=week_start.strftime("%Y-%m-%d"),
                    end=today.strftime("%Y-%m-%d"),
                )
                return

            # Extrair insights
            insights = await self.insight_extractor.extract_insights_from_runs(experiment_runs)

            # Criar documento
            title = (
                f"Relatório de Aprendizado Semanal - Semana de {week_start.strftime('%Y-%m-%d')}"
            )
            summary = self._generate_period_summary(experiment_runs, insights, "semanal")

            document = LearningDocument(
                title=title,
                type=DocumentType.WEEKLY_SUMMARY,
                status=DocumentStatus.COMPLETED,
                format=DocumentFormat.MARKDOWN,
                period_start=week_start,
                period_end=today,
                summary=summary,
                insights=insights,
                experiment_runs=experiment_runs,
                recommendations=self._generate_recommendations(insights),
                metadata={"generated_by": "scheduler", "period_type": "weekly"},
                generated_at=datetime.now(timezone.utc),
            )

            # Salvar no MongoDB
            doc_id = await self.repository.save(document)
            logger.info(
                "weekly_report_saved", doc_id=doc_id, experiments_count=len(experiment_runs)
            )

        except Exception as e:
            logger.error("erro_ao_gerar_relatorio_semanal", error=str(e), exc_info=True)

    async def _generate_monthly_report(self) -> None:
        """Gera relatório mensal de aprendizado"""
        logger.info("generating_monthly_report")

        try:
            # Período: mês anterior
            today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

            # Primeiro dia do mês atual
            if today.day >= self.settings.scheduler_monthly_day:
                # Ainda no mês do agendamento
                month_start = today.replace(day=1)
            else:
                # Já passou para o próximo mês
                if today.month == 1:
                    month_start = today.replace(year=today.year - 1, month=12, day=1)
                else:
                    month_start = today.replace(month=today.month - 1, day=1)

            # Buscar experimentos do período
            experiment_runs = await self.insight_extractor.get_runs_by_period(
                start_time=month_start,
                end_time=today,
                limit=self.settings.max_experiments_per_doc,
            )

            if not experiment_runs:
                logger.info(
                    "no_experiments_for_monthly_report",
                    start=month_start.strftime("%Y-%m-%d"),
                    end=today.strftime("%Y-%m-%d"),
                )
                return

            # Extrair insights
            insights = await self.insight_extractor.extract_insights_from_runs(experiment_runs)

            # Criar documento
            month_name = month_start.strftime("%B %Y")
            title = f"Relatório de Aprendizado Mensal - {month_name}"
            summary = self._generate_period_summary(experiment_runs, insights, "mensal")

            document = LearningDocument(
                title=title,
                type=DocumentType.MONTHLY_SUMMARY,
                status=DocumentStatus.COMPLETED,
                format=DocumentFormat.MARKDOWN,
                period_start=month_start,
                period_end=today,
                summary=summary,
                insights=insights,
                experiment_runs=experiment_runs,
                recommendations=self._generate_recommendations(insights),
                metadata={"generated_by": "scheduler", "period_type": "monthly"},
                generated_at=datetime.now(timezone.utc),
            )

            # Salvar no MongoDB
            doc_id = await self.repository.save(document)
            logger.info(
                "monthly_report_saved",
                doc_id=doc_id,
                month=month_name,
                experiments_count=len(experiment_runs),
            )

        except Exception as e:
            logger.error("erro_ao_gerar_relatorio_mensal", error=str(e), exc_info=True)

    def _generate_period_summary(
        self, experiment_runs: list, insights: list, period_type: str
    ) -> str:
        """Gera resumo executivo do período"""
        total = len(experiment_runs)
        finished = sum(1 for r in experiment_runs if r.status == "FINISHED")

        high_confidence_insights = sum(1 for i in insights if i.confidence.value == "high")

        summary_lines = [
            f"Relatório {period_type} cobrindo {total} experimentos realizados no período.",
            f"Destaque: {finished} experimentos concluídos com sucesso ({finished / total * 100:.1f}%)",
            f"Identificados {len(insights)} insights, sendo {high_confidence_insights} de alta confiança.",
        ]

        if insights:
            top_insight = insights[0]
            summary_lines.append(
                f"Principal descoberta: {top_insight.title} - {top_insight.description[:100]}..."
            )

        return " ".join(summary_lines)

    def _generate_recommendations(self, insights: list) -> list:
        """Gera recomendações baseadas nos insights"""
        recommendations = []

        # Análise de performance
        perf_insights = [i for i in insights if i.category == "performance"]
        if perf_insights:
            recommendations.append(
                "Continuar monitorando métricas de performance dos modelos em produção"
            )

        # Análise de melhorias
        imp_insights = [i for i in insights if i.category == "improvement"]
        if imp_insights:
            recommendations.append(
                "Considerar promover para produção os modelos com melhoria significativa"
            )

        # Análise de regressões
        reg_insights = [i for i in insights if i.category == "regression"]
        if reg_insights:
            recommendations.append(
                "Investigar causas de regressões identificadas antes de promover novos modelos"
            )

        # Recomendação padrão
        if not recommendations:
            recommendations.append(
                "Manter pipeline de experimentos ativo e continuar coletando métricas"
            )

        return recommendations

    async def trigger_manual_report(
        self, doc_type: DocumentType, period_start: datetime, period_end: datetime
    ) -> Optional[str]:
        """Trigger manual de geração de relatório

        Args:
            doc_type: Tipo de documento (DAILY_SUMMARY, WEEKLY_SUMMARY, MONTHLY_SUMMARY)
            period_start: Início do período
            period_end: Fim do período

        Returns:
            ID do documento gerado ou None
        """
        try:
            # Buscar experimentos do período
            experiment_runs = await self.insight_extractor.get_runs_by_period(
                start_time=period_start,
                end_time=period_end,
                limit=self.settings.max_experiments_per_doc,
            )

            if not experiment_runs:
                logger.warning(
                    "no_experiments_for_manual_report",
                    doc_type=doc_type,
                    start=period_start.strftime("%Y-%m-%d"),
                )
                return None

            # Extrair insights
            insights = await self.insight_extractor.extract_insights_from_runs(experiment_runs)

            # Criar documento
            period_name = {
                DocumentType.DAILY_SUMMARY: "Diário",
                DocumentType.WEEKLY_SUMMARY: "Semanal",
                DocumentType.MONTHLY_SUMMARY: "Mensal",
            }.get(doc_type, "Periódico")

            title = f"Relatório de Aprendizado {period_name} (Manual) - {period_start.strftime('%Y-%m-%d')}"
            summary = self._generate_period_summary(experiment_runs, insights, period_name.lower())

            document = LearningDocument(
                title=title,
                type=doc_type,
                status=DocumentStatus.COMPLETED,
                format=DocumentFormat.MARKDOWN,
                period_start=period_start,
                period_end=period_end,
                summary=summary,
                insights=insights,
                experiment_runs=experiment_runs,
                recommendations=self._generate_recommendations(insights),
                metadata={"generated_by": "manual_trigger", "period_type": period_name.lower()},
                generated_at=datetime.now(timezone.utc),
            )

            # Salvar no MongoDB
            doc_id = await self.repository.save(document)
            logger.info(
                "manual_report_saved",
                doc_id=doc_id,
                doc_type=doc_type,
                experiments_count=len(experiment_runs),
            )

            return doc_id

        except Exception as e:
            logger.error("erro_ao_gerar_relatorio_manual", error=str(e), exc_info=True)
            return None

    async def stop(self) -> None:
        """Para o scheduler gracefulmente"""
        if not self._running:
            return

        logger.info("stopping_scheduler")

        if self.scheduler:
            self.scheduler.shutdown(wait=True)
            self.scheduler = None

        self._running = False
        logger.info("scheduler_stopped")

    def is_running(self) -> bool:
        """Verifica se o scheduler está em execução"""
        return self._running and self.scheduler is not None and self.scheduler.running

    def get_next_run_times(self) -> dict:
        """Retorna próximos horários de execução dos jobs"""
        if not self.scheduler:
            return {}

        next_runs = {}
        for job in self.scheduler.get_jobs():
            next_run = job.next_run_time
            if next_run:
                next_runs[job.id] = next_run.isoformat()

        return next_runs
