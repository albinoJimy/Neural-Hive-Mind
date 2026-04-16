"""Aplicação principal Fluxo G Dashboard."""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import structlog

from config.settings import get_settings
from api.routers.dashboard import router as api_router

settings = get_settings()

# Configurar structlog
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerencia ciclo de vida da aplicação."""
    logger.info(
        "starting_fluxo_g_dashboard",
        version=settings.service_version,
        port=settings.port,
    )
    yield
    logger.info("shutting_down_fluxo_g_dashboard")


app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Templates
templates = Jinja2Templates(directory="src/templates")

# API Router
app.include_router(api_router)


@app.get("/", response_class=HTMLResponse)
async def dashboard_home(request: Request):
    """Página principal do dashboard."""
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "title": "Fluxo G Dashboard",
            "refresh_interval": settings.refresh_interval_seconds,
        },
    )


@app.get("/health")
async def health():
    """Health check."""
    return {"status": "healthy", "service": settings.service_name}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
