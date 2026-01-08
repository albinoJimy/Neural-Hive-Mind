from prometheus_client import Counter, Histogram, Gauge


class CodeForgeMetrics:
    """Métricas Prometheus para Code Forge"""

    def __init__(self):
        # Lifecycle
        self.startup_total = Counter(
            'code_forge_startup_total',
            'Total de inicializações do Code Forge'
        )
        self.registered_total = Counter(
            'code_forge_registered_total',
            'Total de registros no Service Registry',
            ['status']
        )
        self.heartbeat_total = Counter(
            'code_forge_heartbeat_total',
            'Total de heartbeats',
            ['status']
        )

        # Pipelines
        self.pipelines_started_total = Counter(
            'code_forge_pipelines_started_total',
            'Total de pipelines iniciados'
        )
        self.pipelines_completed_total = Counter(
            'code_forge_pipelines_completed_total',
            'Total de pipelines concluídos',
            ['status']
        )
        self.pipelines_failed_total = Counter(
            'code_forge_pipelines_failed_total',
            'Total de pipelines falhados',
            ['error_type']
        )
        self.pipelines_duration_seconds = Histogram(
            'code_forge_pipelines_duration_seconds',
            'Duração de pipelines em segundos',
            buckets=[30, 60, 120, 300, 600, 1800, 3600]
        )
        self.active_pipelines = Gauge(
            'code_forge_active_pipelines',
            'Pipelines atualmente em execução'
        )

        # Stages
        self.stage_duration_seconds = Histogram(
            'code_forge_stage_duration_seconds',
            'Duração por stage',
            ['stage'],
            buckets=[5, 10, 30, 60, 120, 300]
        )
        self.stage_failures_total = Counter(
            'code_forge_stage_failures_total',
            'Falhas por stage',
            ['stage', 'error_type']
        )

        # Artifacts
        self.artifacts_generated_total = Counter(
            'code_forge_artifacts_generated_total',
            'Total de artefatos gerados',
            ['artifact_type']
        )
        self.artifacts_signed_total = Counter(
            'code_forge_artifacts_signed_total',
            'Total de artefatos assinados'
        )
        self.artifacts_uploaded_total = Counter(
            'code_forge_artifacts_uploaded_total',
            'Total de uploads de artefatos',
            ['registry_type']
        )

        # Validations
        self.validations_run_total = Counter(
            'code_forge_validations_run_total',
            'Total de validações executadas',
            ['validation_type', 'tool']
        )
        self.validation_issues_found = Histogram(
            'code_forge_validation_issues_found',
            'Issues encontrados',
            ['severity'],
            buckets=[0, 1, 5, 10, 20, 50, 100]
        )
        self.quality_score = Histogram(
            'code_forge_quality_score',
            'Score de qualidade',
            buckets=[0.0, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0]
        )

        # Tests
        self.tests_run_total = Counter(
            'code_forge_tests_run_total',
            'Total de testes executados',
            ['test_type']
        )
        self.tests_passed_total = Counter(
            'code_forge_tests_passed_total',
            'Total de testes passados'
        )
        self.test_coverage_percentage = Histogram(
            'code_forge_test_coverage_percentage',
            'Cobertura de testes',
            buckets=[0, 50, 60, 70, 80, 90, 95, 100]
        )

        # Approvals
        self.auto_approvals_total = Counter(
            'code_forge_auto_approvals_total',
            'Total de aprovações automáticas'
        )
        self.manual_reviews_total = Counter(
            'code_forge_manual_reviews_total',
            'Total de revisões manuais'
        )
        self.rejections_total = Counter(
            'code_forge_rejections_total',
            'Total de rejeições'
        )
        self.merge_requests_created_total = Counter(
            'code_forge_merge_requests_created_total',
            'Total de MRs criados'
        )

        # Templates
        self.template_selections_total = Counter(
            'code_forge_template_selections_total',
            'Total de seleções de templates',
            ['template_id']
        )
        self.template_cache_hits_total = Counter(
            'code_forge_template_cache_hits_total',
            'Total de cache hits de templates'
        )
        self.template_cache_misses_total = Counter(
            'code_forge_template_cache_misses_total',
            'Total de cache misses de templates'
        )

        # API
        self.api_requests_total = Counter(
            'code_forge_api_requests_total',
            'Total de requisições API',
            ['method', 'endpoint', 'status']
        )
        self.api_request_duration_seconds = Histogram(
            'code_forge_api_request_duration_seconds',
            'Latência de API',
            ['method', 'endpoint'],
            buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
        )

        # MCP Integration Metrics
        self.mcp_selection_requests_total = Counter(
            'code_forge_mcp_selection_requests_total',
            'Total MCP tool selection requests',
            ['status']  # success, failure, timeout
        )

        self.mcp_selection_duration_seconds = Histogram(
            'code_forge_mcp_selection_duration_seconds',
            'MCP tool selection duration',
            buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
        )

        self.mcp_tools_selected_total = Counter(
            'code_forge_mcp_tools_selected_total',
            'Total tools selected by MCP',
            ['category']
        )

        self.mcp_feedback_sent_total = Counter(
            'code_forge_mcp_feedback_sent_total',
            'Total feedback sent to MCP',
            ['status']  # success, failure
        )

        # External Tools Metrics
        self.snyk_scan_duration_seconds = Histogram(
            'code_forge_snyk_scan_duration_seconds',
            'Duration of Snyk dependency scans',
            buckets=[5, 10, 30, 60, 120, 300]
        )

        self.trivy_scan_duration_seconds = Histogram(
            'code_forge_trivy_scan_duration_seconds',
            'Duration of Trivy vulnerability scans',
            ['scan_type'],  # image, fs, config
            buckets=[5, 10, 30, 60, 120, 300, 600]
        )

        self.sonarqube_analysis_duration_seconds = Histogram(
            'code_forge_sonarqube_analysis_duration_seconds',
            'Duration of SonarQube code analysis',
            buckets=[30, 60, 120, 300, 600, 900]
        )

        self.git_operations_total = Counter(
            'code_forge_git_operations_total',
            'Total Git operations',
            ['operation', 'provider', 'status']  # operation: create_branch, commit, push, create_mr; provider: gitlab, github
        )

        self.external_tool_errors_total = Counter(
            'code_forge_external_tool_errors_total',
            'Total errors from external tools',
            ['tool', 'error_type']  # tool: snyk, trivy, sonarqube, git; error_type: timeout, api_error, cli_error
        )

        # ========================================================================
        # Métricas de Clients de Banco de Dados
        # ========================================================================

        # MongoDB Metrics
        self.mongodb_operations_total = Counter(
            'code_forge_mongodb_operations_total',
            'Total de operações MongoDB',
            ['operation', 'status']  # operation: save_artifact, get_artifact, save_logs; status: success, failure
        )
        self.mongodb_operation_duration_seconds = Histogram(
            'code_forge_mongodb_operation_duration_seconds',
            'Duração de operações MongoDB',
            ['operation'],
            buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
        )

        # PostgreSQL Metrics
        self.postgres_operations_total = Counter(
            'code_forge_postgres_operations_total',
            'Total de operações PostgreSQL',
            ['operation', 'status']  # operation: save_pipeline, get_pipeline, list, update; status: success, failure
        )
        self.postgres_operation_duration_seconds = Histogram(
            'code_forge_postgres_operation_duration_seconds',
            'Duração de operações PostgreSQL',
            ['operation'],
            buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
        )

        # Redis Metrics
        self.redis_cache_hits_total = Counter(
            'code_forge_redis_cache_hits_total',
            'Total de cache hits Redis'
        )
        self.redis_cache_misses_total = Counter(
            'code_forge_redis_cache_misses_total',
            'Total de cache misses Redis'
        )
        self.redis_operations_total = Counter(
            'code_forge_redis_operations_total',
            'Total de operações Redis',
            ['operation', 'status']  # operation: cache_template, get_template, set_state, acquire_lock; status: success, failure
        )
        self.redis_operation_duration_seconds = Histogram(
            'code_forge_redis_operation_duration_seconds',
            'Duração de operações Redis',
            ['operation'],
            buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5]
        )

        # Sigstore Metrics
        self.sigstore_signatures_total = Counter(
            'code_forge_sigstore_signatures_total',
            'Total de assinaturas Sigstore',
            ['status']  # success, failure, mock
        )
        self.sigstore_sbom_generations_total = Counter(
            'code_forge_sigstore_sbom_generations_total',
            'Total de gerações de SBOM',
            ['status']  # success, failure, mock
        )
        self.sigstore_operation_duration_seconds = Histogram(
            'code_forge_sigstore_operation_duration_seconds',
            'Duração de operações Sigstore',
            ['operation'],  # sign, verify, sbom, rekor_upload
            buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 120.0]
        )
        self.sigstore_rekor_uploads_total = Counter(
            'code_forge_sigstore_rekor_uploads_total',
            'Total de uploads para Rekor',
            ['status']  # success, failure
        )

        # S3 Artifact Storage Metrics
        self.s3_upload_duration_seconds = Histogram(
            'code_forge_s3_upload_duration_seconds',
            'Duração de uploads S3',
            ['operation'],  # sbom, artifact
            buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0]
        )

        self.s3_upload_total = Counter(
            'code_forge_s3_upload_total',
            'Total de uploads S3',
            ['status', 'operation']  # success/failure, sbom/artifact
        )

        self.s3_integrity_check_total = Counter(
            'code_forge_s3_integrity_check_total',
            'Total de verificações de integridade S3',
            ['status']  # success/failure
        )
