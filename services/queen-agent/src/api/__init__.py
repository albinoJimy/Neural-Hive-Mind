from .decisions import router as decisions_router
from .election import router as election_router
from .exceptions import router as exceptions_router
from .health import router as health_router
from .mcp import router as mcp_router
from .status import router as status_router
from .workers import router as workers_router

__all__ = [
    "decisions_router",
    "election_router",
    "exceptions_router",
    "health_router",
    "mcp_router",
    "status_router",
    "workers_router",
]
