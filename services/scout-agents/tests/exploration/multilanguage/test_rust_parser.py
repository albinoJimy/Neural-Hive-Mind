"""
Testes para RustParser.
Parsing de Rust para análise estática.
"""

import pytest
from src.exploration.parsers.multilanguage.rust_parser import RustParser


@pytest.fixture()
def rust_parser():
    return RustParser()


class TestRustParserBasic:
    """Testes básicos do Rust parser."""

    def test_parse_simple_struct(self, rust_parser):
        """Testa parsing de struct simples."""
        code = """
struct User {
    name: String,
    age: u32,
}
"""
        result = rust_parser.parse(code, "user.rs")

        assert result is not None
        assert len(result["structs"]) == 1
        assert result["structs"][0]["name"] == "User"

    def test_parse_enum(self, rust_parser):
        """Testa parsing de enum."""
        code = """
enum Option {
    Some(T),
    None,
}

enum HttpStatus {
    Ok = 200,
    NotFound = 404,
}
"""
        result = rust_parser.parse(code, "enums.rs")

        assert result is not None
        enums = result.get("enums", [])
        assert len(enums) >= 1

    def test_parse_trait(self, rust_parser):
        """Testa parsing de trait."""
        code = """
trait Repository {
    fn save(&self, entity: &str) -> Result<(), Error>;
    fn find(&self, id: u32) -> Option<&User>;
}
"""
        result = rust_parser.parse(code, "repository.rs")

        assert result is not None
        traits = result.get("traits", [])
        assert len(traits) >= 1

    def test_parse_impl_block(self, rust_parser):
        """Testa parsing de impl block."""
        code = """
impl User {
    fn new(name: String) -> Self {
        User { name, age: 0 }
    }
}

impl Repository for User {
    fn save(&self, entity: &str) -> Result<(), Error> {
        Ok(())
    }
}
"""
        result = rust_parser.parse(code, "user.rs")

        assert result is not None

    def test_parse_function(self, rust_parser):
        """Testa parsing de função."""
        code = """
fn add(a: i32, b: i32) -> i32 {
    a + b
}

pub async fn get_data() -> String {
    String::from("data")
}
"""
        result = rust_parser.parse(code, "math.rs")

        assert result is not None
        functions = result["functions"]
        assert len(functions) >= 1

    def test_parse_macros(self, rust_parser):
        """Testa parsing de macros."""
        code = """
#[derive(Debug, Clone)]
struct User {
    name: String,
}

println!("Hello, {}!", name);
vec![1, 2, 3];
"""
        result = rust_parser.parse(code, "macros.rs")

        assert result is not None


class TestRustParserComplexity:
    """Testes de complexidade."""

    def test_calculate_complexity_simple(self, rust_parser):
        """Testa complexidade simples."""
        code = """
fn add(a: i32, b: i32) -> i32 {
    a + b
}
"""
        result = rust_parser.parse(code, "math.rs")

        assert result is not None
        complexity = result.get("complexity", 1)
        assert complexity >= 1

    def test_calculate_complexity_with_match(self, rust_parser):
        """Testa complexidade com match."""
        code = """
fn process(value: Option<i32>) -> i32 {
    match value {
        Some(v) => v,
        None => 0,
    }
}
"""
        result = rust_parser.parse(code, "process.rs")

        assert result is not None
        complexity = result.get("complexity", 1)
        assert complexity > 1


class TestRustParserErrorHandling:
    """Testes de erros."""

    def test_parse_empty_code(self, rust_parser):
        """Testa código vazio."""
        result = rust_parser.parse("", "empty.rs")

        assert result is not None
        assert len(result["structs"]) == 0
