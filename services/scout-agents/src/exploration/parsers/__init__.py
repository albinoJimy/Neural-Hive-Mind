"""Parsers para diferentes linguagens."""

from .javascript_parser import JavaScriptParser
from .typescript_parser import TypeScriptParser
from .yaml_parser import YAMLParser
from .json_parser import JSONParser

__all__ = [
    'JavaScriptParser',
    'TypeScriptParser',
    'YAMLParser',
    'JSONParser',
]
