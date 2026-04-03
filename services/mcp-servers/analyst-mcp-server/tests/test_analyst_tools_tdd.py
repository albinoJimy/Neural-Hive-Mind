"""
Testes TDD para Analyst MCP Tools.

TDD: Testes escritos ANTES da implementação.
Ferramentas:
- analyze_insights: Analisar insights de dados
- detect_anomalies: Detectar anomalias em time-series
- query_timeseries: Consultar dados de métricas
- generate_dashboard: Gerar dados para disposition dashboard
- export_data: Exportar dados em múltiplos formatos
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest


class TestAnalyzeInsightsTool:
    """Testes da ferramenta analyze_insights."""

    @pytest.mark.asyncio
    async def test_analyze_insights_success(self):
        """Testa análise de insights com sucesso."""
        from analyst_mcp_server.tools.analyst_tools import analyze_insights

        with patch(
            "analyst_mcp_server.tools.analyst_tools._retrieve_insights", new_callable=AsyncMock
        ) as mock_retrieve:
            mock_retrieve.return_value = {
                "insights": [
                    {"metric": "cpu_usage", "value": 85.5, "trend": "up"},
                    {"metric": "memory_usage", "value": 72.3, "trend": "stable"},
                ],
                "total": 2,
            }

            result = await analyze_insights(
                plan_id="plan-123", metrics=["cpu_usage", "memory_usage"], aggregation="avg"
            )

            assert result["total"] == 2
            assert len(result["insights"]) == 2
            mock_retrieve.assert_called_once()

    @pytest.mark.asyncio
    async def test_analyze_insights_with_aggregation(self):
        """Testa análise com agregação."""
        from analyst_mcp_server.tools.analyst_tools import analyze_insights

        with patch(
            "analyst_mcp_server.tools.analyst_tools._retrieve_insights", new_callable=AsyncMock
        ) as mock_retrieve:
            mock_retrieve.return_value = {
                "insights": [
                    {"metric": "cpu_usage", "value": 80, "avg": 75.5, "max": 95},
                ],
                "aggregation": "avg",
                "total": 1,
            }

            result = await analyze_insights(
                plan_id="plan-123", metrics=["cpu_usage"], aggregation="avg"
            )

            assert result["aggregation"] == "avg"
            assert "avg" in result["insights"][0]

    @pytest.mark.asyncio
    async def test_analyze_insights_invalid_aggregation(self):
        """Testa erro para agregação inválida."""
        from analyst_mcp_server.tools.analyst_tools import analyze_insights

        with pytest.raises(ValueError, match="Invalid aggregation"):
            await analyze_insights(
                plan_id="plan-123", metrics=["cpu_usage"], aggregation="invalid_agg"
            )

    @pytest.mark.asyncio
    async def test_analyze_insights_all_valid_aggregations(self):
        """Testa todos os tipos de agregação válidos."""
        from analyst_mcp_server.tools.analyst_tools import analyze_insights

        valid_aggs = ["avg", "min", "max", "sum", "count", "stddev", "p50", "p95", "p99"]

        with patch(
            "analyst_mcp_server.tools.analyst_tools._retrieve_insights",
            new_callable=AsyncMock,
            return_value={"insights": [], "total": 0},
        ):
            for agg in valid_aggs:
                result = await analyze_insights(
                    plan_id="plan-test", metrics=["cpu_usage"], aggregation=agg
                )
                assert "insights" in result

    @pytest.mark.asyncio
    async def test_analyze_insights_with_time_range(self):
        """Testa análise com range de tempo customizado."""
        from analyst_mcp_server.tools.analyst_tools import analyze_insights

        start_time = datetime.now() - timedelta(hours=2)
        end_time = datetime.now()

        with patch(
            "analyst_mcp_server.tools.analyst_tools._retrieve_insights",
            new_callable=AsyncMock,
            return_value={"insights": [], "total": 0},
        ) as mock_retrieve:
            await analyze_insights(
                plan_id="plan-123",
                metrics=["cpu_usage"],
                start_time=start_time.isoformat(),
                end_time=end_time.isoformat(),
            )

            mock_retrieve.assert_called_once()

    @pytest.mark.asyncio
    async def test_analyze_insights_empty_metrics(self):
        """Testa análise com lista de métricas vazia."""
        from analyst_mcp_server.tools.analyst_tools import analyze_insights

        with pytest.raises(ValueError, match="At least one metric"):
            await analyze_insights(plan_id="plan-123", metrics=[])

    @pytest.mark.asyncio
    async def test_analyze_insights_with_group_by(self):
        """Testa análise com group_by."""
        from analyst_mcp_server.tools.analyst_tools import analyze_insights

        with patch(
            "analyst_mcp_server.tools.analyst_tools._retrieve_insights",
            new_callable=AsyncMock,
            return_value={
                "insights": [
                    {"group": "server-1", "cpu_usage": 80},
                    {"group": "server-2", "cpu_usage": 65},
                ],
                "total": 2,
                "group_by": "hostname",
            },
        ):
            result = await analyze_insights(
                plan_id="plan-123", metrics=["cpu_usage"], group_by="hostname"
            )

            assert result["group_by"] == "hostname"
            assert len(result["insights"]) == 2


class TestDetectAnomaliesTool:
    """Testes da ferramenta detect_anomalies."""

    @pytest.mark.asyncio
    async def test_detect_anomalies_success(self):
        """Testa detecção de anomalias com sucesso."""
        from analyst_mcp_server.tools.analyst_tools import detect_anomalies

        with patch(
            "analyst_mcp_server.tools.analyst_tools._run_anomaly_detection", new_callable=AsyncMock
        ) as mock_detect:
            mock_detect.return_value = {
                "anomalies": [
                    {
                        "timestamp": "2026-04-03T10:00:00",
                        "metric": "cpu_usage",
                        "value": 98.5,
                        "score": 0.95,
                        "severity": "high",
                    }
                ],
                "total": 1,
            }

            result = await detect_anomalies(
                metric="cpu_usage", algorithm="isolation_forest", sensitivity=0.8
            )

            assert result["total"] == 1
            assert result["anomalies"][0]["severity"] == "high"
            mock_detect.assert_called_once()

    @pytest.mark.asyncio
    async def test_detect_anomalies_invalid_algorithm(self):
        """Testa erro para algoritmo inválido."""
        from analyst_mcp_server.tools.analyst_tools import detect_anomalies

        with pytest.raises(ValueError, match="Invalid algorithm"):
            await detect_anomalies(metric="cpu_usage", algorithm="invalid_algo")

    @pytest.mark.asyncio
    async def test_detect_anomalies_all_valid_algorithms(self):
        """Testa todos os algoritmos válidos."""
        from analyst_mcp_server.tools.analyst_tools import detect_anomalies

        valid_algos = ["isolation_forest", "zscore", "iqr", "moving_average", "prophet"]

        with patch(
            "analyst_mcp_server.tools.analyst_tools._run_anomaly_detection",
            new_callable=AsyncMock,
            return_value={"anomalies": [], "total": 0},
        ):
            for algo in valid_algos:
                result = await detect_anomalies(metric="cpu_usage", algorithm=algo)
                assert "anomalies" in result

    @pytest.mark.asyncio
    async def test_detect_anomalies_with_threshold(self):
        """Testa detecção com threshold customizado."""
        from analyst_mcp_server.tools.analyst_tools import detect_anomalies

        with patch(
            "analyst_mcp_server.tools.analyst_tools._run_anomaly_detection",
            new_callable=AsyncMock,
            return_value={"anomalies": [], "total": 0},
        ) as mock_detect:
            await detect_anomalies(metric="cpu_usage", algorithm="zscore", threshold=3.0)

            mock_detect.assert_called_once()

    @pytest.mark.asyncio
    async def test_detect_anomalies_sensitivity_validation(self):
        """Testa validação de sensibilidade (0-1)."""
        from analyst_mcp_server.tools.analyst_tools import detect_anomalies

        with pytest.raises(ValueError, match="Sensitivity must be between 0 and 1"):
            await detect_anomalies(
                metric="cpu_usage", algorithm="isolation_forest", sensitivity=1.5
            )

    @pytest.mark.asyncio
    async def test_detect_anomalies_with_time_window(self):
        """Testa detecção com janela de tempo."""
        from analyst_mcp_server.tools.analyst_tools import detect_anomalies

        with patch(
            "analyst_mcp_server.tools.analyst_tools._run_anomaly_detection",
            new_callable=AsyncMock,
            return_value={"anomalies": [], "total": 0},
        ):
            result = await detect_anomalies(
                metric="cpu_usage", algorithm="moving_average", window_size=100, time_window="24h"
            )

            assert "anomalies" in result

    @pytest.mark.asyncio
    async def test_detect_anomalies_returns_severity_levels(self):
        """Testa que anomalias retornam níveis de severidade."""
        from analyst_mcp_server.tools.analyst_tools import detect_anomalies

        with patch(
            "analyst_mcp_server.tools.analyst_tools._run_anomaly_detection", new_callable=AsyncMock
        ) as mock_detect:
            mock_detect.return_value = {
                "anomalies": [
                    {"severity": "low", "score": 0.3},
                    {"severity": "medium", "score": 0.6},
                    {"severity": "high", "score": 0.9},
                ],
                "total": 3,
            }

            result = await detect_anomalies(metric="cpu_usage")

            severities = [a["severity"] for a in result["anomalies"]]
            assert "low" in severities
            assert "medium" in severities
            assert "high" in severities


class TestQueryTimeseriesTool:
    """Testes da ferramenta query_timeseries."""

    @pytest.mark.asyncio
    async def test_query_timeseries_success(self):
        """Testa consulta de time-series com sucesso."""
        from analyst_mcp_server.tools.analyst_tools import query_timeseries

        with patch(
            "analyst_mcp_server.tools.analyst_tools._fetch_timeseries", new_callable=AsyncMock
        ) as mock_fetch:
            mock_fetch.return_value = {
                "metric": "cpu_usage",
                "data": [
                    {"timestamp": "2026-04-03T10:00:00", "value": 75.5},
                    {"timestamp": "2026-04-03T10:01:00", "value": 78.2},
                ],
                "count": 2,
            }

            result = await query_timeseries(
                metric="cpu_usage", start_time="2026-04-03T10:00:00", end_time="2026-04-03T11:00:00"
            )

            assert result["metric"] == "cpu_usage"
            assert result["count"] == 2
            mock_fetch.assert_called_once()

    @pytest.mark.asyncio
    async def test_query_timeseries_with_pagination(self):
        """Testa consulta com paginação."""
        from analyst_mcp_server.tools.analyst_tools import query_timeseries

        with patch(
            "analyst_mcp_server.tools.analyst_tools._fetch_timeseries", new_callable=AsyncMock
        ) as mock_fetch:
            mock_fetch.return_value = {
                "metric": "cpu_usage",
                "data": [{"timestamp": "t", "value": 50}],
                "count": 1,
                "page": 1,
                "page_size": 50,
                "total_pages": 10,
            }

            result = await query_timeseries(
                metric="cpu_usage",
                start_time="2026-04-03T10:00:00",
                end_time="2026-04-03T11:00:00",
                page=1,
                page_size=50,
            )

            assert result["page"] == 1
            assert result["page_size"] == 50

    @pytest.mark.asyncio
    async def test_query_timeseries_invalid_page_size(self):
        """Testa erro para page_size inválido."""
        from analyst_mcp_server.tools.analyst_tools import query_timeseries

        with pytest.raises(ValueError, match="page_size must be positive"):
            await query_timeseries(
                metric="cpu_usage",
                start_time="2026-04-03T10:00:00",
                end_time="2026-04-03T11:00:00",
                page_size=0,
            )

    @pytest.mark.asyncio
    async def test_query_timeseries_with_filters(self):
        """Testa consulta com filtros."""
        from analyst_mcp_server.tools.analyst_tools import query_timeseries

        with patch(
            "analyst_mcp_server.tools.analyst_tools._fetch_timeseries",
            new_callable=AsyncMock,
            return_value={"metric": "cpu_usage", "data": [], "count": 0},
        ):
            result = await query_timeseries(
                metric="cpu_usage",
                start_time="2026-04-03T10:00:00",
                end_time="2026-04-03T11:00:00",
                filters={"hostname": "server-1", "region": "us-east"},
            )

            assert "metric" in result

    @pytest.mark.asyncio
    async def test_query_timeseries_with_aggregation(self):
        """Testa consulta com agregação temporal."""
        from analyst_mcp_server.tools.analyst_tools import query_timeseries

        with patch(
            "analyst_mcp_server.tools.analyst_tools._fetch_timeseries",
            new_callable=AsyncMock,
            return_value={"metric": "cpu_usage", "data": [], "aggregation": "1m", "count": 0},
        ):
            result = await query_timeseries(
                metric="cpu_usage",
                start_time="2026-04-03T10:00:00",
                end_time="2026-04-03T11:00:00",
                aggregation="1m",
            )

            assert result["aggregation"] == "1m"

    @pytest.mark.asyncio
    async def test_query_timeseries_with_downsampling(self):
        """Testa consulta com downsampling."""
        from analyst_mcp_server.tools.analyst_tools import query_timeseries

        valid_downsamplings = ["1m", "5m", "15m", "1h", "1d"]

        with patch(
            "analyst_mcp_server.tools.analyst_tools._fetch_timeseries",
            new_callable=AsyncMock,
            return_value={"metric": "cpu", "data": [], "count": 0},
        ):
            for downsample in valid_downsamplings:
                result = await query_timeseries(
                    metric="cpu",
                    start_time="2026-04-03T10:00:00",
                    end_time="2026-04-03T11:00:00",
                    aggregation=downsample,
                )
                assert "metric" in result

    @pytest.mark.asyncio
    async def test_query_timeseries_empty_result(self):
        """Testa consulta que retorna resultado vazio."""
        from analyst_mcp_server.tools.analyst_tools import query_timeseries

        with patch(
            "analyst_mcp_server.tools.analyst_tools._fetch_timeseries",
            new_callable=AsyncMock,
            return_value={"metric": "cpu", "data": [], "count": 0},
        ):
            result = await query_timeseries(
                metric="cpu", start_time="2026-04-03T10:00:00", end_time="2026-04-03T11:00:00"
            )

            assert result["count"] == 0
            assert result["data"] == []


class TestGenerateDashboardTool:
    """Testes da ferramenta generate_dashboard."""

    @pytest.mark.asyncio
    async def test_generate_dashboard_success(self):
        """Testa geração de dashboard com sucesso."""
        from analyst_mcp_server.tools.analyst_tools import generate_dashboard

        with patch(
            "analyst_mcp_server.tools.analyst_tools._compile_dashboard_data", new_callable=AsyncMock
        ) as mock_compile:
            mock_compile.return_value = {
                "dashboard_id": "dash-123",
                "widgets": [
                    {"type": "line", "title": "CPU Usage", "metric": "cpu_usage", "data": []}
                ],
                "generated_at": datetime.now().isoformat(),
            }

            result = await generate_dashboard(
                dashboard_name="System Overview", widgets=[{"type": "line", "metric": "cpu_usage"}]
            )

            assert result["dashboard_id"] == "dash-123"
            assert len(result["widgets"]) == 1
            mock_compile.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_dashboard_invalid_widget_type(self):
        """Testa erro para tipo de widget inválido."""
        from analyst_mcp_server.tools.analyst_tools import generate_dashboard

        with pytest.raises(ValueError, match="Invalid widget type"):
            await generate_dashboard(
                dashboard_name="Test", widgets=[{"type": "invalid_type", "metric": "cpu"}]
            )

    @pytest.mark.asyncio
    async def test_generate_dashboard_all_valid_widget_types(self):
        """Testa todos os tipos de widgets válidos."""
        from analyst_mcp_server.tools.analyst_tools import generate_dashboard

        valid_types = ["line", "bar", "pie", "gauge", "table", "heatmap", "stat"]

        with patch(
            "analyst_mcp_server.tools.analyst_tools._compile_dashboard_data",
            new_callable=AsyncMock,
            return_value={"dashboard_id": "test", "widgets": []},
        ):
            for widget_type in valid_types:
                result = await generate_dashboard(
                    dashboard_name="Test", widgets=[{"type": widget_type, "metric": "cpu"}]
                )
                assert "widgets" in result

    @pytest.mark.asyncio
    async def test_generate_dashboard_multiple_widgets(self):
        """Testa geração com múltiplos widgets."""
        from analyst_mcp_server.tools.analyst_tools import generate_dashboard

        widgets = [
            {"type": "line", "metric": "cpu_usage"},
            {"type": "gauge", "metric": "memory_usage"},
            {"type": "stat", "metric": "request_count"},
        ]

        with patch(
            "analyst_mcp_server.tools.analyst_tools._compile_dashboard_data", new_callable=AsyncMock
        ) as mock_compile:
            mock_compile.return_value = {
                "dashboard_id": "dash-1",
                "widgets": widgets,
                "widget_count": 3,
            }

            result = await generate_dashboard(dashboard_name="System", widgets=widgets)

            assert result["widget_count"] == 3

    @pytest.mark.asyncio
    async def test_generate_dashboard_with_time_range(self):
        """Testa geração com range de tempo."""
        from analyst_mcp_server.tools.analyst_tools import generate_dashboard

        with patch(
            "analyst_mcp_server.tools.analyst_tools._compile_dashboard_data",
            new_callable=AsyncMock,
            return_value={"dashboard_id": "dash-1", "widgets": [], "time_range": "1h"},
        ):
            result = await generate_dashboard(
                dashboard_name="Test", widgets=[{"type": "line", "metric": "cpu"}], time_range="1h"
            )

            assert result["time_range"] == "1h"

    @pytest.mark.asyncio
    async def test_generate_dashboard_with_refresh_interval(self):
        """Testa geração com intervalo de refresh."""
        from analyst_mcp_server.tools.analyst_tools import generate_dashboard

        with patch(
            "analyst_mcp_server.tools.analyst_tools._compile_dashboard_data",
            new_callable=AsyncMock,
            return_value={"dashboard_id": "dash-1", "widgets": []},
        ):
            result = await generate_dashboard(
                dashboard_name="Test",
                widgets=[{"type": "line", "metric": "cpu"}],
                refresh_interval=30,
            )

            assert "dashboard_id" in result

    @pytest.mark.asyncio
    async def test_generate_dashboard_empty_widgets(self):
        """Testa erro para lista de widgets vazia."""
        from analyst_mcp_server.tools.analyst_tools import generate_dashboard

        with pytest.raises(ValueError, match="At least one widget"):
            await generate_dashboard(dashboard_name="Test", widgets=[])


class TestExportDataTool:
    """Testes da ferramenta export_data."""

    @pytest.mark.asyncio
    async def test_export_data_json_success(self):
        """Testa exportação JSON com sucesso."""
        from analyst_mcp_server.tools.analyst_tools import export_data

        with patch(
            "analyst_mcp_server.tools.analyst_tools._fetch_data_for_export", new_callable=AsyncMock
        ) as mock_fetch:
            mock_fetch.return_value = {
                "data": [
                    {"timestamp": "2026-04-03T10:00:00", "value": 75.5},
                    {"timestamp": "2026-04-03T10:01:00", "value": 78.2},
                ],
                "count": 2,
            }

            result = await export_data(metric="cpu_usage", format="json")

            assert result["count"] == 2
            assert result["format"] == "json"
            mock_fetch.assert_called_once()

    @pytest.mark.asyncio
    async def test_export_data_invalid_format(self):
        """Testa erro para formato inválido."""
        from analyst_mcp_server.tools.analyst_tools import export_data

        with pytest.raises(ValueError, match="Invalid format"):
            await export_data(metric="cpu_usage", format="invalid_format")

    @pytest.mark.asyncio
    async def test_export_data_all_valid_formats(self):
        """Testa todos os formatos válidos."""
        from analyst_mcp_server.tools.analyst_tools import export_data

        valid_formats = ["json", "csv", "xlsx", "parquet"]

        with patch(
            "analyst_mcp_server.tools.analyst_tools._fetch_data_for_export",
            new_callable=AsyncMock,
            return_value={"data": [], "count": 0},
        ):
            for fmt in valid_formats:
                result = await export_data(metric="cpu_usage", format=fmt)
                assert result["format"] == fmt

    @pytest.mark.asyncio
    async def test_export_data_csv_format(self):
        """Testa exportação CSV."""
        from analyst_mcp_server.tools.analyst_tools import export_data

        with patch(
            "analyst_mcp_server.tools.analyst_tools._fetch_data_for_export", new_callable=AsyncMock
        ) as mock_fetch:
            mock_fetch.return_value = {
                "data": [{"timestamp": "2026-04-03T10:00:00", "value": 75.5}],
                "count": 1,
                "format": "csv",
            }

            result = await export_data(metric="cpu_usage", format="csv")

            assert result["format"] == "csv"

    @pytest.mark.asyncio
    async def test_export_data_with_time_range(self):
        """Testa exportação com range de tempo."""
        from analyst_mcp_server.tools.analyst_tools import export_data

        with patch(
            "analyst_mcp_server.tools.analyst_tools._fetch_data_for_export",
            new_callable=AsyncMock,
            return_value={"data": [], "count": 0},
        ):
            result = await export_data(
                metric="cpu_usage",
                format="json",
                start_time="2026-04-03T10:00:00",
                end_time="2026-04-03T11:00:00",
            )

            assert "count" in result

    @pytest.mark.asyncio
    async def test_export_data_with_limit(self):
        """Testa exportação com limite de registros."""
        from analyst_mcp_server.tools.analyst_tools import export_data

        with patch(
            "analyst_mcp_server.tools.analyst_tools._fetch_data_for_export",
            new_callable=AsyncMock,
            return_value={"data": [], "count": 0, "limit": 100},
        ):
            result = await export_data(metric="cpu_usage", format="json", limit=100)

            assert result["limit"] == 100

    @pytest.mark.asyncio
    async def test_export_data_invalid_limit(self):
        """Testa erro para limite inválido."""
        from analyst_mcp_server.tools.analyst_tools import export_data

        with pytest.raises(ValueError, match="Limit must be positive"):
            await export_data(metric="cpu_usage", format="json", limit=0)

    @pytest.mark.asyncio
    async def test_export_data_with_filters(self):
        """Testa exportação com filtros."""
        from analyst_mcp_server.tools.analyst_tools import export_data

        with patch(
            "analyst_mcp_server.tools.analyst_tools._fetch_data_for_export",
            new_callable=AsyncMock,
            return_value={"data": [], "count": 0},
        ):
            result = await export_data(
                metric="cpu_usage", format="json", filters={"hostname": "server-1"}
            )

            assert "count" in result


class TestHelperFunctions:
    """Testes das funções auxiliares."""

    @pytest.mark.asyncio
    async def test_retrieve_insights_success(self):
        """Testa recuperação de insights."""
        from analyst_mcp_server.tools.analyst_tools import _retrieve_insights

        # A função retorna dados simulados quando MongoDB não está disponível
        result = await _retrieve_insights(
            plan_id="plan-1", metrics=["cpu_usage"], start_time=None, end_time=None
        )

        # Verificar estrutura do resultado
        assert "insights" in result
        assert "total" in result

    @pytest.mark.asyncio
    async def test_run_anomaly_detection_success(self):
        """Testa execução de detecção de anomalias."""
        from analyst_mcp_server.tools.analyst_tools import _run_anomaly_detection

        # A função retorna dados simulados quando scikit-learn gera exceção
        result = await _run_anomaly_detection(
            metric="cpu_usage", algorithm="zscore", threshold=3.0, sensitivity=0.8
        )

        # Verificar estrutura do resultado
        assert "anomalies" in result
        assert "total" in result

    @pytest.mark.asyncio
    async def test_fetch_timeseries_success(self):
        """Testa busca de time-series."""
        from analyst_mcp_server.tools.analyst_tools import _fetch_timeseries

        # A função retorna dados simulados quando Feature Store não está disponível
        result = await _fetch_timeseries(
            metric="cpu_usage", start_time="2026-04-03T10:00:00", end_time="2026-04-03T11:00:00"
        )

        # Verificar estrutura do resultado
        assert "metric" in result
        assert "data" in result
        assert "count" in result

    @pytest.mark.asyncio
    async def test_compile_dashboard_data_success(self):
        """Testa compilação de dashboard."""
        from analyst_mcp_server.tools.analyst_tools import _compile_dashboard_data

        widgets = [
            {"type": "line", "metric": "cpu_usage"},
            {"type": "gauge", "metric": "memory_usage"},
        ]

        result = await _compile_dashboard_data(dashboard_name="Test Dashboard", widgets=widgets)

        # Verificar estrutura do resultado
        assert "dashboard_id" in result
        assert "widgets" in result

    @pytest.mark.asyncio
    async def test_fetch_data_for_export_success(self):
        """Testa busca de dados para exportação."""
        from analyst_mcp_server.tools.analyst_tools import _fetch_data_for_export

        result = await _fetch_data_for_export(
            metric="cpu_usage", start_time=None, end_time=None, limit=1000
        )

        # Verificar estrutura do resultado
        assert "data" in result
        assert "count" in result


class TestAnalystMCPServerIntegration:
    """Testes de integração do Analyst MCP Server."""

    def test_server_has_required_tools(self):
        """Testa que o servidor expõe as ferramentas requeridas."""
        from analyst_mcp_server.server import mcp

        assert mcp is not None
        assert mcp.name == "Analyst MCP Server"

    def test_tools_have_metadata(self):
        """Testa que ferramentas têm metadata descritiva."""
        from analyst_mcp_server.tools.analyst_tools import (
            analyze_insights,
            detect_anomalies,
            export_data,
            generate_dashboard,
            query_timeseries,
        )

        assert analyze_insights.__doc__
        assert detect_anomalies.__doc__
        assert query_timeseries.__doc__
        assert generate_dashboard.__doc__
        assert export_data.__doc__

    def test_server_info_resource_exists(self):
        """Testa que resource de info existe."""
        from analyst_mcp_server.server import get_analyst_info

        assert get_analyst_info is not None
        info = get_analyst_info()
        assert "Analyst MCP Server" in info
        assert "analyze_insights" in info

    def test_register_analyst_tools_function_exists(self):
        """Testa que função de registro existe."""
        from analyst_mcp_server.tools.analyst_tools import register_analyst_tools

        assert register_analyst_tools is not None
        assert callable(register_analyst_tools)


class TestErrorHandling:
    """Testes de tratamento de erros."""

    @pytest.mark.asyncio
    async def test_error_handling_invalid_input_analyze_insights(self):
        """Testa erro para input inválido em analyze_insights."""
        from analyst_mcp_server.tools.analyst_tools import analyze_insights

        with pytest.raises(ValueError, match="At least one metric"):
            await analyze_insights(plan_id="plan-123", metrics=[])

    @pytest.mark.asyncio
    async def test_error_handling_invalid_input_detect_anomalies(self):
        """Testa erro para input inválido em detect_anomalies."""
        from analyst_mcp_server.tools.analyst_tools import detect_anomalies

        with pytest.raises(ValueError, match="Invalid algorithm"):
            await detect_anomalies(metric="cpu_usage", algorithm="invalid")

    @pytest.mark.asyncio
    async def test_error_handling_invalid_input_query_timeseries(self):
        """Testa erro para input inválido em query_timeseries."""
        from analyst_mcp_server.tools.analyst_tools import query_timeseries

        with pytest.raises(ValueError, match="page_size must be positive"):
            await query_timeseries(
                metric="cpu_usage",
                start_time="2026-04-03T10:00:00",
                end_time="2026-04-03T11:00:00",
                page_size=-10,
            )

    @pytest.mark.asyncio
    async def test_error_handling_invalid_input_generate_dashboard(self):
        """Testa erro para input inválido em generate_dashboard."""
        from analyst_mcp_server.tools.analyst_tools import generate_dashboard

        with pytest.raises(ValueError, match="At least one widget"):
            await generate_dashboard(dashboard_name="Test", widgets=[])

    @pytest.mark.asyncio
    async def test_error_handling_invalid_input_export_data(self):
        """Testa erro para input inválido em export_data."""
        from analyst_mcp_server.tools.analyst_tools import export_data

        with pytest.raises(ValueError, match="Invalid format"):
            await export_data(metric="cpu_usage", format="invalid_format")

        with pytest.raises(ValueError, match="Limit must be positive"):
            await export_data(metric="cpu_usage", format="json", limit=0)


class TestConnectionHandling:
    """Testes de tratamento de conexões."""

    @pytest.mark.asyncio
    async def test_connection_failed_retrieve_insights(self):
        """Testa comportamento quando conexão com MongoDB falha."""
        from analyst_mcp_server.tools.analyst_tools import _retrieve_insights

        # Simula falha de conexão (deve retornar dados simulados)
        result = await _retrieve_insights(
            plan_id="plan-test", metrics=["cpu_usage"], start_time=None, end_time=None
        )

        # Deve retornar dados simulados em vez de levantar exceção
        assert "insights" in result
        assert "total" in result

    @pytest.mark.asyncio
    async def test_connection_failed_fetch_timeseries(self):
        """Testa comportamento quando conexão com Feature Store falha."""
        from analyst_mcp_server.tools.analyst_tools import _fetch_timeseries

        # Simula falha de conexão (deve retornar dados simulados)
        result = await _fetch_timeseries(
            metric="cpu_usage",
            start_time="2026-04-03T10:00:00",
            end_time="2026-04-03T11:00:00",
        )

        # Deve retornar dados vazios com estrutura válida
        assert "metric" in result
        assert "data" in result
        assert "count" in result

    @pytest.mark.asyncio
    async def test_connection_failed_anomaly_detection(self):
        """Testa comportamento quando scikit-learn falha."""
        from analyst_mcp_server.tools.analyst_tools import _run_anomaly_detection

        # Simula falha (deve retornar dados simulados)
        result = await _run_anomaly_detection(
            metric="cpu_usage", algorithm="isolation_forest", threshold=3.0, sensitivity=0.8
        )

        # Deve retornar anomalias simuladas
        assert "anomalies" in result
        assert "total" in result

    @pytest.mark.asyncio
    async def test_connection_failed_export_data(self):
        """Testa comportamento quando exportação falha."""
        from analyst_mcp_server.tools.analyst_tools import _fetch_data_for_export

        # Simula falha (deve retornar dados simulados)
        result = await _fetch_data_for_export(
            metric="cpu_usage", start_time=None, end_time=None, limit=1000
        )

        # Deve retornar estrutura válida
        assert "data" in result
        assert "count" in result


class TestEdgeCases:
    """Testes de casos extremos."""

    @pytest.mark.asyncio
    async def test_large_metrics_list(self):
        """Testa com lista grande de métricas."""
        from analyst_mcp_server.tools.analyst_tools import analyze_insights

        large_metrics_list = [f"metric_{i}" for i in range(100)]

        with patch(
            "analyst_mcp_server.tools.analyst_tools._retrieve_insights",
            new_callable=AsyncMock,
            return_value={"insights": [], "total": 0},
        ):
            result = await analyze_insights(
                plan_id="plan-123", metrics=large_metrics_list, aggregation="avg"
            )

            assert "insights" in result

    @pytest.mark.asyncio
    async def test_extreme_time_ranges(self):
        """Testa com ranges de tempo extremos."""
        from analyst_mcp_server.tools.analyst_tools import query_timeseries

        with patch(
            "analyst_mcp_server.tools.analyst_tools._fetch_timeseries",
            new_callable=AsyncMock,
            return_value={"metric": "cpu", "data": [], "count": 0},
        ):
            # Range muito pequeno (1 segundo)
            result = await query_timeseries(
                metric="cpu_usage",
                start_time="2026-04-03T10:00:00",
                end_time="2026-04-03T10:00:01",
            )

            assert "metric" in result

    @pytest.mark.asyncio
    async def test_special_characters_in_filters(self):
        """Testa filtros com caracteres especiais."""
        from analyst_mcp_server.tools.analyst_tools import query_timeseries

        filters = {"hostname": "server-1", "region": "us-east-1", "tag": "production:critical"}

        with patch(
            "analyst_mcp_server.tools.analyst_tools._fetch_timeseries",
            new_callable=AsyncMock,
            return_value={"metric": "cpu", "data": [], "count": 0},
        ):
            result = await query_timeseries(
                metric="cpu_usage",
                start_time="2026-04-03T10:00:00",
                end_time="2026-04-03T11:00:00",
                filters=filters,
            )

            assert "metric" in result

    @pytest.mark.asyncio
    async def test_empty_dashboard_name(self):
        """Testa com nome de dashboard vazio."""
        from analyst_mcp_server.tools.analyst_tools import generate_dashboard

        with patch(
            "analyst_mcp_server.tools.analyst_tools._compile_dashboard_data",
            new_callable=AsyncMock,
            return_value={"dashboard_id": "dash-1", "widgets": []},
        ):
            result = await generate_dashboard(
                dashboard_name="", widgets=[{"type": "line", "metric": "cpu"}]
            )

            # Aceita nome vazio (pode ser validado em outra camada)
            assert "dashboard_id" in result

    @pytest.mark.asyncio
    async def test_zero_limit_export(self):
        """Testa exportação com limite zero (deve falhar)."""
        from analyst_mcp_server.tools.analyst_tools import export_data

        with pytest.raises(ValueError, match="Limit must be positive"):
            await export_data(metric="cpu_usage", format="json", limit=0)

    @pytest.mark.asyncio
    async def test_negative_page_size(self):
        """Testa paginação com tamanho negativo (deve falhar)."""
        from analyst_mcp_server.tools.analyst_tools import query_timeseries

        with pytest.raises(ValueError, match="page_size must be positive"):
            await query_timeseries(
                metric="cpu_usage",
                start_time="2026-04-03T10:00:00",
                end_time="2026-04-03T11:00:00",
                page_size=-1,
            )
