"""
Testes para CppParser (C/C++).
Parsing de C/C++ para análise estática.
"""
import pytest

from src.exploration.parsers.multilanguage.cpp_parser import CppParser


@pytest.fixture
def cpp_parser():
    """Instância de CppParser para testes."""
    return CppParser()


class TestCppParserBasic:
    """Testes básicos do C++ parser."""

    def test_parse_simple_class(self, cpp_parser):
        """Testa parsing de classe simples."""
        code = """
class UserService {
private:
    std::string name;

public:
    UserService(std::string n) : name(n) {}

    std::string GetName() {
        return name;
    }
};
"""
        result = cpp_parser.parse(code, "UserService.cpp")

        assert result is not None
        assert len(result["classes"]) == 1
        assert result["classes"][0]["name"] == "UserService"

    def test_parse_struct(self, cpp_parser):
        """Testa parsing de struct C/C++."""
        code = """
struct User {
    char name[50];
    int age;
};

struct Point {
    int x;
    int y;
};
"""
        result = cpp_parser.parse(code, "user.cpp")

        assert result is not None
        structs = result.get("structs", [])
        assert len(structs) >= 1

    def test_parse_function(self, cpp_parser):
        """Testa parsing de função."""
        code = """
int add(int a, int b) {
    return a + b;
}

std::string getName() {
    return "Test";
}
"""
        result = cpp_parser.parse(code, "functions.cpp")

        assert result is not None
        functions = result["functions"]
        assert len(functions) >= 1

    def test_parse_template(self, cpp_parser):
        """Testa parsing de template."""
        code = """
template<typename T>
class Container {
    T data;
public:
    T get() { return data; }
};

template<typename K, typename V>
class Map {
    // implementation
};
"""
        result = cpp_parser.parse(code, "container.hpp")

        assert result is not None
        classes = result.get("classes", [])
        assert len(classes) >= 1

    def test_parse_namespace(self, cpp_parser):
        """Testa parsing de namespace."""
        code = """
namespace Example {
    class Service {
    public:
        void serve() {}
    };
}
"""
        result = cpp_parser.parse(code, "service.cpp")

        assert result is not None
        assert "Example" in result.get("namespaces", "")

    def test_parse_includes(self, cpp_parser):
        """Testa extração de includes."""
        code = """
#include <iostream>
#include <vector>
#include "myheader.h"
"""
        result = cpp_parser.parse(code, "main.cpp")

        assert result is not None
        includes = result["imports"]
        assert len(includes) >= 3


class TestCppParserComplexity:
    """Testes de cálculo de complexidade."""

    def test_calculate_complexity_simple(self, cpp_parser):
        """Testa complexidade de função simples."""
        code = """
int add(int a, int b) {
    return a + b;
}
"""
        result = cpp_parser.parse(code, "math.cpp")

        assert result is not None
        complexity = result.get("complexity", 1)
        assert complexity >= 1

    def test_calculate_complexity_with_loops(self, cpp_parser):
        """Testa complexidade com loops."""
        code = """
void process(std::vector<int> items) {
    for (auto item : items) {
        if (item > 0) {
            std::cout << item << std::endl;
        }
    }
}
"""
        result = cpp_parser.parse(code, "process.cpp")

        assert result is not None
        complexity = result.get("complexity", 1)
        assert complexity > 1


class TestCppParserMacros:
    """Testes de detecção de macros."""

    def test_detect_macros(self, cpp_parser):
        """Testa detecção de macros."""
        code = """
#define MAX_SIZE 100
#define PI 3.14159
#define LOG(msg) std::cout << msg

#ifdef DEBUG
    #define DEBUG_LOG(msg) LOG(msg)
#endif
"""
        result = cpp_parser.parse(code, "macros.hpp")

        assert result is not None


class TestCppParserErrorHandling:
    """Testes de tratamento de erros."""

    def test_parse_empty_code(self, cpp_parser):
        """Testa parsing de código vazio."""
        result = cpp_parser.parse("", "empty.cpp")

        assert result is not None
        assert len(result["classes"]) == 0
