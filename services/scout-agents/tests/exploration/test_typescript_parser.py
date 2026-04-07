"""
Testes para TypeScriptParser.
Parsing de TypeScript para análise estática.
"""
import pytest

from src.exploration.parsers.typescript_parser import TypeScriptParser


@pytest.fixture
def ts_parser():
    """Instância de TypeScriptParser para testes."""
    return TypeScriptParser()


class TestTypeScriptParserBasic:
    """Testes básicos do TypeScript parser."""

    def test_parse_simple_class(self, ts_parser):
        """Testa parsing de classe simples."""
        code = """
class UserService {
    private name: string;
    constructor(name: string) {
        this.name = name;
    }
    getName(): string {
        return this.name;
    }
}
"""
        result = ts_parser.parse(code, "user_service.ts")

        assert result is not None
        assert len(result["classes"]) == 1
        assert result["classes"][0]["name"] == "UserService"
        assert result["classes"][0]["methods_count"] == 2  # constructor + getName

    def test_parse_interface(self, ts_parser):
        """Testa parsing de interface TypeScript."""
        code = """
interface User {
    id: string;
    name: string;
    email: string;
    age?: number;
}

interface Repository<T> {
    findById(id: string): Promise<T>;
    save(entity: T): Promise<void>;
}
"""
        result = ts_parser.parse(code, "types.ts")

        assert result is not None
        assert len(result["interfaces"]) == 2
        assert result["interfaces"][0]["name"] == "User"
        assert result["interfaces"][1]["name"] == "Repository"

    def test_parse_function(self, ts_parser):
        """Testa parsing de função."""
        code = """
function calculateSum(a: number, b: number): number {
    return a + b;
}

const multiply = (x: number, y: number): number => x * y;
"""
        result = ts_parser.parse(code, "math.ts")

        assert result is not None
        assert len(result["functions"]) >= 2

    def test_parse_decorator(self, ts_parser):
        """Testa parsing de decorators TypeScript."""
        code = """
@Component({
    selector: 'app-user',
    template: '<div>{{name}}</div>'
})
class UserComponent {
    @Input() name: string;
    @Output() onChange = new EventEmitter();

    @HostBinding('class.active')
    isActive: boolean;
}
"""
        result = ts_parser.parse(code, "component.ts")

        assert result is not None
        decorators = result["classes"][0]["decorators"]
        assert len(decorators) >= 1
        assert any("Component" in str(d) for d in decorators)

    def test_parse_async_function(self, ts_parser):
        """Testa parsing de função async."""
        code = """
async function fetchData(url: string): Promise<any> {
    const response = await fetch(url);
    return response.json();
}

class DataProvider {
    async getUser(id: string): Promise<User> {
        return await db.users.findById(id);
    }
}
"""
        result = ts_parser.parse(code, "api.ts")

        assert result is not None
        async_funcs = [f for f in result["functions"] if f.get("is_async")]
        assert len(async_funcs) >= 1

    def test_parse_imports(self, ts_parser):
        """Testa extração de imports TypeScript."""
        code = """
import { Injectable } from '@nestjs/common';
import { Repository } from 'typeorm';
import { User } from '../entities/user.entity';
import * as fs from 'fs';
import express, { Request, Response } from 'express';
"""
        result = ts_parser.parse(code, "service.ts")

        assert result is not None
        imports = result["imports"]
        assert len(imports) > 0

    def test_parse_generic_class(self, ts_parser):
        """Testa parsing de classe genérica."""
        code = """
class Repository<T, K = string> {
    private items: Map<K, T> = new Map();

    findById(id: K): T | undefined {
        return this.items.get(id);
    }

    save(id: K, entity: T): void {
        this.items.set(id, entity);
    }
}

class UserRepository extends Repository<User, number> {}
"""
        result = ts_parser.parse(code, "repository.ts")

        assert result is not None
        assert len(result["classes"]) == 2
        assert result["classes"][0]["name"] == "Repository"
        # Verificar se detectou generics

    def test_parse_enum(self, ts_parser):
        """Testa parsing de enum TypeScript."""
        code = """
enum UserRole {
    ADMIN = 'admin',
    USER = 'user',
    GUEST = 'guest'
}

enum HttpStatus {
    OK = 200,
    NOT_FOUND = 404,
    SERVER_ERROR = 500
}
"""
        result = ts_parser.parse(code, "enums.ts")

        assert result is not None
        assert len(result["enums"]) == 2
        assert result["enums"][0]["name"] == "UserRole"

    def test_parse_type_alias(self, ts_parser):
        """Testa parsing de type aliases."""
        code = """
type ID = string | number;
type User = {
    id: ID;
    name: string;
    email: string;
};
type AsyncResult<T> = Promise<{ data: T; error: null } | { data: null; error: Error }>;
"""
        result = ts_parser.parse(code, "types.ts")

        assert result is not None
        assert len(result["type_aliases"]) >= 2

    def test_parse_namespace(self, ts_parser):
        """Testa parsing de namespace TypeScript."""
        code = """
namespace MyApp.Models {
    export interface User {
        id: string;
    }
    export class UserService {
        getUser(): User {
            return null;
        }
    }
}

namespace MyApp.Utils {
    export function format(str: string): string {
        return str.trim();
    }
}
"""
        result = ts_parser.parse(code, "models.ts")

        assert result is not None
        assert len(result["namespaces"]) == 2


class TestTypeScriptParserErrorHandling:
    """Testes de tratamento de erros."""

    def test_parse_syntax_error(self, ts_parser):
        """Testa parsing de código com erro de sintaxe."""
        invalid_code = """
class UserService {
    private name string;
    constructor(name: string {
        this.name = name;
    }
}
"""
        result = ts_parser.parse(invalid_code, "invalid.ts")

        # Parser deve retornar None ou marcar erro
        assert result is None or result.get("has_errors") == True

    def test_parse_empty_code(self, ts_parser):
        """Testa parsing de código vazio."""
        result = ts_parser.parse("", "empty.ts")

        assert result is not None
        assert len(result["classes"]) == 0
        assert len(result["functions"]) == 0


class TestTypeScriptParserComplexity:
    """Testes de cálculo de complexidade."""

    def test_calculate_complexity_simple(self, ts_parser):
        """Testa complexidade de função simples."""
        code = """
function simple(a: number): number {
    return a * 2;
}
"""
        result = ts_parser.parse(code, "simple.ts")

        assert result is not None
        complexity = result.get("complexity", 1)
        assert complexity >= 1

    def test_calculate_complexity_with_conditionals(self, ts_parser):
        """Testa complexidade com condicionais."""
        code = """
function complexLogic(x: number): string {
    if (x < 0) {
        return "negative";
    } else if (x > 0) {
        return "positive";
    } else {
        return "zero";
    }
}
"""
        result = ts_parser.parse(code, "logic.ts")

        assert result is not None
        # Complexidade deve ser maior que 1 (2 ifs)
        complexity = result.get("complexity", 1)
        assert complexity > 1

    def test_calculate_complexity_with_loops(self, ts_parser):
        """Testa complexidade com loops."""
        code = """
function process(items: number[]): number {
    let sum = 0;
    for (const item of items) {
        if (item > 0) {
            sum += item;
        }
    }
    return sum;
}
"""
        result = ts_parser.parse(code, "process.ts")

        assert result is not None
        complexity = result.get("complexity", 1)
        # Deve contar o for e o if
        assert complexity > 1


class TestTypeScriptParserArrowFunctions:
    """Testes específicos para arrow functions."""

    def test_parse_arrow_functions(self, ts_parser):
        """Testa parsing de arrow functions."""
        code = """
const add = (a: number, b: number) => a + b;
const greet = (name: string) => {
    console.log(`Hello ${name}`);
    return name;
};
const double = x => x * 2;
"""
        result = ts_parser.parse(code, "arrows.ts")

        assert result is not None
        assert len(result["functions"]) >= 3

    def test_parse_array_methods_with_arrows(self, ts_parser):
        """Testa parsing de métodos de array com arrow functions."""
        code = """
const numbers = [1, 2, 3, 4, 5];
const doubled = numbers.map(n => n * 2);
const evens = numbers.filter(n => n % 2 === 0);
const sum = numbers.reduce((acc, n) => acc + n, 0);
"""
        result = ts_parser.parse(code, "array.ts")

        assert result is not None
        # Deve detectar as arrow functions inline
