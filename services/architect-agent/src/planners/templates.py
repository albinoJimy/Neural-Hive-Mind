"""Templates de prompts para LLM de arquitetura."""

from typing import Dict, Any


SYSTEM_PROMPT = """You are an expert software architect specializing in distributed systems, microservices, and cloud-native applications.

Your task is to analyze requirements and propose an appropriate software architecture. Consider:
- Scalability requirements
- Consistency requirements
- Latency requirements
- Team size and expertise
- Budget constraints
- Time-to-market constraints

Respond ONLY with valid JSON in the following format:
{
  "architecture_type": "microservices|monolith|serverless|hybrid",
  "components": [
    {"name": "component-name", "stack": "tech-stack", "replicas": 1, "ha": false}
  ],
  "patterns": ["repository", "cqrs", "event_sourcing", "saga", "circuit_breaker"],
  "rationale": "Clear explanation of architectural decisions"
}
"""


def get_user_prompt(requirements: Dict[str, Any]) -> str:
    """Gera prompt para o usuário baseado nos requisitos.

    Args:
        requirements: Dicionário com requisitos do sistema

    Returns:
        String com o prompt formatado
    """
    intent = requirements.get("intent", "unknown")
    scale = requirements.get("scale", "medium")
    consistency = requirements.get("consistency", "eventual")
    latency_p99_ms = requirements.get("latency_p99_ms", 500)
    team_size = requirements.get("team_size", 5)
    budget = requirements.get("budget", "medium")

    return f"""Analyze the following requirements and propose a software architecture:

**Intent:** {intent}
**Scale:** {scale} (expected requests per second)
**Consistency:** {consistency} (strong/eventual)
**Latency P99:** {latency_p99_ms}ms
**Team Size:** {team_size} developers
**Budget:** {budget}

Provide:
1. Architecture type (microservices/monolith/serverless/hybrid) with rationale
2. Components with tech stack and deployment details
3. Design patterns to apply (choose from: repository, cqrs, event_sourcing, saga, circuit_breaker, api_gateway, message_broker)
4. Clear rationale for each decision

Respond ONLY with valid JSON."""
