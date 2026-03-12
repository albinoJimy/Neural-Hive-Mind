# Exemplos de Uso - CodeForge

## Visão Geral

Este documento fornece exemplos práticos e completos de uso do CodeForge, desde cenários simples até casos avançados.

## Índice

1. [Exemplo 1: Microserviço Python FastAPI](#exemplo-1-microserviço-python-fastapi)
2. [Exemplo 2: WebApp Node.js Express](#exemplo-2-webapp-nodejs-express)
3. [Exemplo 3: API TypeScript NestJS](#exemplo-3-api-typescript-nestjs)
4. [Exemplo 4: CLI Tool em Go](#exemplo-4-cli-tool-em-go)
5. [Exemplo 5: Serviço Java Spring Boot](#exemplo-5-serviço-java-spring-boot)
6. [Exemplo 6: Lambda Function Python](#exemplo-6-lambda-function-python)
7. [Exemplo 7: Build com Build Args Customizados](#exemplo-7-build-com-build-args-customizados)
8. [Exemplo 8: Pipeline Completo com Validação](#exemplo-8-pipeline-completo-com-validação)

---

## Exemplo 1: Microserviço Python FastAPI

### Cenário

Criar um microserviço FastAPI com endpoints REST básicos.

### Código do Serviço

```python
# src/main.py
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class Item(BaseModel):
    name: str
    price: float

@app.get("/")
def read_root():
    return {"message": "Hello World"}

@app.get("/items/{item_id}")
def read_item(item_id: int):
    return {"item_id": item_id, "name": "Example Item"}

@app.post("/items")
def create_item(item: Item):
    return {"item_id": 1, **item.dict()}
```

```txt
# requirements.txt
fastapi==0.104.1
uvicorn[standard]==0.24.0
pydantic==2.5.0
```

### Execução no Pipeline

```python
from src.models.codeforge_ticket import CodeForgeTicket, ArtifactType
from src.services.pipeline_engine import PipelineEngine
from src.services.dockerfile_generator import DockerfileGenerator, SupportedLanguage
from src.services.container_builder import ContainerBuilder

async def create_fastapi_service():
    # 1. Criar ticket
    ticket = CodeForgeTicket(
        ticket_id="fastapi-service-001",
        intent_description="Create a FastAPI microservice with CRUD endpoints",
        parameters={
            "language": "python",
            "framework": "fastapi",
            "artifact_type": "microservice",
            "service_name": "items-api",
            "version": "1.0.0",
            "port": 8000
        },
        artifact_type=ArtifactType.MICROSERVICE
    )

    # 2. Configurar pipeline
    engine = PipelineEngine(
        enable_container_build=True,
        dockerfile_generator=DockerfileGenerator(),
        container_builder=ContainerBuilder()
    )

    # 3. Executar
    result = await engine.execute_pipeline(ticket)

    if result.status == "COMPLETED":
        print(f"✅ Service created successfully!")
        print(f"   Image: {result.metadata.get('container_image', {}).get('image_tag')}")
        print(f"   Digest: {result.metadata.get('container_image', {}).get('digest')}")
        print(f"   Size: {result.metadata.get('container_image', {}).get('size_bytes', 0) / 1024 / 1024:.1f} MB")

        return result
    else:
        print(f"❌ Pipeline failed: {result.error_message}")
        raise Exception(f"Pipeline execution failed")
```

### Dockerfile Gerado

```dockerfile
# Builder stage
FROM python:3.11-slim as builder

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Final stage
FROM python:3.11-slim

WORKDIR /app

# Copy Python packages from builder
COPY --from=builder /root/.local /root/.local
COPY . .

# Create non-root user
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose port
EXPOSE 8000

# Run application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Teste Local

```bash
# Build manual (para testes)
docker build -t items-api:1.0.0 .

# Rodar container
docker run -p 8000:8000 items-api:1.0.0

# Testar endpoints
curl http://localhost:8000/
curl http://localhost:8000/items/1
curl -X POST http://localhost:8000/items -H "Content-Type: application/json" \
  -d '{"name": "Test Item", "price": 9.99}'
```

---

## Exemplo 2: WebApp Node.js Express

### Cenário

Criar uma aplicação web Express.js com middleware de logging.

### Código da Aplicação

```javascript
// src/index.js
const express = require('express');
const morgan = require('morgan');

const app = express();
const PORT = process.env.PORT || 3000;

// Middleware
app.use(express.json());
app.use(morgan('combined'));

// Routes
app.get('/', (req, res) => {
  res.json({ message: 'Hello from Express!' });
});

app.get('/health', (req, res) => {
  res.json({ status: 'healthy', uptime: process.uptime() });
});

app.get('/users/:id', (req, res) => {
  const { id } = req.params;
  res.json({ userId: id, name: 'John Doe', email: 'john@example.com' });
});

app.post('/users', (req, res) => {
  const user = req.body;
  res.status(201).json({ ...user, id: Date.now() });
});

// Start server
app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});
```

```json
// package.json
{
  "name": "express-webapp",
  "version": "1.0.0",
  "main": "src/index.js",
  "scripts": {
    "start": "node src/index.js",
    "dev": "nodemon src/index.js"
  },
  "dependencies": {
    "express": "^4.18.2",
    "morgan": "^1.10.0"
  },
  "devDependencies": {
    "nodemon": "^3.0.1"
  }
}
```

### Execução no Pipeline

```python
from src.models.codeforge_ticket import CodeForgeTicket, ArtifactType
from src.services.pipeline_engine import PipelineEngine
from src.services.dockerfile_generator import DockerfileGenerator, SupportedLanguage

async def create_express_app():
    ticket = CodeForgeTicket(
        ticket_id="express-app-001",
        intent_description="Create an Express.js web application",
        parameters={
            "language": "nodejs",
            "framework": "express",
            "artifact_type": "microservice",
            "service_name": "user-api",
            "version": "1.0.0",
            "port": 3000
        },
        artifact_type=ArtifactType.MICROSERVICE
    )

    engine = PipelineEngine(
        enable_container_build=True,
        dockerfile_generator=DockerfileGenerator(),
        container_builder=ContainerBuilder()
    )

    result = await engine.execute_pipeline(ticket)
    return result
```

### Dockerfile Gerado

```dockerfile
# Builder stage
FROM node:20-alpine as builder

WORKDIR /app

# Install all dependencies
COPY package*.json ./
RUN npm ci

# Final stage
FROM node:20-alpine

WORKDIR /app

# Copy production dependencies
COPY package*.json ./
RUN npm ci --only=production

# Copy application code
COPY . .

# Create non-root user
RUN addgroup -g 1000 nodejs && \
    adduser -u 1000 -G nodejs nodejs && \
    chown -R nodejs:nodejs /app
USER nodejs

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:3000/health || exit 1

# Expose port
EXPOSE 3000

# Start application
CMD ["node", "src/index.js"]
```

---

## Exemplo 3: API TypeScript NestJS

### Cenário

Criar uma API REST estruturada com NestJS.

### Código da Aplicação

```typescript
// src/main.ts
import { NestFactory } from '@nestjs/core';
import { AppModule } from './app.module';
import { ValidationPipe } from '@nestjs/common';

async function bootstrap() {
  const app = await NestFactory.create(AppModule);

  // Enable validation
  app.useGlobalPipes(new ValidationPipe({
    whitelist: true,
    forbidNonWhitelisted: true,
  }));

  // CORS
  app.enableCors();

  await app.listen(3000);
  console.log('Application is running on: http://localhost:3000');
}
bootstrap();
```

```typescript
// src/app.module.ts
import { Module } from '@nestjs/common';
import { UsersController } from './users/users.controller';
import { UsersService } from './users/users.service';

@Module({
  imports: [],
  controllers: [UsersController],
  providers: [UsersService],
})
export class AppModule {}
```

```typescript
// src/users/users.controller.ts
import { Controller, Get, Post, Body, Param } from '@nestjs/common';
import { UsersService } from './users.service';
import { CreateUserDto } from './dto/create-user.dto';

@Controller('users')
export class UsersController {
  constructor(private readonly usersService: UsersService) {}

  @Get()
  findAll() {
    return this.usersService.findAll();
  }

  @Get(':id')
  findOne(@Param('id') id: string) {
    return this.usersService.findOne(id);
  }

  @Post()
  create(@Body() createUserDto: CreateUserDto) {
    return this.usersService.create(createUserDto);
  }
}
```

```json
// package.json
{
  "name": "nestjs-api",
  "version": "1.0.0",
  "scripts": {
    "build": "nest build",
    "start": "nest start",
    "start:prod": "node dist/main"
  },
  "dependencies": {
    "@nestjs/common": "^10.0.0",
    "@nestjs/core": "^10.0.0",
    "@nestjs/platform-express": "^10.0.0",
    "class-validator": "^0.14.0",
    "class-transformer": "^0.5.1",
    "reflect-metadata": "^0.1.13"
  },
  "devDependencies": {
    "@nestjs/cli": "^10.0.0",
    "typescript": "^5.1.3"
  }
}
```

### Execução no Pipeline

```python
from src.models.codeforge_ticket import CodeForgeTicket, ArtifactType
from src.services.pipeline_engine import PipelineEngine
from src.services.dockerfile_generator import DockerfileGenerator, SupportedLanguage

async def create_nestjs_api():
    ticket = CodeForgeTicket(
        ticket_id="nestjs-api-001",
        intent_description="Create a NestJS REST API",
        parameters={
            "language": "typescript",
            "framework": "nestjs",
            "artifact_type": "microservice",
            "service_name": "users-api",
            "version": "1.0.0",
            "port": 3000
        },
        artifact_type=ArtifactType.MICROSERVICE
    )

    engine = PipelineEngine(
        enable_container_build=True,
        dockerfile_generator=DockerfileGenerator(),
        container_builder=ContainerBuilder()
    )

    result = await engine.execute_pipeline(ticket)
    return result
```

### Dockerfile Gerado

```dockerfile
# Build stage - all dependencies
FROM node:20-alpine as build-all

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

# Production stage - production dependencies only
FROM node:20-alpine as build-prod

WORKDIR /app

COPY package*.json ./
RUN npm ci --only=production

# Final stage
FROM node:20-alpine

WORKDIR /app

# Copy dependencies and built code
COPY --from=build-prod /app/node_modules ./node_modules
COPY --from=build-all /app/dist ./dist

# Create non-root user
RUN addgroup -g 1000 nodejs && \
    adduser -u 1000 -G nodejs nodejs && \
    chown -R nodejs:nodejs /app
USER nodejs

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:3000/health || exit 1

# Expose port
EXPOSE 3000

# Start application
ENTRYPOINT ["/usr/bin/dumb-init", "--"]
CMD ["node", "dist/main"]
```

---

## Exemplo 4: CLI Tool em Go

### Cenário

Criar uma ferramenta de linha de comando para gerenciar tarefas.

### Código da Aplicação

```go
// cmd/cli/main.go
package main

import (
    "flag"
    "fmt"
    "os"
)

type Task struct {
    ID    int
    Title string
    Done  bool
}

var tasks []Task

func main() {
    listCmd := flag.NewFlagSet("list", flag.ExitOnError)
    addCmd := flag.NewFlagSet("add", flag.ExitOnError)

    addTitle := addCmd.String("title", "", "Task title")

    if len(os.Args) < 2 {
        fmt.Println("Expected 'list' or 'add' subcommands")
        os.Exit(1)
    }

    switch os.Args[1] {
    case "list":
        listCmd.Parse(os.Args[2:])
        listTasks()
    case "add":
        addCmd.Parse(os.Args[2:])
        addTask(*addTitle)
    default:
        fmt.Println("Expected 'list' or 'add' subcommands")
        os.Exit(1)
    }
}

func listTasks() {
    fmt.Println("Tasks:")
    for _, task := range tasks {
        status := " "
        if task.Done {
            status = "✓"
        }
        fmt.Printf("  [%s] %d: %s\n", status, task.ID, task.Title)
    }
}

func addTask(title string) {
    if title == "" {
        fmt.Println("Title is required")
        os.Exit(1)
    }
    task := Task{
        ID:    len(tasks) + 1,
        Title: title,
        Done:  false,
    }
    tasks = append(tasks, task)
    fmt.Printf("Added task: %s\n", title)
}
```

```go
// go.mod
module cli-tool

go 1.21
```

### Execução no Pipeline

```python
from src.models.codeforge_ticket import CodeForgeTicket, ArtifactType
from src.services.pipeline_engine import PipelineEngine
from src.services.dockerfile_generator import DockerfileGenerator, SupportedLanguage

async def create_cli_tool():
    ticket = CodeForgeTicket(
        ticket_id="cli-tool-001",
        intent_description="Create a CLI task manager tool in Go",
        parameters={
            "language": "golang",
            "artifact_type": "cli_tool",
            "service_name": "taskcli",
            "version": "1.0.0"
        },
        artifact_type=ArtifactType.CLI_TOOL
    )

    engine = PipelineEngine(
        enable_container_build=True,
        dockerfile_generator=DockerfileGenerator(),
        container_builder=ContainerBuilder()
    )

    result = await engine.execute_pipeline(ticket)
    return result
```

### Dockerfile Gerado

```dockerfile
# Build stage
FROM golang:1.21-alpine AS builder

WORKDIR /app

# Copy go mod files
COPY go.* ./
RUN go mod download

# Copy source code
COPY . .

# Build static binary
RUN CGO_ENABLED=0 GOOS=linux go build -a -installsuffix cgo -o main ./cmd/cli

# Final stage - scratch for minimal size
FROM scratch

WORKDIR /app

# Copy binary from builder
COPY --from=builder /app/main .

# Copy CA certificates for HTTPS
COPY --from=builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/

# Set entrypoint
ENTRYPOINT ["./main"]
```

---

## Exemplo 5: Serviço Java Spring Boot

### Cenário

Criar um microserviço Spring Boot com JPA.

### Código da Aplicação

```java
// src/main/java/com/example/demo/DemoApplication.java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

```java
// src/main/java/com/example/demo/ProductController.java
package com.example.demo;

import org.springframework.web.bind.annotation.*;
import java.util.List;
import java.util.ArrayList;

@RestController
@RequestMapping("/api/products")
public class ProductController {

    private List<Product> products = new ArrayList<>();

    @GetMapping
    public List<Product> getAll() {
        return products;
    }

    @GetMapping("/{id}")
    public Product getById(@PathVariable Long id) {
        return products.stream()
            .filter(p -> p.getId().equals(id))
            .findFirst()
            .orElse(null);
    }

    @PostMapping
    public Product create(@RequestBody Product product) {
        product.setId((long) (products.size() + 1));
        products.add(product);
        return product;
    }
}
```

```java
// src/main/java/com/example/demo/Product.java
package com.example.demo;

public class Product {
    private Long id;
    private String name;
    private Double price;

    // Getters and setters
    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
    public Double getPrice() { return price; }
    public void setPrice(Double price) { this.price = price; }
}
```

```xml
<!-- pom.xml -->
<project>
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>demo</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.2.0</version>
    </parent>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### Execução no Pipeline

```python
from src.models.codeforge_ticket import CodeForgeTicket, ArtifactType
from src.services.pipeline_engine import PipelineEngine
from src.services.dockerfile_generator import DockerfileGenerator, SupportedLanguage

async def create_spring_boot_service():
    ticket = CodeForgeTicket(
        ticket_id="springboot-service-001",
        intent_description="Create a Spring Boot REST API",
        parameters={
            "language": "java",
            "framework": "spring-boot",
            "artifact_type": "microservice",
            "service_name": "product-api",
            "version": "1.0.0",
            "port": 8080
        },
        artifact_type=ArtifactType.MICROSERVICE
    )

    engine = PipelineEngine(
        enable_container_build=True,
        dockerfile_generator=DockerfileGenerator(),
        container_builder=ContainerBuilder()
    )

    result = await engine.execute_pipeline(ticket)
    return result
```

### Dockerfile Gerado

```dockerfile
# Build stage
FROM maven:3.9-eclipse-temurin-21-alpine AS builder

WORKDIR /app

# Copy pom.xml and download dependencies
COPY pom.xml .
RUN mvn dependency:go-offline

# Copy source and build
COPY src ./src
RUN mvn clean package -DskipTests

# Final stage
FROM eclipse-temurin:21-jre-alpine

WORKDIR /app

# Copy JAR from builder
COPY --from=builder /app/target/*.jar app.jar

# Create non-root user
RUN addgroup -S spring && \
    adduser -S spring -G spring && \
    chown -R spring:spring /app
USER spring

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:8080/actuator/health || exit 1

# Expose port
EXPOSE 8080

# Run application
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

---

## Exemplo 6: Lambda Function Python

### Cenário

Criar uma AWS Lambda function para processamento de eventos.

### Código da Handler

```python
# lambda_function.py
import json
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """
    Lambda handler for processing S3 events
    """
    logger.info(f"Processing event: {json.dumps(event)}")

    # Process records
    results = []
    for record in event.get('Records', []):
        result = {
            'bucket': record['s3']['bucket']['name'],
            'key': record['s3']['object']['key'],
            'size': record['s3']['object']['size'],
            'processed': True
        }
        results.append(result)
        logger.info(f"Processed: {result['key']}")

    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': 'Processing complete',
            'processed_count': len(results),
            'results': results
        })
    }
```

```txt
# requirements.txt
boto3==1.34.0
```

### Execução no Pipeline

```python
from src.models.codeforge_ticket import CodeForgeTicket, ArtifactType
from src.services.pipeline_engine import PipelineEngine
from src.services.dockerfile_generator import DockerfileGenerator, SupportedLanguage

async def create_lambda_function():
    ticket = CodeForgeTicket(
        ticket_id="lambda-function-001",
        intent_description="Create a Lambda function for S3 event processing",
        parameters={
            "language": "python",
            "artifact_type": "lambda_function",
            "service_name": "s3-processor",
            "version": "1.0.0"
        },
        artifact_type=ArtifactType.LAMBDA_FUNCTION
    )

    engine = PipelineEngine(
        enable_container_build=True,
        dockerfile_generator=DockerfileGenerator(),
        container_builder=ContainerBuilder()
    )

    result = await engine.execute_pipeline(ticket)
    return result
```

### Dockerfile Gerado

```dockerfile
# Builder stage
FROM python:3.11-slim as builder

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Final stage
FROM public.ecr.aws/lambda/python:3.11

WORKDIR /app

# Copy dependencies from builder
COPY --from=builder /root/.local /root/.local

# Copy handler
COPY lambda_function.py .

# Make sure handlers are in PYTHONPATH
ENV PYTHONPATH=/root/.local/lib/python3.11/site-packages:$PYTHONPATH

# Set handler
CMD ["lambda_function.lambda_handler"]
```

---

## Exemplo 7: Build com Build Args Customizados

### Cenário

Build com variáveis de build para ambientes diferentes.

### Execução

```python
from src.services.container_builder import ContainerBuilder
from src.services.dockerfile_generator import DockerfileGenerator, SupportedLanguage

async def build_with_args():
    # 1. Gerar Dockerfile com suporte a ARG
    generator = DockerfileGenerator()
    dockerfile = generator.generate_dockerfile(
        language=SupportedLanguage.PYTHON,
        framework="fastapi"
    )

    # Salvar Dockerfile
    with open("/tmp/Dockerfile", "w") as f:
        f.write(dockerfile)

    # 2. Build com argumentos customizados
    builder = ContainerBuilder(timeout_seconds=3600)

    result = await builder.build_container(
        dockerfile_path="/tmp/Dockerfile",
        build_context="/app",
        image_tag="myapp:1.0.0",
        build_args=[
            "ENVIRONMENT=production",
            "APP_VERSION=1.0.0",
            "BUILD_DATE=2026-03-12",
            "GIT_COMMIT=abc123",
            "DEBUG=false"
        ]
    )

    if result.success:
        print(f"✅ Build succeeded!")
        print(f"   Tag: {result.image_tag}")
        print(f"   Digest: {result.image_digest}")
        print(f"   Size: {result.size_bytes / 1024 / 1024:.1f} MB")
        print(f"   Duration: {result.duration_ms / 1000:.1f}s")

    return result
```

### Dockerfile com ARG

```dockerfile
# Docker gerado suporta ARG
ARG ENVIRONMENT=development
ARG APP_VERSION=1.0.0
ARG BUILD_DATE=unknown
ARG GIT_COMMIT=unknown

FROM python:3.11-slim as builder

WORKDIR /app

# ... resto do Dockerfile

# Usar ARG no ENV
ENV APP_VERSION=${APP_VERSION}
ENV ENVIRONMENT=${ENVIRONMENT}
ENV BUILD_DATE=${BUILD_DATE}
ENV GIT_COMMIT=${GIT_COMMIT}
```

---

## Exemplo 8: Pipeline Completo com Validação

### Cenário

Executar pipeline completo com todas as validações habilitadas.

### Código

```python
import asyncio
from src.models.codeforge_ticket import CodeForgeTicket, ArtifactType
from src.services.pipeline_engine import PipelineEngine
from src.services.dockerfile_generator import DockerfileGenerator
from src.services.container_builder import ContainerBuilder
from src.clients.trivy_client import TrivyClient
from src.clients.sonarqube_client import SonarQubeClient
from src.services.validator import Validator

async def complete_pipeline_with_validation():
    """
    Executa pipeline completo com todas as validações
    """
    # 1. Configurar clientes de validação
    trivy_client = TrivyClient()
    sonarqube_client = SonarQubeClient(
        host_url="http://sonarqube:9000",
        auth_token="your-token"
    )

    validator = Validator(
        trivy_client=trivy_client,
        sonarqube_client=sonarqube_client,
        snyk_client=None,  # Opcional
        enabled_validations=[
            "vulnerability_scan",
            "code_quality",
            "security_analysis"
        ]
    )

    # 2. Configurar pipeline
    engine = PipelineEngine(
        dockerfile_generator=DockerfileGenerator(),
        container_builder=ContainerBuilder(
            timeout_seconds=3600
        ),
        validator=validator,
        enable_container_build=True,
        auto_approval_threshold=0.9  # Requer alta confiança
    )

    # 3. Criar ticket
    ticket = CodeForgeTicket(
        ticket_id="complete-pipeline-001",
        intent_description="Create a secure FastAPI microservice",
        parameters={
            "language": "python",
            "framework": "fastapi",
            "artifact_type": "microservice",
            "service_name": "secure-api",
            "version": "1.0.0",
            "port": 8000
        },
        artifact_type=ArtifactType.MICROSERVICE
    )

    # 4. Executar pipeline
    print("🚀 Starting complete pipeline...")
    result = await engine.execute_pipeline(ticket)

    # 5. Verificar resultado
    print("\n" + "="*60)
    print("PIPELINE EXECUTION RESULT")
    print("="*60)

    print(f"Status: {result.status}")
    print(f"Stage Results:")

    for stage_name, stage_result in result.stage_results.items():
        status_icon = "✅" if stage_result["success"] else "❌"
        print(f"  {status_icon} {stage_name}: {stage_result['status']}")
        if stage_result.get("error_message"):
            print(f"     Error: {stage_result['error_message']}")

    # 6. Detalhes do container build
    if "container_image" in result.metadata:
        container_info = result.metadata["container_image"]
        print(f"\n📦 Container Build:")
        print(f"   Image Tag: {container_info.get('image_tag')}")
        print(f"   Digest: {container_info.get('digest')}")
        print(f"   Size: {container_info.get('size_bytes', 0) / 1024 / 1024:.1f} MB")

    # 7. Detalhes de validação
    if "validation" in result.metadata:
        validation_info = result.metadata["validation"]
        print(f"\n🔒 Validation Results:")

        if "vulnerability_scan" in validation_info:
            vuln = validation_info["vulnerability_scan"]
            print(f"   Vulnerabilities:")
            print(f"     Critical: {vuln.get('critical_count', 0)}")
            print(f"     High: {vuln.get('high_count', 0)}")
            print(f"     Medium: {vuln.get('medium_count', 0)}")
            print(f"     Low: {vuln.get('low_count', 0)}")

        if "code_quality" in validation_info:
            quality = validation_info["code_quality"]
            print(f"   Code Quality:")
            print(f"     Coverage: {quality.get('coverage', 'N/A')}")
            print(f"     Bugs: {quality.get('bugs', 'N/A')}")
            print(f"     Vulnerabilities: {quality.get('vulnerabilities', 'N/A')}")

    # 8. Resultado final
    if result.status == "COMPLETED":
        print(f"\n✅ Pipeline completed successfully!")
        print(f"   {len(result.artifacts)} artifacts generated")
        for artifact in result.artifacts:
            print(f"   - {artifact.artifact_type}: {artifact.artifact_id}")
    elif result.status == "REQUIRES_REVIEW":
        print(f"\n⚠️ Pipeline requires review")
        print(f"   Confidence: {result.metadata.get('confidence', 'N/A')}")
        print(f"   Message: {result.error_message}")
    else:
        print(f"\n❌ Pipeline failed: {result.error_message}")

    return result

# Executar
if __name__ == "__main__":
    result = asyncio.run(complete_pipeline_with_validation())
```

### Saída Esperada

```
🚀 Starting complete pipeline...

============================================================
PIPELINE EXECUTION RESULT
============================================================
Status: COMPLETED
Stage Results:
  ✅ template_selection: COMPLETED
  ✅ code_composition: COMPLETED
  ✅ dockerfile_generation: COMPLETED
  ✅ container_build: COMPLETED
  ✅ validation: COMPLETED
  ✅ packaging: COMPLETED

📦 Container Build:
   Image Tag: secure-api:1.0.0
   Digest: sha256:abc123...
   Size: 145.2 MB

🔒 Validation Results:
   Vulnerabilities:
     Critical: 0
     High: 0
     Medium: 2
     Low: 5
   Code Quality:
     Coverage: 85.2%
     Bugs: 0
     Vulnerabilities: 0

✅ Pipeline completed successfully!
   3 artifacts generated
   - MICROSERVICE: artifact-001
   - DOCKERFILE: dockerfile-001
   - SBOM: sbom-001
```

---

## Exemplo 9: Tratamento de Erros e Retry

### Código

```python
import asyncio
import logging
from src.services.container_builder import ContainerBuilder
from src.services.pipeline_engine import PipelineEngine

async def build_with_retry(max_retries=3):
    """
    Executa build com retry em caso de falha
    """
    builder = ContainerBuilder(timeout_seconds=1800)

    for attempt in range(1, max_retries + 1):
        print(f"Attempt {attempt}/{max_retries}...")

        result = await builder.build_container(
            dockerfile_path="Dockerfile",
            build_context=".",
            image_tag=f"myapp:1.0.{attempt}"
        )

        if result.success:
            print(f"✅ Build succeeded on attempt {attempt}")
            return result

        # Verificar se é erro recuperável
        error = result.error_message or ""

        # Erros não recuperáveis
        if any(msg in error.lower() for msg in ["syntax error", "file not found"]):
            print(f"❌ Non-recoverable error: {error}")
            return result

        print(f"⚠️ Attempt {attempt} failed: {error}")

        if attempt < max_retries:
            wait_time = attempt * 5  # 5, 10, 15 segundos
            print(f"   Waiting {wait_time}s before retry...")
            await asyncio.sleep(wait_time)

    print(f"❌ All {max_retries} attempts failed")
    return result
```

---

## Exemplo 10: Build Paralelo de Múltiplas Imagens

### Código

```python
async def parallel_build():
    """
    Build múltiplas imagens em paralelo
    """
    services = [
        {"name": "api", "context": "./services/api", "tag": "api:1.0.0"},
        {"name": "worker", "context": "./services/worker", "tag": "worker:1.0.0"},
        {"name": "scheduler", "context": "./services/scheduler", "tag": "scheduler:1.0.0"},
    ]

    async def build_service(service):
        builder = ContainerBuilder()
        return await builder.build_container(
            dockerfile_path=f"{service['context']}/Dockerfile",
            build_context=service['context'],
            image_tag=service['tag']
        )

    # Executar builds em paralelo
    results = await asyncio.gather(
        *[build_service(s) for s in services],
        return_exceptions=True
    )

    # Verificar resultados
    for service, result in zip(services, results):
        if isinstance(result, Exception):
            print(f"❌ {service['name']}: {result}")
        elif result.success:
            print(f"✅ {service['name']}: {result.image_digest}")
        else:
            print(f"❌ {service['name']}: {result.error_message}")

    return results
```

---

## Referências

- [Dockerfile Generator Guide](dockerfile-generator-guide.md)
- [Container Builder Guide](container-builder-guide.md)
- [Architecture](architecture.md)
- [Troubleshooting](troubleshooting.md)
