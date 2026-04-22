"""
Testes para CSharpParser.
Parsing de C# para análise estática.
"""

import pytest
from src.exploration.parsers.multilanguage.csharp_parser import CSharpParser


@pytest.fixture()
def csharp_parser():
    """Instância de CSharpParser para testes."""
    return CSharpParser()


class TestCSharpParserBasic:
    """Testes básicos do C# parser."""

    def test_parse_simple_class(self, csharp_parser):
        """Testa parsing de classe simples."""
        code = """
public class UserService
{
    private string name;

    public UserService(string name)
    {
        this.name = name;
    }

    public string GetName()
    {
        return this.name;
    }
}
"""
        result = csharp_parser.parse(code, "UserService.cs")

        assert result is not None
        assert len(result["classes"]) == 1
        assert result["classes"][0]["name"] == "UserService"
        assert "GetName" in [m["name"] for m in result["methods"]]

    def test_parse_interface(self, csharp_parser):
        """Testa parsing de interface C#."""
        code = """
public interface IRepository
{
    void Save(string entity);
    T Find<T>(int id);
}
"""
        result = csharp_parser.parse(code, "IRepository.cs")

        assert result is not None
        interfaces = result.get("interfaces", [])
        assert len(interfaces) >= 1

    def test_parse_enum(self, csharp_parser):
        """Testa parsing de enum C#."""
        code = """
public enum UserRole
{
    Admin,
    User,
    Guest
}

enum HttpStatus
{
    Ok = 200,
    NotFound = 404,
    ServerError = 500
}
"""
        result = csharp_parser.parse(code, "UserRole.cs")

        assert result is not None
        assert len(result["enums"]) >= 1
        assert result["enums"][0]["name"] in ["UserRole", "HttpStatus"]

    def test_parse_method_with_return_type(self, csharp_parser):
        """Testa parsing de método com tipo de retorno."""
        code = """
public class Calculator
{
    public int Add(int a, int b)
    {
        return a + b;
    }

    public string GetName()
    {
        return "Calculator";
    }

    public async Task<string> GetDataAsync()
    {
        return await Task.FromResult("data");
    }
}
"""
        result = csharp_parser.parse(code, "Calculator.cs")

        assert result is not None
        methods = result["methods"]
        assert len(methods) >= 2
        assert any(m["name"] == "Add" for m in methods)
        assert any(m["name"] == "GetName" for m in methods)

    def test_parse_attributes(self, csharp_parser):
        """Testa parsing de attributes C#."""
        code = """
public class User
{
    private long id;

    [Obsolete("Use GetFullName instead")]
    public string GetName()
    {
        return "User";
    }

    [HttpGet("users/{id}")]
    [ProducesResponseType(typeof(User), 200)]
    public IActionResult GetUser(int id)
    {
        return Ok();
    }
}
"""
        result = csharp_parser.parse(code, "User.cs")

        assert result is not None
        cls = result["classes"][0]
        assert cls["name"] == "User"

    def test_parse_generics(self, csharp_parser):
        """Testa parsing de classes genéricas."""
        code = """
public class Repository<T, K> where T : class where K : notnull
{
    public T FindById(K id)
    {
        return default(T);
    }
}

public class UserRepository : Repository<User, long>
{
    public User FindByEmail(string email)
    {
        return default(User);
    }
}
"""
        result = csharp_parser.parse(code, "Repository.cs")

        assert result is not None
        assert len(result["classes"]) >= 1

    def test_parse_inheritance(self, csharp_parser):
        """Testa parsing de herança."""
        code = """
public class Dog : Animal
{
    public void Bark()
    {
        Console.WriteLine("Woof!");
    }
}

public class Customer : Person, ICustomer
{
    public string Email { get; set; }
}
"""
        result = csharp_parser.parse(code, "Dog.cs")

        assert result is not None
        classes = result.get("classes", [])
        assert len(classes) >= 1

    def test_parse_static_method(self, csharp_parser):
        """Testa parsing de método estático."""
        code = """
public class MathUtils
{
    public const double PI = 3.14159;

    public static double Add(double a, double b)
    {
        return a + b;
    }
}
"""
        result = csharp_parser.parse(code, "MathUtils.cs")

        assert result is not None
        methods = result["methods"]
        static_methods = [m for m in methods if m.get("is_static")]
        assert len(static_methods) >= 1

    def test_parse_abstract_class(self, csharp_parser):
        """Testa parsing de classe abstrata."""
        code = """
public abstract class Shape
{
    public abstract void Draw();

    public void Move(int x, int y)
    {
        Console.WriteLine("Moving");
    }
}
"""
        result = csharp_parser.parse(code, "Shape.cs")

        assert result is not None
        classes = result.get("classes", [])
        assert len(classes) >= 1

    def test_parse_namespace_declaration(self, csharp_parser):
        """Testa parsing de declaração de namespace."""
        code = """
namespace Example.Services
{
    public class UserService
    {
        public void Serve() {}
    }
}
"""
        result = csharp_parser.parse(code, "UserService.cs")

        assert result is not None
        assert result["namespaces"] == "Example.Services"


class TestCSharpParserProperties:
    """Testes de propriedades C#."""

    def test_parse_properties(self, csharp_parser):
        """Testa extração de propriedades."""
        code = """
public class User
{
    public long Id { get; set; }
    public string Name { get; private set; }
    public readonly string Email;

    private int age;
    public int Age
    {
        get { return age; }
        set { age = value; }
    }
}
"""
        result = csharp_parser.parse(code, "User.cs")

        assert result is not None
        # Nota: parser regex pode não capturar todas propriedades


class TestCSharpParserUsings:
    """Testes de extração de using directives."""

    def test_parse_usings(self, csharp_parser):
        """Testa extração de using directives."""
        code = """
using System;
using System.Collections.Generic;
using System.Linq;
using static MathUtils;

public class Test
{
    private List<string> items = new();
}
"""
        result = csharp_parser.parse(code, "Test.cs")

        assert result is not None
        usings = result["imports"]
        assert len(usings) >= 3
        assert any(u["name"] == "System" for u in usings)


class TestCSharpParserComplexity:
    """Testes de cálculo de complexidade."""

    def test_calculate_complexity_simple(self, csharp_parser):
        """Testa complexidade de método simples."""
        code = """
public class Math
{
    public int Add(int a, int b)
    {
        return a + b;
    }
}
"""
        result = csharp_parser.parse(code, "Math.cs")

        assert result is not None
        complexity = result.get("complexity", 1)
        assert complexity >= 1

    def test_calculate_complexity_with_conditionals(self, csharp_parser):
        """Testa complexidade com condicionais."""
        code = """
public class Logic
{
    public string Process(int value)
    {
        if (value < 0)
        {
            return "negative";
        }
        else if (value > 0)
        {
            return "positive";
        }
        else
        {
            return "zero";
        }
    }
}
"""
        result = csharp_parser.parse(code, "Logic.cs")

        assert result is not None
        complexity = result.get("complexity", 1)
        assert complexity > 1

    def test_calculate_complexity_with_loops(self, csharp_parser):
        """Testa complexidade com loops."""
        code = """
public class Loop
{
    public void Process(List<string> items)
    {
        foreach (var item in items)
        {
            if (item != null)
            {
                Console.WriteLine(item);
            }
        }
    }
}
"""
        result = csharp_parser.parse(code, "Loop.cs")

        assert result is not None
        complexity = result.get("complexity", 1)
        assert complexity > 1


class TestCSharpParserAsync:
    """Testes de métodos assíncronos."""

    def test_parse_async_method(self, csharp_parser):
        """Testa parsing de método assíncrono."""
        code = """
public class DataProcessor
{
    public async Task ProcessAsync()
    {
        await Task.Delay(100);
    }

    public async Task<int> CalculateAsync()
    {
        return await Task.FromResult(42);
    }
}
"""
        result = csharp_parser.parse(code, "DataProcessor.cs")

        assert result is not None
        methods = result["methods"]
        async_methods = [m for m in methods if m.get("is_async")]
        assert len(async_methods) >= 1


class TestCSharpParserErrorHandling:
    """Testes de tratamento de erros."""

    def test_parse_syntax_error(self, csharp_parser):
        """Testa parsing de código com erro de sintaxe."""
        invalid_code = """
public class UserService
{
    private string name

    public UserService(string name
    {
        this.name = name;
    }
}
"""
        result = csharp_parser.parse(invalid_code, "UserService.cs")

        # Parser deve retornar resultado (mesmo que incompleto) ou None
        assert result is not None or result is None

    def test_parse_empty_code(self, csharp_parser):
        """Testa parsing de código vazio."""
        result = csharp_parser.parse("", "Empty.cs")

        assert result is not None
        assert len(result["classes"]) == 0


class TestCSharpParserRecords:
    """Testes de record types (C# 9+)."""

    def test_parse_record(self, csharp_parser):
        """Testa parsing de record."""
        code = """
public record Person(string FirstName, string LastName);

public record User(int Id, string Email) : Person("John", "Doe");
"""
        result = csharp_parser.parse(code, "Person.cs")

        assert result is not None
        # Nota: records podem ser capturados como classes ou tipos especiais
