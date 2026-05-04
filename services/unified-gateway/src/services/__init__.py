"""Serviços do Unified Gateway."""

from .context_builder import (
    ContextBuilder,
    ContextBuilderConfig,
    ContextBuilderError,
    build_request_context,
    build_rich_context,
    get_context_builder,
)

__all__ = [
    "ContextBuilder",
    "ContextBuilderConfig",
    "ContextBuilderError",
    "build_request_context",
    "build_rich_context",
    "get_context_builder",
]
