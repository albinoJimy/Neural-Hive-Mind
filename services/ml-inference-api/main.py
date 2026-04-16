"""ML Inference API - API de Inferência de Modelos ML."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog

logger = structlog.get_logger(__name__)


def create_app() -> FastAPI:
    """Cria aplicação FastAPI."""
    app = FastAPI(
        title="ML Inference API",
        description="API de Inferência de Modelos ML",
        version="0.1.0",
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health():
        return {"status": "healthy", "service": "ml-inference-api"}

    @app.get("/")
    async def root():
        return {"message": "ML Inference API", "version": "0.1.0"}

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8020)
