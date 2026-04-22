"""
Métricas Prometheus para Learning Documentation Generator.
"""

from prometheus_client import Counter, Gauge, Histogram


class LearningDocMetrics:
    """Métricas Prometheus do Learning Documentation Generator."""

    def __init__(self):
        # Documentos gerados
        self.docs_generated_total = Counter(
            "learning_docs_generated_total",
            "Total de documentos de aprendizado gerados",
            ["doc_type", "status"],
        )

        # Duração da geração
        self.generation_duration = Histogram(
            "learning_docs_generation_duration_seconds",
            "Duração da geração de documentos de aprendizado",
            ["doc_type"],
            buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0],
        )

        # Insights extraídos
        self.insights_extracted_total = Counter(
            "learning_insights_extracted_total",
            "Total de insights extraídos de experimentos",
            ["category", "confidence"],
        )

        # Experimentos processados
        self.experiments_processed_total = Counter(
            "learning_experiments_processed_total",
            "Total de experimentos MLflow processados",
            ["status"],
        )

        # Documentos por status
        self.docs_by_status = Gauge(
            "learning_docs_by_status",
            "Número de documentos por status",
            ["doc_type", "status"],
        )

        # Última geração por tipo
        self.last_generation_timestamp = Gauge(
            "learning_docs_last_generation_timestamp",
            "Timestamp Unix da última geração de documento",
            ["doc_type"],
        )

        # Tamanho dos documentos gerados
        self.doc_size_bytes = Histogram(
            "learning_docs_size_bytes",
            "Tamanho em bytes dos documentos gerados",
            ["doc_type"],
            buckets=[1024, 10240, 102400, 1024000, 10485760],
        )

        # Plots gerados
        self.plots_generated_total = Counter(
            "learning_plots_generated_total",
            "Total de plots gráficos gerados",
            ["plot_type", "format"],
        )

        # Erros de geração
        self.generation_errors_total = Counter(
            "learning_docs_generation_errors_total",
            "Total de erros na geração de documentos",
            ["doc_type", "error_type"],
        )

        # Filas de geração
        self.generation_queue_size = Gauge(
            "learning_docs_generation_queue_size",
            "Tamanho atual da fila de geração de documentos",
        )

    def record_doc_generated(
        self,
        doc_type: str,
        status: str,
        duration: float,
        size_bytes: int = 0,
    ) -> None:
        """Registra geração de documento.

        Args:
            doc_type: Tipo do documento
            status: Status da geração (success, failed, etc)
            duration: Duração em segundos
            size_bytes: Tamanho do documento em bytes
        """
        self.docs_generated_total.labels(doc_type=doc_type, status=status).inc()

        if status == "success":
            self.generation_duration.labels(doc_type=doc_type).observe(duration)
            self.last_generation_timestamp.labels(doc_type=doc_type).set_to_current_time()
            if size_bytes > 0:
                self.doc_size_bytes.labels(doc_type=doc_type).observe(size_bytes)
        else:
            self.generation_errors_total.labels(
                doc_type=doc_type, error_type="generation_failed"
            ).inc()

    def record_insight_extracted(self, category: str, confidence: str) -> None:
        """Registra insight extraído.

        Args:
            category: Categoria do insight (performance, improvement, trend, etc)
            confidence: Nível de confiança (high, medium, low)
        """
        self.insights_extracted_total.labels(category=category, confidence=confidence).inc()

    def record_experiment_processed(self, status: str) -> None:
        """Registra experimento processado.

        Args:
            status: Status do processamento (success, failed, skipped)
        """
        self.experiments_processed_total.labels(status=status).inc()

    def update_docs_by_status(self, doc_type: str, status: str, count: int) -> None:
        """Atualiza contador de documentos por status.

        Args:
            doc_type: Tipo do documento
            status: Status do documento
            count: Quantidade
        """
        self.docs_by_status.labels(doc_type=doc_type, status=status).set(count)

    def record_plot_generated(self, plot_type: str, format_type: str) -> None:
        """Registra plot gerado.

        Args:
            plot_type: Tipo do plot (line, bar, scatter, etc)
            format_type: Formato do arquivo (png, svg, pdf)
        """
        self.plots_generated_total.labels(plot_type=plot_type, format=format_type).inc()

    def update_queue_size(self, size: int) -> None:
        """Atualiza tamanho da fila de geração.

        Args:
            size: Tamanho atual da fila
        """
        self.generation_queue_size.set(size)

    def record_generation_error(self, doc_type: str, error_type: str) -> None:
        """Registra erro de geração.

        Args:
            doc_type: Tipo do documento
            error_type: Tipo do erro (mlflow_error, mongodb_error, etc)
        """
        self.generation_errors_total.labels(doc_type=doc_type, error_type=error_type).inc()


# Instância global
learning_doc_metrics = LearningDocMetrics()
