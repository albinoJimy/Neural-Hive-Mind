"""Parsers para diferentes linguagens."""

from .javascript_parser import JavaScriptParser
from .json_parser import JSONParser
from .typescript_parser import TypeScriptParser
from .yaml_parser import YAMLParser

__all__ = [
    "JavaScriptParser",
    "TypeScriptParser",
    "YAMLParser",
    "JSONParser",
]
