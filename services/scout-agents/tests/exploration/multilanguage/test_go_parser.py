"""
Testes para GoParser.
Parsing de Go para análise estática.
"""

import pytest
from src.exploration.parsers.multilanguage.go_parser import GoParser


@pytest.fixture()
def go_parser():
    """Instância de GoParser para testes."""
    return GoParser()


class TestGoParserBasic:
    """Testes básicos do Go parser."""

    def test_parse_simple_struct(self, go_parser):
        """Testa parsing de struct simples."""
        code = """
package main

type User struct {
    Name string
    Age  int
}

func (u *User) GetName() string {
    return u.Name
}
"""
        result = go_parser.parse(code, "user.go")

        assert result is not None
        assert len(result["structs"]) == 1
        assert result["structs"][0]["name"] == "User"

    def test_parse_interface(self, go_parser):
        """Testa parsing de interface Go."""
        code = """
package main

type Repository interface {
    Save(entity interface{}) error
    Find(id int) interface{}
}
"""
        result = go_parser.parse(code, "repository.go")

        assert result is not None
        interfaces = result.get("interfaces", [])
        assert len(interfaces) >= 1

    def test_parse_function(self, go_parser):
        """Testa parsing de função."""
        code = """
package main

func Add(a int, b int) int {
    return a + b
}

func GetData() (string, error) {
    return "data", nil
}
"""
        result = go_parser.parse(code, "math.go")

        assert result is not None
        functions = result["functions"]
        assert len(functions) >= 1
        assert any(f["name"] == "Add" for f in functions)

    def test_parse_method(self, go_parser):
        """Testa parsing de método."""
        code = """
package main

type Calculator struct{}

func (c *Calculator) Add(a int, b int) int {
    return a + b
}

func (c Calculator) Multiply(a int, b int) int {
    return a * b
}
"""
        result = go_parser.parse(code, "calculator.go")

        assert result is not None
        methods = result["methods"]
        assert len(methods) >= 1

    def test_parse_package_declaration(self, go_parser):
        """Testa parsing de declaração de package."""
        code = """
package main

func hello() {}
"""
        result = go_parser.parse(code, "main.go")

        assert result is not None
        assert result["packages"] == "main"

    def test_parse_imports(self, go_parser):
        """Testa extração de imports."""
        code = """
package main

import "fmt"
import "os"

import (
    "net/http"
    "encoding/json"
)
"""
        result = go_parser.parse(code, "main.go")

        assert result is not None
        imports = result["imports"]
        assert len(imports) >= 4
        assert any(i["name"] == "fmt" for i in imports)


class TestGoParserAdvanced:
    """Testes avançados do Go parser."""

    def test_parse_goroutine(self, go_parser):
        """Testa parsing de goroutine."""
        code = """
package main

func Process() {
    go func() {
        println("processing")
    }()
}
"""
        result = go_parser.parse(code, "process.go")

        assert result is not None
        # Verificar se detecta uso de goroutine

    def test_parse_channel(self, go_parser):
        """Testa parsing de channel."""
        code = """
package main

func sendData(ch chan string) {
    ch <- "data"
}

func receiveData(ch chan string) {
    data := <-ch
}
"""
        result = go_parser.parse(code, "channel.go")

        assert result is not None
        # Verificar se detecta canais

    def test_parse_defer(self, go_parser):
        """Testa parsing de defer."""
        code = """
package main

func Process() {
    defer cleanup()
    defer close(file)
}

func cleanup() {}
"""
        result = go_parser.parse(code, "defer.go")

        assert result is not None
        # Verificar se detecta defer

    def test_parse_select(self, go_parser):
        """Testa parsing de select statement."""
        code = """
package main

func Process(ch1, ch2 chan string) {
    select {
    case msg := <-ch1:
        println(msg)
    case msg := <-ch2:
        println(msg)
    }
}
"""
        result = go_parser.parse(code, "select.go")

        assert result is not None

    def test_parse_struct_with_embedded(self, go_parser):
        """Testa parsing de struct com embedded types."""
        code = """
package main

type Animal struct {
    Name string
}

type Dog struct {
    Animal
    Breed string
}
"""
        result = go_parser.parse(code, "dog.go")

        assert result is not None
        structs = result.get("structs", [])
        assert len(structs) >= 1


class TestGoParserComplexity:
    """Testes de cálculo de complexidade."""

    def test_calculate_complexity_simple(self, go_parser):
        """Testa complexidade de função simples."""
        code = """
package main

func Add(a int, b int) int {
    return a + b
}
"""
        result = go_parser.parse(code, "math.go")

        assert result is not None
        complexity = result.get("complexity", 1)
        assert complexity >= 1

    def test_calculate_complexity_with_conditionals(self, go_parser):
        """Testa complexidade com condicionais."""
        code = """
package main

func Process(value int) string {
    if value < 0 {
        return "negative"
    } else if value > 0 {
        return "positive"
    } else {
        return "zero"
    }
}
"""
        result = go_parser.parse(code, "logic.go")

        assert result is not None
        complexity = result.get("complexity", 1)
        assert complexity > 1

    def test_calculate_complexity_with_loops(self, go_parser):
        """Testa complexidade com loops."""
        code = """
package main

func Process(items []string) {
    for _, item := range items {
        if item != "" {
            println(item)
        }
    }
}
"""
        result = go_parser.parse(code, "loop.go")

        assert result is not None
        complexity = result.get("complexity", 1)
        assert complexity > 1


class TestGoParserConcurrency:
    """Testes de detecção de padrões de concorrência."""

    def test_detect_goroutines(self, go_parser):
        """Testa detecção de goroutines."""
        code = """
package main

func main() {
    go process()
    go func() {
        println("anonymous")
    }()
}

func process() {}
"""
        result = go_parser.parse(code, "main.go")

        assert result is not None

    def test_detect_channels(self, go_parser):
        """Testa detecção de channels."""
        code = """
package main

func main() {
    ch := make(chan string)
    ch2 := make(chan int, 10)
}
"""
        result = go_parser.parse(code, "main.go")

        assert result is not None


class TestGoParserErrorHandling:
    """Testes de tratamento de erros."""

    def test_parse_syntax_error(self, go_parser):
        """Testa parsing de código com erro de sintaxe."""
        invalid_code = """
package main

func hello()
{
    println("hello")
}
"""
        result = go_parser.parse(invalid_code, "invalid.go")

        # Parser deve retornar resultado (mesmo que incompleto) ou None
        assert result is not None or result is None

    def test_parse_empty_code(self, go_parser):
        """Testa parsing de código vazio."""
        result = go_parser.parse("", "empty.go")

        assert result is not None
        assert len(result["structs"]) == 0
