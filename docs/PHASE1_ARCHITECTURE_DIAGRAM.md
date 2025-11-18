# Phase 1 Architecture Diagrams
## Neural Hive-Mind - Foundation Layer

**Version**: 1.0
**Date**: November 12, 2025

---

## 📐 Overview

This document provides comprehensive architecture diagrams for Phase 1 of the Neural Hive-Mind project using Mermaid syntax.

---

## 1. System Overview

### 1.1 High-Level Architecture

```mermaid
graph TB
    subgraph "Client Layer"
        USER[User/Application]
    end

    subgraph "Ingestion Layer"
        GW[Gateway de Intenções<br/>v1.0.0]
    end

    subgraph "Cognitive Processing Layer"
        STE[Semantic Translation Engine<br/>v1.0.0]
        SB[Specialist Business<br/>v1.0.7]
        ST[Specialist Technical<br/>v1.0.7]
        SBeh[Specialist Behavior<br/>v1.0.7]
        SE[Specialist Evolution<br/>v1.0.7]
        SA[Specialist Architecture<br/>v1.0.7]
        CE[Consensus Engine<br/>v1.0.7]
    end

    subgraph "Memory Layer"
        direction LR
        REDIS[(Redis<br/>HOT)]
        MONGO[(MongoDB<br/>WARM)]
        NEO4J[(Neo4j<br/>SEMANTIC)]
        CLICK[(ClickHouse<br/>COLD)]
    end

    subgraph "Messaging Backbone"
        KAFKA[Apache Kafka<br/>15 Topics]
    end

    subgraph "Governance Layer"
        OPA[OPA Gatekeeper]
        LEDGER[Cognitive Ledger<br/>MongoDB]
    end

    USER -->|HTTP POST /intentions| GW
    GW -->|intentions.*| KAFKA
    KAFKA -->|intentions.*| STE
    STE -->|plans.ready| KAFKA
    KAFKA -->|plans.ready| CE

    CE -.gRPC.-> SB
    CE -.gRPC.-> ST
    CE -.gRPC.-> SBeh
    CE -.gRPC.-> SE
    CE -.gRPC.-> SA

    CE -->|plans.consensus| KAFKA
    CE -->|decisions| LEDGER

    STE -.query.-> NEO4J
    CE -.pheromones.-> REDIS
    CE -.decisions.-> MONGO
    STE -.plans.-> MONGO

    OPA -.policies.-> CE
    OPA -.policies.-> STE

    style GW fill:#4CAF50
    style CE fill:#2196F3
    style STE fill:#FF9800
    style KAFKA fill:#FFC107
    style LEDGER fill:#9C27B0
```

---

## 2. Data Flow Diagram

### 2.1 Intent to Decision Flow

```mermaid
sequenceDiagram
    participant User
    participant Gateway
    participant Kafka
    participant STE as Semantic<br/>Translation<br/>Engine
    participant Neo4j
    participant Specialists
    participant Consensus
    participant MongoDB
    participant Redis

    User->>Gateway: POST /intentions<br/>{intent}
    Gateway->>Gateway: Validate & classify
    Gateway->>Kafka: Publish to intentions.*
    Gateway-->>User: 202 Accepted

    Kafka->>STE: Consume intent
    STE->>Neo4j: Query knowledge graph
    Neo4j-->>STE: Context & ontologies
    STE->>STE: Generate DAG<br/>Calculate risk
    STE->>MongoDB: Store plan (ledger)
    STE->>Kafka: Publish to plans.ready

    Kafka->>Consensus: Consume plan
    Consensus->>Specialists: gRPC EvaluatePlan (5 parallel calls)
    Specialists-->>Consensus: Opinions with confidence
    Consensus->>Consensus: Bayesian aggregation<br/>Voting ensemble
    Consensus->>MongoDB: Store decision (ledger)
    Consensus->>Redis: Publish pheromones (TTL)
    Consensus->>Kafka: Publish to plans.consensus

    Note over Consensus,MongoDB: 100% auditability<br/>SHA-256 hashes<br/>Explainability tokens
```

---

## 3. Component Topology

### 3.1 Kubernetes Deployment Topology

```mermaid
graph TB
    subgraph "Cluster: neural-hive-dev"
        subgraph "Namespace: kafka"
            K1[kafka-0]
            K2[kafka-1]
            K3[kafka-2]
        end

        subgraph "Namespace: mongodb-cluster"
            M1[mongodb-0]
            M2[mongodb-1]
            M3[mongodb-2]
        end

        subgraph "Namespace: redis-cluster"
            R1[redis-0]
        end

        subgraph "Namespace: neo4j-cluster"
            N1[neo4j-0]
        end

        subgraph "Namespace: gateway-intencoes"
            GW1[gateway-pod]
        end

        subgraph "Namespace: semantic-translation-engine"
            STE1[ste-pod]
        end

        subgraph "Namespace: specialist-business"
            SB1[specialist-business-pod]
        end

        subgraph "Namespace: specialist-technical"
            ST1[specialist-technical-pod]
        end

        subgraph "Namespace: specialist-behavior"
            SBeh1[specialist-behavior-pod]
        end

        subgraph "Namespace: specialist-evolution"
            SE1[specialist-evolution-pod]
        end

        subgraph "Namespace: specialist-architecture"
            SA1[specialist-architecture-pod]
        end

        subgraph "Namespace: consensus-engine"
            CE1[consensus-engine-pod]
        end

        subgraph "Namespace: memory-layer-api"
            ML1[memory-layer-api-pod]
        end

        subgraph "Namespace: gatekeeper-system"
            OPA1[gatekeeper-controller]
            OPA2[gatekeeper-audit]
            OPA3[gatekeeper-webhook]
        end
    end

    style K1 fill:#FFC107
    style M1 fill:#4CAF50
    style R1 fill:#F44336
    style N1 fill:#00BCD4
```

---

## 4. Memory Architecture

### 4.1 4-Tier Memory Layer

```mermaid
graph LR
    subgraph "Memory Layer API"
        API[Unified API]
    end

    subgraph "HOT Memory (Sub-second)"
        REDIS[(Redis<br/>5-15 min TTL)]
    end

    subgraph "WARM Memory (Seconds)"
        MONGO[(MongoDB<br/>30 days retention)]
    end

    subgraph "SEMANTIC Memory (Context)"
        NEO4J[(Neo4j<br/>Knowledge Graph)]
    end

    subgraph "COLD Memory (Analytics)"
        CLICK[(ClickHouse<br/>18 months retention)]
    end

    API -->|Write/Read| REDIS
    API -->|Write/Read| MONGO
    API -->|Query| NEO4J
    API -->|Analytics| CLICK

    REDIS -.fallback.-> MONGO
    MONGO -.batch sync.-> CLICK

    style REDIS fill:#F44336
    style MONGO fill:#4CAF50
    style NEO4J fill:#00BCD4
    style CLICK fill:#9C27B0
```

### 4.2 Memory Access Patterns

```mermaid
flowchart TD
    START([Request])
    CHECK_HOT{In Redis?}
    CHECK_WARM{In MongoDB?}
    CHECK_COLD{In ClickHouse?}

    REDIS[(Redis<br/>Cache Hit)]
    MONGO[(MongoDB<br/>Ledger Hit)]
    CLICK[(ClickHouse<br/>Archive Hit)]
    NOTFOUND[404 Not Found]

    START --> CHECK_HOT
    CHECK_HOT -->|Yes<br/><5ms| REDIS
    CHECK_HOT -->|No| CHECK_WARM
    CHECK_WARM -->|Yes<br/><50ms| MONGO
    CHECK_WARM -->|No| CHECK_COLD
    CHECK_COLD -->|Yes<br/><200ms| CLICK
    CHECK_COLD -->|No| NOTFOUND

    REDIS --> RETURN([Return Result])
    MONGO --> RETURN
    CLICK --> RETURN
    NOTFOUND --> RETURN

    style REDIS fill:#F44336
    style MONGO fill:#4CAF50
    style CLICK fill:#9C27B0
```

---

## 5. Consensus Mechanism

### 5.1 Consensus Flow

```mermaid
flowchart TD
    START([Cognitive Plan])
    INVOKE[Invoke 5 Specialists<br/>in Parallel]

    SB[Business<br/>Opinion]
    ST[Technical<br/>Opinion]
    SBeh[Behavior<br/>Opinion]
    SE[Evolution<br/>Opinion]
    SA[Architecture<br/>Opinion]

    COLLECT[Collect Opinions]
    BAYESIAN[Bayesian Model<br/>Averaging]
    VOTING[Voting Ensemble<br/>Weighted]
    FALLBACK{Compliance<br/>Check}
    DETERMINISTIC[Deterministic<br/>Fallback]
    EXPLAINABILITY[Generate<br/>Explainability]
    LEDGER[Store in Ledger<br/>SHA-256 Hash]
    PHEROMONES[Publish<br/>Pheromones]
    KAFKA[Publish to<br/>plans.consensus]

    START --> INVOKE
    INVOKE --> SB & ST & SBeh & SE & SA
    SB & ST & SBeh & SE & SA --> COLLECT
    COLLECT --> BAYESIAN
    BAYESIAN --> VOTING
    VOTING --> FALLBACK
    FALLBACK -->|Pass| EXPLAINABILITY
    FALLBACK -->|Fail| DETERMINISTIC
    DETERMINISTIC --> EXPLAINABILITY
    EXPLAINABILITY --> LEDGER
    LEDGER --> PHEROMONES
    PHEROMONES --> KAFKA

    style BAYESIAN fill:#2196F3
    style VOTING fill:#4CAF50
    style DETERMINISTIC fill:#FF9800
    style LEDGER fill:#9C27B0
```

---

## 6. Observability Architecture

### 6.1 Monitoring Stack (Planned)

```mermaid
graph TB
    subgraph "Services"
        GW[Gateway]
        STE[STE]
        SPEC[Specialists]
        CE[Consensus]
    end

    subgraph "Metrics Collection"
        SM[ServiceMonitors<br/>9+ Configured]
        PROM[Prometheus<br/>Pending Deployment]
    end

    subgraph "Visualization"
        GRAF[Grafana<br/>28 Dashboards]
    end

    subgraph "Tracing"
        JAEGER[Jaeger<br/>Pending Deployment]
    end

    subgraph "Alerting"
        AM[Alertmanager<br/>19 Rule Files]
    end

    GW -->|/metrics| SM
    STE -->|/metrics| SM
    SPEC -->|/metrics| SM
    CE -->|/metrics| SM

    SM --> PROM
    PROM --> GRAF
    PROM --> AM

    GW -.traces.-> JAEGER
    STE -.traces.-> JAEGER
    SPEC -.traces.-> JAEGER
    CE -.traces.-> JAEGER

    style PROM fill:#E64A19
    style GRAF fill:#FF9800
    style JAEGER fill:#00BCD4
```

---

## 7. Governance & Security

### 7.1 Governance Architecture

```mermaid
graph TB
    subgraph "Policy Engine"
        OPA[OPA Gatekeeper]
        CT[ConstraintTemplates<br/>4+ Templates]
        CONST[Constraints<br/>2+ Active]
    end

    subgraph "Services"
        GW[Gateway]
        STE[STE]
        CE[Consensus]
    end

    subgraph "Audit & Compliance"
        LEDGER[(Cognitive Ledger<br/>SHA-256 Hashes)]
        EXPL[(Explainability Ledger<br/>SHAP/LIME)]
        PHER[(Pheromones<br/>TTL-based)]
    end

    OPA --> CT
    CT --> CONST
    CONST -.enforce.-> GW
    CONST -.enforce.-> STE
    CONST -.enforce.-> CE

    CE --> LEDGER
    CE --> EXPL
    CE --> PHER

    LEDGER -.audit.-> AUDIT[Audit API]
    EXPL -.explain.-> EXPLAPI[Explainability API]

    style OPA fill:#4CAF50
    style LEDGER fill:#9C27B0
    style EXPL fill:#FF9800
```

---

## 8. Network Topology

### 8.1 Service Communication

```mermaid
graph LR
    subgraph "External"
        USER[User/App]
    end

    subgraph "Ingress"
        GW[Gateway<br/>:8000 HTTP]
    end

    subgraph "Kafka Bus"
        KAFKA[Kafka<br/>:9092]
    end

    subgraph "Cognitive Services"
        STE[STE<br/>:8000 HTTP]
        CE[Consensus<br/>:8000 HTTP]
        SB[Business<br/>:50051 gRPC]
        ST[Technical<br/>:50051 gRPC]
        SBeh[Behavior<br/>:50051 gRPC]
        SE[Evolution<br/>:50051 gRPC]
        SA[Architecture<br/>:50051 gRPC]
    end

    subgraph "Storage"
        MONGO[(MongoDB<br/>:27017)]
        REDIS[(Redis<br/>:6379)]
        NEO4J[(Neo4j<br/>:7687 Bolt)]
    end

    USER -->|HTTP| GW
    GW <-->|Produce/Consume| KAFKA
    STE <-->|Produce/Consume| KAFKA
    CE <-->|Produce/Consume| KAFKA

    CE -->|gRPC| SB & ST & SBeh & SE & SA

    STE -->|Write| MONGO
    CE -->|Write| MONGO
    CE -->|Write| REDIS
    STE -->|Query| NEO4J

    style KAFKA fill:#FFC107
    style GW fill:#4CAF50
    style CE fill:#2196F3
```

---

## 9. Deployment Pipeline (Future)

### 9.1 CI/CD Flow (Planned for Phase 2)

```mermaid
flowchart LR
    GIT[Git Push] --> CI[CI Pipeline<br/>GitHub Actions]
    CI --> BUILD[Build Images]
    CI --> TEST[Run Tests]
    TEST --> SCAN[Security Scan]
    SCAN --> PUSH[Push to Registry]
    PUSH --> CD[CD Pipeline<br/>ArgoCD]
    CD --> DEV[Deploy to Dev]
    DEV --> VALIDATE[Validation Tests]
    VALIDATE --> STAGING[Deploy to Staging]
    STAGING --> PROD[Deploy to Prod<br/>Blue-Green]

    style CI fill:#4CAF50
    style TEST fill:#FF9800
    style PROD fill:#2196F3
```

---

## 10. Resource Allocation

### 10.1 CPU & Memory Distribution

```mermaid
pie title CPU Allocation (7550m total)
    "Consensus Engine" : 1000
    "STE" : 1000
    "Gateway" : 500
    "Specialists (5x500m)" : 2500
    "Memory API" : 500
    "Infrastructure" : 2050
```

```mermaid
pie title Memory Allocation (~6Gi total)
    "Consensus Engine" : 1024
    "STE" : 1024
    "Specialists (5x512Mi)" : 2560
    "Gateway" : 512
    "Memory API" : 512
    "Infrastructure" : 468
```

---

## 📊 Diagram Legend

| Symbol | Meaning |
|--------|---------|
| `-->` | Synchronous communication (HTTP, gRPC) |
| `-.->` | Asynchronous communication (Kafka, events) |
| `===>` | Data flow |
| `[Component]` | Service/Application |
| `[(Database)]` | Data store |
| `{Decision}` | Decision point |

---

**Document Version**: 1.0
**Last Updated**: November 12, 2025
**Maintained by**: Neural Hive-Mind Team
