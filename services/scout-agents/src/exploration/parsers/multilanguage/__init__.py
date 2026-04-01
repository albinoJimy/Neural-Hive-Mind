"""
Multi-language parsers usando tree-sitter.

Suporta Java, C#, Go, C/C++, Rust.
"""
from .cpp_parser import CppParser
from .csharp_parser import CSharpParser
from .go_parser import GoParser
from .java_parser import JavaParser
from .rust_parser import RustParser

__all__ = ["JavaParser", "CSharpParser", "GoParser", "CppParser", "RustParser"]
