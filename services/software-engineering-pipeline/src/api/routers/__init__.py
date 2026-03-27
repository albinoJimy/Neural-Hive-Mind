from src.api.routers.health import router as health_router
from src.api.routers.pipeline_runs import router as pipeline_runs_router
from src.api.routers.manifests import router as manifests_router
from src.api.routers.anomalies import router as anomalies_router
from src.api.routers.insights import router as insights_router

__all__ = [
    "health_router",
    "pipeline_runs_router",
    "manifests_router",
    "anomalies_router",
    "insights_router",
]
