#!/usr/bin/env python3
"""
Debug Script para Semantic Translation Engine (STE) - Kafka Connection

Este script diagnostica problemas de conexão entre o STE e o Kafka, incluindo:
- Teste de conectividade TCP aos bootstrap servers
- Listagem de tópicos disponíveis no Kafka
- Comparação entre tópicos configurados e disponíveis
- Detecção de mismatches de nomenclatura (ex: '.' vs '-')

USO:
    python debug-ste-kafka-connection.py

    Ou dentro do pod do STE:
    kubectl exec -n semantic-translation <pod-name> -- python /app/scripts/debug-ste-kafka-connection.py

OUTPUT:
    - Console: Resumo dos resultados
    - Arquivo: /reports/ste-kafka-debug-results.md (relatório detalhado)

EXIT CODES:
    0 - Sucesso (todos os tópicos configurados estão disponíveis)
    1 - Erro (problemas de conectividade ou tópicos faltando)
"""

import os
import sys
import json
import socket
from datetime import datetime
from typing import Dict, List, Tuple, Any
from confluent_kafka.admin import AdminClient
import structlog

# Configurar logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer()
    ]
)
logger = structlog.get_logger()


def get_environment_config() -> Dict[str, Any]:
    """
    Lê configurações do STE das variáveis de ambiente.

    Returns:
        Dict com configurações: bootstrap_servers, topics, consumer_group, etc.
    """
    config = {}

    # Bootstrap servers (obrigatório)
    config['bootstrap_servers'] = os.getenv('KAFKA_BOOTSTRAP_SERVERS', '')

    # Consumer group
    config['consumer_group'] = os.getenv('KAFKA_CONSUMER_GROUP_ID', 'ste-consumer-group')

    # Security protocol
    config['security_protocol'] = os.getenv('KAFKA_SECURITY_PROTOCOL', 'PLAINTEXT')

    # Parsear tópicos (pode ser JSON ou CSV)
    # Baseado em services/semantic-translation-engine/src/config/settings.py:114-128
    kafka_topics_raw = os.getenv('KAFKA_TOPICS', '[]')

    try:
        # Tentar parsear como JSON primeiro
        config['topics'] = json.loads(kafka_topics_raw)
        logger.info("Tópicos parseados como JSON", topics=config['topics'])
    except json.JSONDecodeError:
        # Se falhar, tentar como CSV
        if kafka_topics_raw:
            config['topics'] = [t.strip() for t in kafka_topics_raw.split(',') if t.strip()]
            logger.info("Tópicos parseados como CSV", topics=config['topics'])
        else:
            config['topics'] = []
            logger.warning("KAFKA_TOPICS vazio ou inválido")

    logger.info("Configuração do ambiente carregada", config=config)
    return config


def test_tcp_connectivity(bootstrap_servers: str) -> Tuple[bool, str]:
    """
    Testa conectividade TCP aos bootstrap servers do Kafka.

    Args:
        bootstrap_servers: String com formato "host:port" ou "host1:port1,host2:port2"

    Returns:
        Tuple (sucesso: bool, mensagem: str)
    """
    if not bootstrap_servers:
        return False, "KAFKA_BOOTSTRAP_SERVERS não configurado"

    # Parsear múltiplos servidores
    servers = [s.strip() for s in bootstrap_servers.split(',')]
    results = []

    for server in servers:
        try:
            # Extrair host e porta
            if ':' not in server:
                results.append(f"❌ {server} - Formato inválido (esperado host:porta)")
                continue

            host, port_str = server.rsplit(':', 1)
            port = int(port_str)

            # Tentar conexão TCP
            socket.create_connection((host, port), timeout=5)
            results.append(f"✅ {server} - Conectividade OK")
            logger.info("Conectividade TCP OK", server=server)

        except socket.timeout:
            results.append(f"❌ {server} - Timeout (5s)")
            logger.error("Timeout de conexão TCP", server=server)
        except socket.gaierror as e:
            results.append(f"❌ {server} - DNS lookup falhou: {e}")
            logger.error("DNS lookup falhou", server=server, error=str(e))
        except ConnectionRefusedError:
            results.append(f"❌ {server} - Conexão recusada")
            logger.error("Conexão recusada", server=server)
        except Exception as e:
            results.append(f"❌ {server} - Erro: {e}")
            logger.error("Erro ao testar conectividade", server=server, error=str(e))

    # Determinar sucesso geral
    all_ok = all('✅' in r for r in results)
    message = "\n".join(results)

    return all_ok, message


def list_kafka_topics(bootstrap_servers: str) -> Tuple[bool, List[str], str]:
    """
    Lista todos os tópicos disponíveis no Kafka usando AdminClient.

    Args:
        bootstrap_servers: String com bootstrap servers

    Returns:
        Tuple (sucesso: bool, tópicos: List[str], mensagem_erro: str)
    """
    if not bootstrap_servers:
        return False, [], "KAFKA_BOOTSTRAP_SERVERS não configurado"

    try:
        # Criar AdminClient
        admin_config = {
            'bootstrap.servers': bootstrap_servers,
            'socket.timeout.ms': 10000,
            'api.timeout.ms': 10000
        }
        admin_client = AdminClient(admin_config)

        # Listar tópicos
        metadata = admin_client.list_topics(timeout=10)
        topics = list(metadata.topics.keys())

        # Filtrar tópicos internos do Kafka
        topics = [t for t in topics if not t.startswith('__')]

        logger.info("Tópicos listados com sucesso", count=len(topics))
        return True, sorted(topics), ""

    except Exception as e:
        error_msg = f"Erro ao listar tópicos: {type(e).__name__}: {e}"
        logger.error("Erro ao listar tópicos", error=str(e))
        return False, [], error_msg


def compare_topics(configured_topics: List[str], available_topics: List[str]) -> Dict[str, Any]:
    """
    Compara tópicos configurados vs. disponíveis no Kafka.

    Args:
        configured_topics: Lista de tópicos configurados no STE
        available_topics: Lista de tópicos disponíveis no Kafka

    Returns:
        Dict com: missing, extra, exact_matches, possible_matches
    """
    configured_set = set(configured_topics)
    available_set = set(available_topics)

    # Tópicos que existem exatamente
    exact_matches = configured_set & available_set

    # Tópicos configurados que não existem
    missing = configured_set - available_set

    # Tópicos disponíveis que não estão configurados
    extra = available_set - configured_set

    # Detectar possíveis matches com nomenclatura diferente
    possible_matches = []
    for conf_topic in missing:
        # Tentar substituir '.' por '-' e vice-versa
        variant1 = conf_topic.replace('.', '-')
        variant2 = conf_topic.replace('-', '.')

        for avail_topic in available_topics:
            if avail_topic in exact_matches:
                continue

            if avail_topic == variant1 or avail_topic == variant2:
                possible_matches.append({
                    'configured': conf_topic,
                    'available': avail_topic,
                    'reason': 'Diferença de nomenclatura (. vs -)'
                })

    result = {
        'exact_matches': sorted(list(exact_matches)),
        'missing': sorted(list(missing)),
        'extra': sorted(list(extra)),
        'possible_matches': possible_matches
    }

    logger.info("Comparação de tópicos concluída", result=result)
    return result


def generate_markdown_report(results: Dict[str, Any], output_path: str) -> None:
    """
    Gera relatório em Markdown com os resultados do diagnóstico.

    Args:
        results: Dict com todos os resultados das análises
        output_path: Caminho para salvar o relatório
    """
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Determinar status geral
    status = "✅ OK" if results.get('overall_success', False) else "❌ ERRO"

    report_lines = [
        "# Relatório de Debug - STE Kafka Connection",
        "",
        f"**Data/Hora**: {timestamp}",
        f"**Status Geral**: {status}",
        "",
        "---",
        "",
        "## 1. Sumário Executivo",
        "",
    ]

    # Sumário executivo
    if results.get('overall_success', False):
        report_lines.append("✅ Todos os tópicos configurados estão disponíveis no Kafka.")
        report_lines.append("✅ Conectividade TCP OK.")
    else:
        report_lines.append("❌ Problemas identificados:")
        if not results.get('tcp_success', False):
            report_lines.append("  - Falha na conectividade TCP")
        if results.get('comparison', {}).get('missing'):
            report_lines.append(f"  - {len(results['comparison']['missing'])} tópicos configurados não encontrados")
        if results.get('comparison', {}).get('possible_matches'):
            report_lines.append(f"  - {len(results['comparison']['possible_matches'])} possíveis mismatches de nomenclatura detectados")

    report_lines.extend([
        "",
        "---",
        "",
        "## 2. Configuração do STE",
        "",
        "### Variáveis de Ambiente",
        "",
        f"- **KAFKA_BOOTSTRAP_SERVERS**: `{results['config']['bootstrap_servers']}`",
        f"- **KAFKA_CONSUMER_GROUP_ID**: `{results['config']['consumer_group']}`",
        f"- **KAFKA_SECURITY_PROTOCOL**: `{results['config']['security_protocol']}`",
        "",
        "### Tópicos Configurados",
        "",
    ])

    if results['config']['topics']:
        report_lines.append("```json")
        report_lines.append(json.dumps(results['config']['topics'], indent=2))
        report_lines.append("```")
    else:
        report_lines.append("⚠️ Nenhum tópico configurado")

    report_lines.extend([
        "",
        "---",
        "",
        "## 3. Teste de Conectividade TCP",
        "",
    ])

    report_lines.append(results['tcp_message'])

    report_lines.extend([
        "",
        "---",
        "",
        "## 4. Tópicos Disponíveis no Kafka",
        "",
    ])

    if results.get('kafka_topics_success', False):
        report_lines.append(f"**Total**: {len(results['kafka_topics'])} tópicos")
        report_lines.append("")
        for topic in results['kafka_topics']:
            report_lines.append(f"- `{topic}`")
    else:
        report_lines.append(f"❌ **Erro ao listar tópicos**: {results.get('kafka_topics_error', 'Erro desconhecido')}")

    report_lines.extend([
        "",
        "---",
        "",
        "## 5. Análise de Comparação",
        "",
    ])

    comparison = results.get('comparison', {})

    # Exact matches
    report_lines.append("### ✅ Tópicos Configurados e Disponíveis (Exact Matches)")
    report_lines.append("")
    if comparison.get('exact_matches'):
        for topic in comparison['exact_matches']:
            report_lines.append(f"- `{topic}`")
    else:
        report_lines.append("_Nenhum_")
    report_lines.append("")

    # Missing topics
    report_lines.append("### ❌ Tópicos Configurados NÃO Encontrados (Missing)")
    report_lines.append("")
    if comparison.get('missing'):
        for topic in comparison['missing']:
            report_lines.append(f"- `{topic}`")
    else:
        report_lines.append("_Nenhum_")
    report_lines.append("")

    # Possible matches
    report_lines.append("### ⚠️ Possíveis Matches com Nomenclatura Diferente")
    report_lines.append("")
    if comparison.get('possible_matches'):
        report_lines.append("| Configurado | Disponível | Motivo |")
        report_lines.append("|-------------|------------|--------|")
        for match in comparison['possible_matches']:
            report_lines.append(f"| `{match['configured']}` | `{match['available']}` | {match['reason']} |")
    else:
        report_lines.append("_Nenhum_")
    report_lines.append("")

    # Extra topics
    report_lines.append("### ℹ️ Tópicos Disponíveis NÃO Configurados (Extra)")
    report_lines.append("")
    if comparison.get('extra'):
        for topic in comparison['extra']:
            report_lines.append(f"- `{topic}`")
    else:
        report_lines.append("_Nenhum_")
    report_lines.append("")

    report_lines.extend([
        "---",
        "",
        "## 6. Diagnóstico e Recomendações",
        "",
    ])

    # Gerar recomendações baseadas nos resultados
    if results.get('overall_success', False):
        report_lines.append("✅ Nenhum problema detectado. O STE está corretamente configurado para consumir dos tópicos Kafka.")
    else:
        report_lines.append("### Problemas Identificados e Soluções:")
        report_lines.append("")

        if not results.get('tcp_success', False):
            report_lines.extend([
                "#### 1. Falha de Conectividade TCP",
                "",
                "**Problema**: Não foi possível estabelecer conexão TCP aos bootstrap servers.",
                "",
                "**Possíveis Causas**:",
                "- DNS não resolve os hostnames do Kafka",
                "- Firewall ou Network Policy bloqueando a conexão",
                "- Kafka não está rodando ou indisponível",
                "",
                "**Solução**:",
                "```bash",
                "# Testar DNS",
                "nslookup kafka-bootstrap.kafka.svc.cluster.local",
                "",
                "# Testar conectividade",
                "telnet kafka-bootstrap.kafka.svc.cluster.local 9092",
                "",
                "# Verificar Network Policies",
                "kubectl get networkpolicies -n semantic-translation",
                "```",
                "",
            ])

        if comparison.get('missing'):
            report_lines.extend([
                "#### 2. Tópicos Configurados Não Encontrados",
                "",
                f"**Problema**: {len(comparison['missing'])} tópico(s) configurado(s) no STE não existe(m) no Kafka.",
                "",
                "**Tópicos faltando**:",
            ])
            for topic in comparison['missing']:
                report_lines.append(f"- `{topic}`")
            report_lines.extend([
                "",
                "**Solução**:",
                "```bash",
                "# Criar tópicos manualmente",
                "kubectl exec -n kafka kafka-0 -- kafka-topics \\",
                "  --bootstrap-server localhost:9092 \\",
                "  --create --topic <topic-name> \\",
                "  --partitions 3 --replication-factor 2",
                "",
                "# Ou aplicar via Helm/Kubernetes",
                "kubectl apply -f k8s/kafka-topics/",
                "```",
                "",
            ])

        if comparison.get('possible_matches'):
            report_lines.extend([
                "#### 3. Mismatch de Nomenclatura Detectado",
                "",
                f"**Problema**: {len(comparison['possible_matches'])} tópico(s) com nomenclatura diferente detectado(s).",
                "",
                "**Matches possíveis**:",
            ])
            for match in comparison['possible_matches']:
                report_lines.append(f"- Configurado: `{match['configured']}` → Disponível: `{match['available']}`")
            report_lines.extend([
                "",
                "**Solução**: Atualizar variável de ambiente `KAFKA_TOPICS` no deployment do STE:",
                "```bash",
                "# Editar ConfigMap ou Deployment",
                "kubectl edit deployment semantic-translation-engine -n semantic-translation",
                "",
                "# Ou atualizar values.yaml do Helm chart e fazer upgrade",
                "helm upgrade semantic-translation-engine ./helm-charts/semantic-translation-engine \\",
                "  --namespace semantic-translation \\",
                "  --set kafka.topics='[\"intentions-business\",\"intentions-technical\",...]'",
                "```",
                "",
            ])

    report_lines.extend([
        "---",
        "",
        "## 7. Comandos Úteis para Troubleshooting",
        "",
        "### Listar Tópicos no Kafka",
        "```bash",
        "kubectl exec -n kafka kafka-0 -- kafka-topics \\",
        "  --bootstrap-server localhost:9092 --list",
        "```",
        "",
        "### Descrever Tópico Específico",
        "```bash",
        "kubectl exec -n kafka kafka-0 -- kafka-topics \\",
        "  --bootstrap-server localhost:9092 \\",
        "  --describe --topic <topic-name>",
        "```",
        "",
        "### Verificar Consumer Groups",
        "```bash",
        "kubectl exec -n kafka kafka-0 -- kafka-consumer-groups \\",
        "  --bootstrap-server localhost:9092 --list",
        "",
        "kubectl exec -n kafka kafka-0 -- kafka-consumer-groups \\",
        "  --bootstrap-server localhost:9092 \\",
        "  --describe --group ste-consumer-group",
        "```",
        "",
        "### Ver Logs do STE",
        "```bash",
        "kubectl logs -n semantic-translation deployment/semantic-translation-engine --tail=100 -f",
        "```",
        "",
        "### Testar Consumo Manual",
        "```bash",
        "kubectl exec -n kafka kafka-0 -- kafka-console-consumer \\",
        "  --bootstrap-server localhost:9092 \\",
        "  --topic intentions-business \\",
        "  --from-beginning --max-messages 10",
        "```",
        "",
        "---",
        "",
        "## 8. Referências",
        "",
        "- **Código do STE**: `services/semantic-translation-engine/src/consumers/intent_consumer.py`",
        "- **Configuração do STE**: `services/semantic-translation-engine/src/config/settings.py`",
        "- **Relatório de Teste E2E**: `reports/teste-e2e-manual-20251124.md`",
        "- **Script de Teste EOS**: `scripts/kafka/test-eos.py`",
        "",
    ])

    # Salvar relatório
    try:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(report_lines))
        logger.info("Relatório Markdown gerado", path=output_path)
    except Exception as e:
        logger.error("Erro ao salvar relatório", path=output_path, error=str(e))
        raise


def main() -> int:
    """
    Função principal que executa todos os diagnósticos.

    Returns:
        Exit code (0 = sucesso, 1 = erro)
    """
    print("=" * 60)
    print("Debug STE Kafka Connection")
    print("=" * 60)
    print()

    results = {}

    try:
        # 1. Ler configuração do ambiente
        print("1. Lendo configuração do ambiente...")
        config = get_environment_config()
        results['config'] = config
        print(f"   ✓ Bootstrap servers: {config['bootstrap_servers']}")
        print(f"   ✓ Tópicos configurados: {len(config['topics'])}")
        print()

        # 2. Testar conectividade TCP
        print("2. Testando conectividade TCP aos bootstrap servers...")
        tcp_success, tcp_message = test_tcp_connectivity(config['bootstrap_servers'])
        results['tcp_success'] = tcp_success
        results['tcp_message'] = tcp_message
        print(tcp_message)
        print()

        # 3. Listar tópicos do Kafka
        print("3. Listando tópicos disponíveis no Kafka...")
        kafka_topics_success, kafka_topics, kafka_topics_error = list_kafka_topics(config['bootstrap_servers'])
        results['kafka_topics_success'] = kafka_topics_success
        results['kafka_topics'] = kafka_topics
        results['kafka_topics_error'] = kafka_topics_error

        if kafka_topics_success:
            print(f"   ✓ {len(kafka_topics)} tópicos encontrados")
        else:
            print(f"   ✗ Erro: {kafka_topics_error}")
        print()

        # 4. Comparar tópicos
        print("4. Comparando tópicos configurados vs. disponíveis...")
        if kafka_topics_success:
            comparison = compare_topics(config['topics'], kafka_topics)
            results['comparison'] = comparison

            print(f"   ✓ Exact matches: {len(comparison['exact_matches'])}")
            print(f"   ✗ Missing: {len(comparison['missing'])}")
            print(f"   ⚠ Possible matches: {len(comparison['possible_matches'])}")
            print(f"   ℹ Extra: {len(comparison['extra'])}")

            if comparison['possible_matches']:
                print("\n   Possíveis mismatches de nomenclatura detectados:")
                for match in comparison['possible_matches']:
                    print(f"     • {match['configured']} → {match['available']}")
        else:
            comparison = {'exact_matches': [], 'missing': config['topics'], 'extra': [], 'possible_matches': []}
            results['comparison'] = comparison
            print("   ✗ Não foi possível comparar (falha ao listar tópicos)")
        print()

        # 5. Determinar status geral
        overall_success = (
            tcp_success and
            kafka_topics_success and
            len(comparison['missing']) == 0 and
            len(comparison['possible_matches']) == 0
        )
        results['overall_success'] = overall_success

        # 6. Gerar relatório
        print("5. Gerando relatório Markdown...")
        output_path = '/reports/ste-kafka-debug-results.md'
        generate_markdown_report(results, output_path)
        print(f"   ✓ Relatório salvo em: {output_path}")
        print()

        # 7. Imprimir resumo final
        print("=" * 60)
        print("RESUMO")
        print("=" * 60)
        if overall_success:
            print("✅ STATUS: OK")
            print("Todos os tópicos configurados estão disponíveis no Kafka.")
        else:
            print("❌ STATUS: ERRO")
            print("Problemas detectados:")
            if not tcp_success:
                print("  - Falha na conectividade TCP")
            if comparison['missing']:
                print(f"  - {len(comparison['missing'])} tópicos configurados não encontrados")
            if comparison['possible_matches']:
                print(f"  - {len(comparison['possible_matches'])} possíveis mismatches de nomenclatura")
            print(f"\nConsulte o relatório para mais detalhes: {output_path}")
        print("=" * 60)

        return 0 if overall_success else 1

    except Exception as e:
        logger.error("Erro durante execução do diagnóstico", error=str(e))
        print(f"\n❌ ERRO FATAL: {e}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
