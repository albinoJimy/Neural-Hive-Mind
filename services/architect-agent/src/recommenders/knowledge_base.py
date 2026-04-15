"""Knowledge base for tech stack recommendations."""

TECH_KNOWLEDGE_BASE = {
    "backend": {
        "python": {
            "frameworks": {
                "fastapi": {
                    "pros": ["async nativo", "type hints", "performance", "API automática"],
                    "cons": ["ecossistema menor que Django/Flask"],
                    "use_cases": ["APIs REST", "microserviços", "high performance"],
                    "complexity": "media",
                    "learning_curve": "media"
                },
                "django": {
                    "pros": ["batteries included", "admin ORM", "ecosistema enorme"],
                    "cons": ["pesado", "sync por padrão", "verboso"],
                    "use_cases": ["monólitos", "CRUD apps", "prototipagem rápida"],
                    "complexity": "baixa",
                    "learning_curve": "baixa"
                }
            }
        },
        "nodejs": {
            "frameworks": {
                "express": {
                    "pros": ["minimal", "flexível", "ecossistema NPM"],
                    "cons": ["pouco opinionado", "requer setup manual"],
                    "use_cases": ["APIs", "microserviços", "serverless"],
                    "complexity": "baixa",
                    "learning_curve": "baixa"
                },
                "nest": {
                    "pros": ["TypeScript nativo", "estruturado", "injeção de dependências"],
                    "cons": ["curva de aprendizado", "verboso"],
                    "use_cases": ["apps empresariais", "microserviços"],
                    "complexity": "media",
                    "learning_curve": "media"
                }
            }
        }
    },
    "database": {
        "relational": {
            "postgresql": {
                "pros": ["ACID", "JSON support", "extensível", "open source"],
                "cons": ["setup mais complexo que SQLite"],
                "use_cases": ["dados estruturados", "transações", "analytics"],
                "complexity": "media",
                "cost": "baixo"
            },
            "mysql": {
                "pros": ["popular", "robusto", "boa performance"],
                "cons": ["licenciamento em alguns casos"],
                "use_cases": ["web apps", "e-commerce"],
                "complexity": "media",
                "cost": "baixo"
            }
        },
        "nosql": {
            "mongodb": {
                "pros": ["flexível", "schemaless", "boa para documentos"],
                "cons": ["sem ACID nativo em algumas operações"],
                "use_cases": ["dados dinâmicos", "prototipagem", "hierarchical data"],
                "complexity": "baixa",
                "cost": "baixo"
            },
            "redis": {
                "pros": ["rápido", "in-memory", "versátil"],
                "cons": ["volátil por padrão", "tamanho limitado"],
                "use_cases": ["cache", "sessions", "rate limiting", "queues"],
                "complexity": "baixa",
                "cost": "baixo"
            }
        }
    },
    "messaging": {
        "kafka": {
            "pros": ["escalável", "durável", "event streaming"],
            "cons": ["complexo", "requer ZooKeeper/KRaft"],
            "use_cases": ["event-driven", "microserviços", "data pipelines"],
            "complexity": "alta",
            "cost": "alto"
        },
        "rabbitmq": {
            "pros": ["flexível", "simples", "work queues"],
            "cons": ["menos escalável que Kafka"],
            "use_cases": ["work queues", "request/response"],
            "complexity": "media",
            "cost": "baixo"
        }
    }
}
