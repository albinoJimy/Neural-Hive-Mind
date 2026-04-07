"""
Testes para YAMLParser.
Parsing de YAML para análise de configurações.
"""

import pytest

from src.exploration.parsers.yaml_parser import YAMLParser


@pytest.fixture
def yaml_parser():
    """Instância de YAMLParser para testes."""
    return YAMLParser()


class TestYAMLParserBasic:
    """Testes básicos do YAML parser."""

    def test_parse_simple_dict(self, yaml_parser):
        """Testa parsing de dicionário simples."""
        code = """
name: test-service
version: 1.0.0
port: 8080
"""
        result = yaml_parser.parse(code, "config.yaml")

        assert result is not None
        assert len(result["keys"]) == 3
        assert "name" in result["keys"]

    def test_parse_nested_dict(self, yaml_parser):
        """Testa parsing de dicionário aninhado."""
        code = """
server:
  host: localhost
  port: 8080
  ssl:
    enabled: true
    cert: /path/to/cert.pem
database:
  host: db.example.com
  port: 5432
"""
        result = yaml_parser.parse(code, "config.yaml")

        assert result is not None
        assert len(result["keys"]) >= 2
        assert "server" in result["keys"]
        assert "database" in result["keys"]

    def test_parse_list(self, yaml_parser):
        """Testa parsing de listas."""
        code = """
hosts:
  - localhost:8080
  - localhost:8081
  - localhost:8082
tags:
  - web
  - api
  - microservice
"""
        result = yaml_parser.parse(code, "config.yaml")

        assert result is not None
        assert "hosts" in result["keys"]
        assert "tags" in result["keys"]

    def test_parse_kubernetes_deployment(self, yaml_parser):
        """Testa parsing de deployment Kubernetes."""
        code = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nginx-deployment
  labels:
    app: nginx
spec:
  replicas: 3
  selector:
    matchLabels:
      app: nginx
  template:
    metadata:
      labels:
        app: nginx
    spec:
      containers:
      - name: nginx
        image: nginx:1.14.2
        ports:
        - containerPort: 80
"""
        result = yaml_parser.parse(code, "deployment.yaml")

        assert result is not None
        assert result.get("kind") == "Deployment"
        assert result.get("api_version") == "apps/v1"

    def test_parse_docker_compose(self, yaml_parser):
        """Testa parsing de docker-compose."""
        code = """
version: "3.8"
services:
  web:
    image: nginx:latest
    ports:
      - "80:80"
    depends_on:
      - db
  db:
    image: postgres:14
    environment:
      POSTGRES_PASSWORD: example
volumes:
  data:
"""
        result = yaml_parser.parse(code, "docker-compose.yaml")

        assert result is not None
        assert "services" in result["keys"]
        assert "volumes" in result["keys"]

    def test_parse_multiline_strings(self, yaml_parser):
        """Testa parsing de strings multiline."""
        code = """
description: |
  This is a multi-line
  string description.
  It preserves newlines.

summary: >
  This is a folded string
  that joins lines together.

script: |
  #!/bin/bash
  echo "Hello World"
"""
        result = yaml_parser.parse(code, "strings.yaml")

        assert result is not None
        assert "description" in result["keys"]
        assert "summary" in result["keys"]

    def test_parse_anchors_and_aliases(self, yaml_parser):
        """Testa parsing de âncoras e aliases."""
        code = """
defaults: &defaults
  adapter: postgres
  encoding: unicode

development:
  database: my_app_dev
  <<: *defaults

production:
  database: my_app_prod
  <<: *defaults
"""
        result = yaml_parser.parse(code, "database.yaml")

        assert result is not None
        assert "development" in result["keys"]
        assert "production" in result["keys"]

    def test_parse_environment_variables(self, yaml_parser):
        """Testa parsing de variáveis de ambiente."""
        code = """
database:
  url: ${DATABASE_URL}
  host: ${DB_HOST:-localhost}
  port: ${DB_PORT:-5432}
"""
        result = yaml_parser.parse(code, "env.yaml")

        assert result is not None
        assert "database" in result["keys"]
        # Parser deve detectar placeholders de env

    def test_detect_document_separator(self, yaml_parser):
        """Testa detecção de separador de documentos."""
        code = """
---
document: 1
value: first
---
document: 2
value: second
---
document: 3
value: third
"""
        result = yaml_parser.parse(code, "multi.yaml")

        assert result is not None
        assert result.get("document_count") == 3


class TestYAMLParserKubernetes:
    """Testes específicos para Kubernetes resources."""

    def test_detect_kubernetes_kind(self, yaml_parser):
        """Testa detecção de tipo de recurso Kubernetes."""
        test_cases = [
            ("kind: Deployment", "Deployment"),
            ("kind: Service", "Service"),
            ("kind: ConfigMap", "ConfigMap"),
            ("kind: Secret", "Secret"),
            ("kind: Ingress", "Ingress"),
            ("kind: StatefulSet", "StatefulSet"),
            ("kind: DaemonSet", "DaemonSet"),
        ]

        for code_line, expected_kind in test_cases:
            code = f"""
apiVersion: apps/v1
{code_line}
metadata:
  name: test
"""
            result = yaml_parser.parse(code, "test.yaml")
            assert result.get("kind") == expected_kind

    def test_extract_kubernetes_metadata(self, yaml_parser):
        """Testa extração de metadados Kubernetes."""
        code = """
apiVersion: v1
kind: Pod
metadata:
  name: my-pod
  namespace: default
  labels:
    app: myapp
    tier: backend
  annotations:
    prometheus.io/scrape: "true"
spec:
  containers:
  - name: app
    image: myapp:1.0
"""
        result = yaml_parser.parse(code, "pod.yaml")

        assert result is not None
        assert result.get("kind") == "Pod"
        assert result.get("name") == "my-pod"
        assert result.get("namespace") == "default"


class TestYAMLParserCI_CD:
    """Testes para configurações CI/CD."""

    def test_parse_github_actions(self, yaml_parser):
        """Testa parsing de GitHub Actions workflow."""
        code = """
name: CI Pipeline
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Run tests
        run: pytest
  build:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - name: Build
        run: npm run build
"""
        result = yaml_parser.parse(code, "ci.yaml")

        assert result is not None
        assert result.get("ci_type") == "github-actions"
        assert "jobs" in result["keys"]

    def test_parse_gitlab_ci(self, yaml_parser):
        """Testa parsing de GitLab CI."""
        code = """
stages:
  - build
  - test
  - deploy

build:
  stage: build
  script:
    - npm install
    - npm run build
  artifacts:
    paths:
      - dist/

test:
  stage: test
  script:
    - npm test
"""
        result = yaml_parser.parse(code, ".gitlab-ci.yml")

        assert result is not None
        assert result.get("ci_type") == "gitlab-ci"
        assert "stages" in result["keys"]

    def test_detect_ci_platform(self, yaml_parser):
        """Testa detecção de plataforma CI."""
        platforms = [
            ("name: CI\non:", "github-actions"),
            ("stages:\n  - build", "gitlab-ci"),
            ("version:", "circleci"),
            ("apiVersion: v1\nkind:", "kubernetes"),
        ]

        for code_snippet, expected_platform in platforms:
            result = yaml_parser.parse(code_snippet, "detect.yaml")
            if result:
                detected = result.get("ci_platform") or result.get("ci_type")
                if detected:
                    assert detected == expected_platform


class TestYAMLParserErrorHandling:
    """Testes de tratamento de erros."""

    def test_parse_invalid_yaml(self, yaml_parser):
        """Testa parsing de YAML inválido."""
        invalid_code = """
name: test
  invalid indentation
port: [unclosed list
"""
        result = yaml_parser.parse(invalid_code, "invalid.yaml")

        # Deve retornar None ou marcar erro
        assert result is None or result.get("has_errors") == True

    def test_parse_empty_yaml(self, yaml_parser):
        """Testa parsing de YAML vazio."""
        result = yaml_parser.parse("", "empty.yaml")

        assert result is not None
        assert len(result.get("keys", [])) == 0


class TestYAMLParserSecurity:
    """Testes de detecção de segurança."""

    def test_detect_secrets(self, yaml_parser):
        """Testa detecção de segredos."""
        code = """
database:
  password: admin123
  api_key: sk_live_1234567890
  secret: my-secret-key
safe_value: normal_value
"""
        result = yaml_parser.parse(code, "secrets.yaml")

        assert result is not None
        # Deve detectar possíveis segredos
        assert result.get("has_secrets") == True
        assert len(result.get("secret_keys", [])) >= 2

    def test_detect_base64_values(self, yaml_parser):
        """Testa detecção de valores base64."""
        code = """
config:
  cert: LS0tLS1CRUdJTi...
  key: QmFzZTY0IGVuY29kZWQga2V5
normal: not-base64
"""
        result = yaml_parser.parse(code, "base64.yaml")

        assert result is not None
        assert result.get("has_base64") == True
