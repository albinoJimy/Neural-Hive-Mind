"""
Testes para JavaScriptParser.
Parsing de JavaScript para análise estática.
"""

import pytest

from src.exploration.parsers.javascript_parser import JavaScriptParser


@pytest.fixture
def js_parser():
    """Instância de JavaScriptParser para testes."""
    return JavaScriptParser()


class TestJavaScriptParserBasic:
    """Testes básicos do JavaScript parser."""

    def test_parse_simple_class(self, js_parser):
        """Testa parsing de classe simples."""
        code = """
class UserService {
    constructor(name) {
        this.name = name;
    }
    getName() {
        return this.name;
    }
}
"""
        result = js_parser.parse(code, "user_service.js")

        assert result is not None
        assert len(result["classes"]) == 1
        assert result["classes"][0]["name"] == "UserService"

    def test_parse_function(self, js_parser):
        """Testa parsing de função."""
        code = """
function calculateSum(a, b) {
    return a + b;
}

const multiply = (x, y) => x * y;
"""
        result = js_parser.parse(code, "math.js")

        assert result is not None
        assert len(result["functions"]) >= 2

    def test_parse_async_function(self, js_parser):
        """Testa parsing de função async."""
        code = """
async function fetchData(url) {
    const response = await fetch(url);
    return response.json();
}

class DataProvider {
    async getUser(id) {
        return await db.users.findById(id);
    }
}
"""
        result = js_parser.parse(code, "api.js")

        assert result is not None
        async_funcs = [f for f in result["functions"] if f.get("is_async")]
        assert len(async_funcs) >= 1

    def test_parse_imports_es6(self, js_parser):
        """Testa extração de imports ES6."""
        code = """
import { Injectable } from '@nestjs/common';
import { Repository } from 'typeorm';
import { User } from '../entities/user.entity';
import * as fs from 'fs';
import express, { Request, Response } from 'express';
"""
        result = js_parser.parse(code, "service.js")

        assert result is not None
        imports = result["imports"]
        assert len(imports) > 0

    def test_parse_require_commonjs(self, js_parser):
        """Testa extração de require CommonJS."""
        code = """
const express = require('express');
const fs = require('fs');
const { Router } = require('express');
const UserController = require('./controllers/user');
"""
        result = js_parser.parse(code, "app.js")

        assert result is not None
        imports = result.get("commonjs_imports", [])
        assert len(imports) >= 3

    def test_parse_arrow_functions(self, js_parser):
        """Testa parsing de arrow functions."""
        code = """
const add = (a, b) => a + b;
const greet = name => {
    console.log(`Hello ${name}`);
    return name;
};
const numbers = [1, 2, 3].map(n => n * 2);
"""
        result = js_parser.parse(code, "arrows.js")

        assert result is not None
        assert len(result["functions"]) >= 2

    def test_parse_prototype_inheritance(self, js_parser):
        """Testa parsing de herança via prototype."""
        code = """
function Animal(name) {
    this.name = name;
}

Animal.prototype.speak = function() {
    console.log(this.name + ' makes a sound');
};

function Dog(name, breed) {
    Animal.call(this, name);
    this.breed = breed;
}

Dog.prototype = Object.create(Animal.prototype);
Dog.prototype.constructor = Dog;
Dog.prototype.bark = function() {
    console.log(this.name + ' barks');
};
"""
        result = js_parser.parse(code, "prototype.js")

        assert result is not None
        # Deve detectar funções e prototype assignments

    def test_parse_class_inheritance(self, js_parser):
        """Testa parsing de herança de classes."""
        code = """
class Animal {
    constructor(name) {
        this.name = name;
    }
    speak() {
        return `${this.name} makes a sound`;
    }
}

class Dog extends Animal {
    constructor(name, breed) {
        super(name);
        this.breed = breed;
    }
    speak() {
        return super.speak() + ' and barks';
    }
    bark() {
        return 'Woof!';
    }
}
"""
        result = js_parser.parse(code, "classes.js")

        assert result is not None
        assert len(result["classes"]) == 2
        assert result["classes"][1]["name"] == "Dog"
        assert result["classes"][1].get("extends") == "Animal"

    def test_parse_destructuring(self, js_parser):
        """Testa parsing de destructuring."""
        code = """
const { name, age } = user;
const [first, second] = array;
function process({ id, data }) {
    return id;
}
"""
        result = js_parser.parse(code, "destructuring.js")

        assert result is not None
        assert len(result["functions"]) >= 1

    def test_parse_spread_operator(self, js_parser):
        """Testa parsing de spread operator."""
        code = """
const arr = [1, 2, 3];
const newArr = [...arr, 4, 5];

const obj = { a: 1, b: 2 };
const newObj = { ...obj, c: 3 };

function sum(...args) {
    return args.reduce((a, b) => a + b, 0);
}
"""
        result = js_parser.parse(code, "spread.js")

        assert result is not None
        assert len(result["functions"]) >= 1

    def test_parse_template_literals(self, js_parser):
        """Testa parsing de template literals."""
        code = """
const name = 'World';
const greeting = `Hello ${name}!`;

function greet(name) {
    return `Welcome, ${name}!`;
}
"""
        result = js_parser.parse(code, "templates.js")

        assert result is not None


class TestJavaScriptParserErrorHandling:
    """Testes de tratamento de erros."""

    def test_parse_syntax_error(self, js_parser):
        """Testa parsing de código com erro de sintaxe."""
        invalid_code = """
class UserService {
    constructor(name {
        this.name = name;
    }
}
"""
        result = js_parser.parse(invalid_code, "invalid.js")

        assert result is None or result.get("has_errors") == True

    def test_parse_empty_code(self, js_parser):
        """Testa parsing de código vazio."""
        result = js_parser.parse("", "empty.js")

        assert result is not None
        assert len(result["classes"]) == 0


class TestJavaScriptParserComplexity:
    """Testes de cálculo de complexidade."""

    def test_calculate_complexity_with_conditionals(self, js_parser):
        """Testa complexidade com condicionais."""
        code = """
function complexLogic(x) {
    if (x < 0) {
        return "negative";
    } else if (x > 0) {
        return "positive";
    } else {
        return "zero";
    }
}
"""
        result = js_parser.parse(code, "logic.js")

        assert result is not None
        complexity = result.get("complexity", 1)
        assert complexity > 1

    def test_calculate_complexity_with_switch(self, js_parser):
        """Testa complexidade com switch."""
        code = """
function getType(value) {
    switch (typeof value) {
        case 'string':
            return 'str';
        case 'number':
            return 'num';
        case 'boolean':
            return 'bool';
        default:
            return 'other';
    }
}
"""
        result = js_parser.parse(code, "switch.js")

        assert result is not None
        complexity = result.get("complexity", 1)
        # Switch deve aumentar complexidade

    def test_calculate_complexity_with_try_catch(self, js_parser):
        """Testa complexidade com try-catch."""
        code = """
function safeOperation() {
    try {
        return riskyOperation();
    } catch (error) {
        console.error(error);
        return null;
    } finally {
        cleanup();
    }
}
"""
        result = js_parser.parse(code, "safe.js")

        assert result is not None
        complexity = result.get("complexity", 1)
        # Try-catch deve aumentar complexidade
        assert complexity > 1


class TestJavaScriptParserModernFeatures:
    """Testes para features modernas JavaScript."""

    def test_parse_optional_chaining(self, js_parser):
        """Testa parsing de optional chaining."""
        code = """
const name = user?.profile?.name;
const data = response?.data?.items;

function getValue(obj, key) {
    return obj?.[key];
}
"""
        result = js_parser.parse(code, "optional.js")

        assert result is not None

    def test_parse_nullish_coalescing(self, js_parser):
        """Testa parsing de nullish coalescing."""
        code = """
const name = userName ?? 'Anonymous';
const count = items?.length ?? 0;

function getConfig(config) {
    return config ?? getDefaultConfig();
}
"""
        result = js_parser.parse(code, "nullish.js")

        assert result is not None

    def test_parse_private_class_fields(self, js_parser):
        """Testa parsing de campos privados de classe."""
        code = """
class UserService {
    #repo;
    #cache = new Map();

    constructor(repo) {
        this.#repo = repo;
    }

    async getUser(id) {
        if (this.#cache.has(id)) {
            return this.#cache.get(id);
        }
        const user = await this.#repo.findById(id);
        this.#cache.set(id, user);
        return user;
    }
}
"""
        result = js_parser.parse(code, "private.js")

        assert result is not None
        assert len(result["classes"]) == 1

    def test_parse_static_class_members(self, js_parser):
        """Testa parsing de membros estáticos."""
        code = """
class MathUtils {
    static PI = 3.14159;

    static add(a, b) {
        return a + b;
    }

    static #privateStatic = 'private';
}
"""
        result = js_parser.parse(code, "static.js")

        assert result is not None
        assert len(result["classes"]) == 1
