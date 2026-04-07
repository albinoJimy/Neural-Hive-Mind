"""
Testes para JSONParser.
Parsing de JSON para análise de configurações.
"""

import pytest

from src.exploration.parsers.json_parser import JSONParser


@pytest.fixture
def json_parser():
    """Instância de JSONParser para testes."""
    return JSONParser()


class TestJSONParserBasic:
    """Testes básicos do JSON parser."""

    def test_parse_simple_object(self, json_parser):
        """Testa parsing de objeto simples."""
        code = """
{
  "name": "test-service",
  "version": "1.0.0",
  "port": 8080
}
"""
        result = json_parser.parse(code, "config.json")

        assert result is not None
        assert len(result["keys"]) == 3
        assert "name" in result["keys"]

    def test_parse_nested_object(self, json_parser):
        """Testa parsing de objeto aninhado."""
        code = """
{
  "server": {
    "host": "localhost",
    "port": 8080,
    "ssl": {
      "enabled": true,
      "cert": "/path/to/cert.pem"
    }
  },
  "database": {
    "host": "db.example.com",
    "port": 5432
  }
}
"""
        result = json_parser.parse(code, "config.json")

        assert result is not None
        assert len(result["keys"]) >= 2
        assert "server" in result["keys"]
        assert "database" in result["keys"]

    def test_parse_array(self, json_parser):
        """Testa parsing de arrays."""
        code = """
{
  "hosts": ["localhost:8080", "localhost:8081", "localhost:8082"],
  "tags": ["web", "api", "microservice"],
  "numbers": [1, 2, 3, 4, 5]
}
"""
        result = json_parser.parse(code, "config.json")

        assert result is not None
        assert "hosts" in result["keys"]
        assert "tags" in result["keys"]

    def test_parse_mixed_types(self, json_parser):
        """Testa parsing de tipos mistos."""
        code = """
{
  "string": "value",
  "number": 42,
  "float": 3.14,
  "boolean": true,
  "null_value": null,
  "array": [1, 2, 3],
  "object": {"key": "value"}
}
"""
        result = json_parser.parse(code, "mixed.json")

        assert result is not None
        # Deve detectar todos os tipos primitivos

    def test_parse_package_json(self, json_parser):
        """Testa parsing de package.json."""
        code = """
{
  "name": "my-app",
  "version": "1.0.0",
  "description": "A sample application",
  "main": "index.js",
  "scripts": {
    "start": "node index.js",
    "test": "jest",
    "build": "webpack --mode production"
  },
  "dependencies": {
    "express": "^4.18.0",
    "lodash": "^4.17.21"
  },
  "devDependencies": {
    "jest": "^29.0.0",
    "webpack": "^5.0.0"
  }
}
"""
        result = json_parser.parse(code, "package.json")

        assert result is not None
        assert result.get("type") == "package.json"
        assert "dependencies" in result["keys"]
        assert "devDependencies" in result["keys"]

    def test_parse_tsconfig(self, json_parser):
        """Testa parsing de tsconfig.json."""
        code = """
{
  "compilerOptions": {
    "target": "ES2020",
    "module": "commonjs",
    "lib": ["ES2020"],
    "outDir": "./dist",
    "rootDir": "./src",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true
  },
  "include": ["src/**/*"],
  "exclude": ["node_modules", "**/*.test.ts"]
}
"""
        result = json_parser.parse(code, "tsconfig.json")

        assert result is not None
        assert result.get("type") == "tsconfig.json"
        assert "compilerOptions" in result["keys"]

    def test_parse_eslint_config(self, json_parser):
        """Testa parsing de configuração ESLint."""
        code = """
{
  "env": {
    "browser": true,
    "es2021": true,
    "node": true
  },
  "extends": "eslint:recommended",
  "parserOptions": {
    "ecmaVersion": 12,
    "sourceType": "module"
  },
  "rules": {
    "indent": ["error", 2],
    "quotes": ["error", "single"],
    "semi": ["error", "always"]
  }
}
"""
        result = json_parser.parse(code, ".eslintrc.json")

        assert result is not None
        assert result.get("type") == ".eslintrc.json"
        assert "rules" in result["keys"]


class TestJSONParserNPM:
    """Testes específicos para arquivos NPM."""

    def test_extract_npm_scripts(self, json_parser):
        """Testa extração de scripts npm."""
        code = """
{
  "scripts": {
    "start": "node server.js",
    "dev": "nodemon server.js",
    "test": "jest --coverage",
    "lint": "eslint src/",
    "build": "tsc",
    "deploy": "serverless deploy"
  }
}
"""
        result = json_parser.parse(code, "package.json")

        assert result is not None
        scripts = result.get("scripts", {})
        assert len(scripts) >= 6

    def test_extract_npm_dependencies(self, json_parser):
        """Testa extração de dependências npm."""
        code = """
{
  "dependencies": {
    "express": "^4.18.0",
    "mongoose": "^7.0.0",
    "jsonwebtoken": "^9.0.0"
  },
  "devDependencies": {
    "typescript": "^5.0.0",
    "@types/node": "^20.0.0",
    "jest": "^29.0.0"
  },
  "peerDependencies": {
    "react": "^18.0.0"
  },
  "optionalDependencies": {
    "fsevents": "^2.3.0"
  }
}
"""
        result = json_parser.parse(code, "package.json")

        assert result is not None
        assert "dependencies" in result["keys"]
        assert "devDependencies" in result["keys"]
        # Deve contar total de dependências


class TestJSONParserStructureAnalysis:
    """Testes de análise estrutural."""

    def test_calculate_depth(self, json_parser):
        """Testa cálculo de profundidade."""
        code = """
{
  "level1": {
    "level2": {
      "level3": {
        "level4": "value"
      }
    }
  }
}
"""
        result = json_parser.parse(code, "deep.json")

        assert result is not None
        depth = result.get("max_depth", 0)
        assert depth >= 4

    def test_count_primitive_values(self, json_parser):
        """Testa contagem de valores primitivos."""
        code = """
{
  "strings": ["a", "b", "c"],
  "numbers": [1, 2, 3],
  "booleans": [true, false],
  "nulls": [null, null]
}
"""
        result = json_parser.parse(code, "primitives.json")

        assert result is not None
        # Deve contar quantos valores de cada tipo

    def test_detect_empty_containers(self, json_parser):
        """Testa detecção de containers vazios."""
        code = """
{
  "empty_object": {},
  "empty_array": [],
  "non_empty": {"key": "value"},
  "nested_empty": {"outer": {"inner": {}}}
}
"""
        result = json_parser.parse(code, "empty.json")

        assert result is not None
        assert result.get("has_empty_containers") == True
        assert result.get("empty_count") >= 2


class TestJSONParserErrorHandling:
    """Testes de tratamento de erros."""

    def test_parse_invalid_json(self, json_parser):
        """Testa parsing de JSON inválido."""
        invalid_code = """
{
  "name": "test",
  invalid syntax here
  "port": 8080
}
"""
        result = json_parser.parse(invalid_code, "invalid.json")

        assert result is None or result.get("has_errors") == True

    def test_parse_trailing_comma(self, json_parser):
        """Testa parsing com trailing comma (não válido JSON padrão)."""
        code = """
{
  "name": "test",
  "port": 8080,
}
"""
        result = json_parser.parse(code, "trailing.json")

        # JSON padrão não aceita trailing comma
        assert result is None or result.get("has_errors") == True

    def test_parse_empty_json(self, json_parser):
        """Testa parsing de JSON vazio."""
        result = json_parser.parse("{}", "empty.json")

        assert result is not None
        assert len(result.get("keys", [])) == 0


class TestJSONParserSecurity:
    """Testes de detecção de segurança."""

    def test_detect_secrets_in_json(self, json_parser):
        """Testa detecção de segredos em JSON."""
        code = """
{
  "database": {
    "password": "admin123",
    "api_key": "sk_live_1234567890"
  },
  "tokens": {
    "jwt": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
  },
  "safe_value": "normal_value"
}
"""
        result = json_parser.parse(code, "secrets.json")

        assert result is not None
        assert result.get("has_secrets") == True
        assert len(result.get("secret_keys", [])) >= 2

    def test_detect_sensitive_patterns(self, json_parser):
        """Testa detecção de padrões sensíveis."""
        code = """
{
  "credentials": {
    "username": "admin",
    "password": "secret123"
  },
  "api": {
    "secret_key": "sk_live_abc",
    "access_token": "ghp_xyz123"
  }
}
"""
        result = json_parser.parse(code, "sensitive.json")

        assert result is not None
        # Deve detectar chaves sensíveis
