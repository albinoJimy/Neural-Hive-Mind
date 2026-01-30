#!/usr/bin/env python3
"""
Diagnóstico Completo - Gateway Neural Hive-Mind

Script para verificar e diagnosticar problemas comuns no gateway:
1. Redis Health Check
2. OTEL Health Check
3. Configurações de ambiente
4. Conectividade com serviços

Usage:
    python diagnose_gateway.py [--namespace <namespace>] [--pod <pod-name>]

Exemplos:
    # Diagnóstico automático (encontra pod automaticamente)
    python diagnose_gateway.py
    
    # Diagnóstico em namespace específico
    python diagnose_gateway.py --namespace gateway-intencoes
    
    # Diagnóstico em pod específico
    python diagnose_gateway.py --pod gateway-intencoes-7c4b8f9d5-x2k9m
"""

import argparse
import json
import subprocess
import sys
from typing import Optional, Dict, Any, List


class Colors:
    """Cores para output no terminal."""
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


def run_kubectl(cmd: str, namespace: Optional[str] = None) -> tuple:
    """Executa comando kubectl e retorna (stdout, stderr, returncode)."""
    full_cmd = "kubectl"
    if namespace:
        full_cmd += f" -n {namespace}"
    full_cmd += f" {cmd}"
    
    try:
        result = subprocess.run(
            full_cmd.split(),
            capture_output=True,
            text=True,
            timeout=30
        )
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return "", "Timeout", 1
    except Exception as e:
        return "", str(e), 1


def find_gateway_pod(namespace: str) -> Optional[str]:
    """Encontra o pod do gateway automaticamente."""
    stdout, _, rc = run_kubectl(
        "get pods -l app=gateway-intencoes -o jsonpath='{.items[0].metadata.name}'",
        namespace
    )
    if rc == 0 and stdout:
        return stdout.strip().strip("'")
    return None


def check_pod_status(namespace: str, pod_name: str) -> Dict[str, Any]:
    """Verifica status do pod."""
    stdout, _, rc = run_kubectl(
        f"get pod {pod_name} -o json",
        namespace
    )
    if rc != 0:
        return {"error": "Failed to get pod status"}
    
    try:
        pod_info = json.loads(stdout)
        return {
            "phase": pod_info.get("status", {}).get("phase", "Unknown"),
            "ready": any(
                cs.get("ready", False) 
                for cs in pod_info.get("status", {}).get("containerStatuses", [])
            ),
            "restart_count": sum(
                cs.get("restartCount", 0)
                for cs in pod_info.get("status", {}).get("containerStatuses", [])
            ),
            "conditions": pod_info.get("status", {}).get("conditions", [])
        }
    except json.JSONDecodeError:
        return {"error": "Failed to parse pod info"}


def check_environment_variables(namespace: str, pod_name: str) -> Dict[str, Any]:
    """Verifica variáveis de ambiente críticas."""
    stdout, _, rc = run_kubectl(
        f"exec {pod_name} -- env | grep -E 'OTEL|REDIS|KAFKA'",
        namespace
    )
    
    env_vars = {}
    if rc == 0:
        for line in stdout.strip().split("\n"):
            if "=" in line:
                key, value = line.split("=", 1)
                env_vars[key] = value
    
    # Verificar problemas conhecidos
    issues = []
    
    # Verificar OTEL endpoint
    otel_endpoint = env_vars.get("OTEL_ENDPOINT", "")
    if otel_endpoint.startswith("https://"):
        issues.append({
            "severity": "HIGH",
            "message": f"OTEL_ENDPOINT usa HTTPS mas collector geralmente usa HTTP: {otel_endpoint}",
            "fix": "Mudar para http:// no ConfigMap/values"
        })
    
    # Verificar Redis
    redis_nodes = env_vars.get("REDIS_CLUSTER_NODES", "")
    if not redis_nodes:
        issues.append({
            "severity": "HIGH",
            "message": "REDIS_CLUSTER_NODES não configurado",
            "fix": "Verificar ConfigMap e Secret"
        })
    
    return {
        "env_vars": env_vars,
        "issues": issues
    }


def check_health_endpoint(namespace: str, pod_name: str) -> Dict[str, Any]:
    """Verifica endpoint de health."""
    stdout, stderr, rc = run_kubectl(
        f"exec {pod_name} -- wget -qO- http://localhost:8000/health 2>&1",
        namespace
    )
    
    if rc != 0:
        return {
            "status": "ERROR",
            "error": stderr or stdout,
            "http_code": None
        }
    
    try:
        health_data = json.loads(stdout)
        return {
            "status": health_data.get("status", "unknown"),
            "components": health_data.get("components", {}),
            "error": None,
            "http_code": 200
        }
    except json.JSONDecodeError:
        return {
            "status": "PARSE_ERROR",
            "raw_output": stdout[:500],
            "error": "Failed to parse health response",
            "http_code": None
        }


def check_redis_ping(namespace: str, pod_name: str) -> Dict[str, Any]:
    """Verifica se RedisClient.ping funciona corretamente."""
    test_script = '''
import asyncio
import sys
sys.path.insert(0, '/app/src')

try:
    from cache.redis_client import get_redis_client
    
    async def test():
        client = await get_redis_client()
        
        # Testar se ping é callable
        if not hasattr(client, 'ping'):
            print("ERROR: RedisClient não tem atributo 'ping'")
            return
        
        ping_method = client.ping
        
        # Testar se é coroutine
        import inspect
        is_coro = inspect.iscoroutinefunction(ping_method)
        print(f"ping é coroutine: {is_coro}")
        
        # Testar chamada
        try:
            if is_coro:
                result = await ping_method()
            else:
                result = ping_method()
            print(f"ping resultado: {result}")
            print(f"ping tipo resultado: {type(result)}")
        except Exception as e:
            print(f"ping erro: {e}")
    
    asyncio.run(test())
except Exception as e:
    print(f"IMPORT ERROR: {e}")
'''
    
    # Escrever script temporário no pod
    _, stderr, rc = run_kubectl(
        f"exec {pod_name} -- sh -c 'cat > /tmp/test_redis.py'",
        namespace
    )
    
    if rc != 0:
        return {"error": f"Failed to create test script: {stderr}"}
    
    # Executar teste
    stdout, stderr, rc = run_kubectl(
        f"exec {pod_name} -- python3 /tmp/test_redis.py",
        namespace
    )
    
    return {
        "output": stdout,
        "errors": stderr,
        "return_code": rc
    }


def check_otel_connectivity(namespace: str, pod_name: str, otel_endpoint: str) -> Dict[str, Any]:
    """Verifica conectividade com OTEL Collector."""
    # Derivar endpoint HTTP (porta 4318)
    http_endpoint = otel_endpoint.replace(":4317", ":4318")
    
    stdout, stderr, rc = run_kubectl(
        f"exec {pod_name} -- wget -qO- {http_endpoint}/health 2>&1 || echo 'HTTP_ERROR'",
        namespace
    )
    
    return {
        "endpoint": http_endpoint,
        "reachable": "HTTP_ERROR" not in stdout and rc == 0,
        "response": stdout[:200] if rc == 0 else stderr[:200],
        "suggestion": "Se falhar com HTTPS, tente HTTP"
    }


def print_header(text: str):
    """Imprime header formatado."""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}")


def print_success(text: str):
    """Imprime mensagem de sucesso."""
    print(f"{Colors.OKGREEN}✓ {text}{Colors.ENDC}")


def print_warning(text: str):
    """Imprime warning."""
    print(f"{Colors.WARNING}⚠ {text}{Colors.ENDC}")


def print_error(text: str):
    """Imprime erro."""
    print(f"{Colors.FAIL}✗ {text}{Colors.ENDC}")


def print_info(text: str):
    """Imprime info."""
    print(f"{Colors.OKBLUE}ℹ {text}{Colors.ENDC}")


def main():
    parser = argparse.ArgumentParser(
        description="Diagnóstico completo do Gateway Neural Hive-Mind"
    )
    parser.add_argument(
        "--namespace",
        default="gateway-intencoes",
        help="Namespace do gateway (default: gateway-intencoes)"
    )
    parser.add_argument(
        "--pod",
        help="Nome específico do pod (se não informado, encontra automaticamente)"
    )
    
    args = parser.parse_args()
    
    print_header("DIAGNÓSTICO GATEWAY NEURAL HIVE-MIND")
    
    # Encontrar pod
    if args.pod:
        pod_name = args.pod
        print_info(f"Usando pod especificado: {pod_name}")
    else:
        pod_name = find_gateway_pod(args.namespace)
        if not pod_name:
            print_error("Não foi possível encontrar o pod do gateway!")
            print_info("Verifique se o namespace está correto e se o pod está rodando")
            sys.exit(1)
        print_success(f"Pod encontrado: {pod_name}")
    
    # 1. Verificar status do pod
    print_header("1. STATUS DO POD")
    pod_status = check_pod_status(args.namespace, pod_name)
    
    if "error" in pod_status:
        print_error(f"Erro: {pod_status['error']}")
    else:
        print(f"  Fase: {pod_status['phase']}")
        print(f"  Ready: {'Sim' if pod_status['ready'] else 'Não'}")
        print(f"  Restarts: {pod_status['restart_count']}")
        
        if pod_status['restart_count'] > 5:
            print_warning(f"Pod tem {pod_status['restart_count']} restarts - possível problema de inicialização")
    
    # 2. Verificar variáveis de ambiente
    print_header("2. VARIÁVEIS DE AMBIENTE")
    env_check = check_environment_variables(args.namespace, pod_name)
    
    print_info("Variáveis encontradas:")
    for key, value in env_check["env_vars"].items():
        print(f"  {key}={value[:50]}{'...' if len(value) > 50 else ''}")
    
    if env_check["issues"]:
        print_error(f"\n{len(env_check['issues'])} problema(s) encontrado(s):")
        for issue in env_check["issues"]:
            severity_color = Colors.FAIL if issue["severity"] == "HIGH" else Colors.WARNING
            print(f"\n  {severity_color}[{issue['severity']}]{Colors.ENDC} {issue['message']}")
            print(f"  {Colors.OKCYAN}Solução:{Colors.ENDC} {issue['fix']}")
    else:
        print_success("Nenhum problema encontrado nas variáveis de ambiente")
    
    # 3. Verificar endpoint de health
    print_header("3. HEALTH CHECK")
    health = check_health_endpoint(args.namespace, pod_name)
    
    if health.get("error"):
        print_error(f"Erro ao chamar /health: {health['error']}")
    else:
        status = health.get("status", "unknown")
        if status == "healthy":
            print_success(f"Status: {status}")
        elif status == "degraded":
            print_warning(f"Status: {status}")
        else:
            print_error(f"Status: {status}")
        
        components = health.get("components", {})
        if components:
            print("\n  Componentes:")
            for name, info in components.items():
                comp_status = info.get("status", "unknown")
                if comp_status == "healthy":
                    print(f"    {Colors.OKGREEN}✓{Colors.ENDC} {name}: {comp_status}")
                elif comp_status == "degraded":
                    print(f"    {Colors.WARNING}⚠{Colors.ENDC} {name}: {comp_status}")
                else:
                    print(f"    {Colors.FAIL}✗{Colors.ENDC} {name}: {comp_status}")
                    if "message" in info:
                        print(f"      Mensagem: {info['message']}")
    
    # 4. Verificar Redis especificamente
    print_header("4. TESTE ESPECÍFICO - REDIS PING")
    print_info("Verificando se RedisClient.ping funciona corretamente...")
    redis_test = check_redis_ping(args.namespace, pod_name)
    
    if redis_test.get("error"):
        print_error(f"Erro no teste: {redis_test['error']}")
    else:
        print("Output do teste:")
        for line in redis_test.get("output", "").split("\n"):
            if line.strip():
                print(f"  {line}")
        
        if "ERROR" in redis_test.get("output", ""):
            print_error("Redis ping apresenta problemas!")
            print_info("Solução: Verificar se está passando função async diretamente (sem lambda)")
        else:
            print_success("Redis ping parece estar funcionando")
    
    # 5. Verificar OTEL
    print_header("5. TESTE ESPECÍFICO - OTEL CONNECTIVITY")
    otel_endpoint = env_check["env_vars"].get("OTEL_ENDPOINT", "")
    if otel_endpoint:
        print_info(f"Testando conectividade com: {otel_endpoint}")
        otel_test = check_otel_connectivity(args.namespace, pod_name, otel_endpoint)
        
        print(f"  Endpoint HTTP: {otel_test['endpoint']}")
        print(f"  Alcançável: {'Sim' if otel_test['reachable'] else 'Não'}")
        
        if not otel_test['reachable']:
            print_error("OTEL Collector não está acessível!")
            print_info("Possíveis causas:")
            print("  1. Endpoint configurado como HTTPS mas collector usa HTTP")
            print("  2. OTEL Collector não está rodando")
            print("  3. Problema de rede/service mesh")
            print("\nSolução: Verificar valores-staging.yaml e usar http://")
        else:
            print_success("OTEL Collector está acessível")
    else:
        print_warning("OTEL_ENDPOINT não configurado - OpenTelemetry desabilitado")
    
    # Resumo
    print_header("RESUMO")
    total_issues = len(env_check["issues"])
    
    if total_issues == 0 and health.get("status") == "healthy":
        print_success("Gateway parece estar saudável!")
    else:
        print_warning(f"{total_issues} problema(s) encontrado(s)")
        print_info("Ações recomendadas:")
        
        # Sugerir correções específicas
        if any("OTEL_ENDPOINT usa HTTPS" in i.get("message", "") for i in env_check["issues"]):
            print("  1. Editar helm-charts/gateway-intencoes/values-staging.yaml")
            print("  2. Mudar otelEndpoint de https:// para http://")
            print("  3. Re-deploy: helm upgrade gateway-intencoes helm-charts/gateway-intencoes -f values-staging.yaml")
        
        if any("REDIS_CLUSTER_NODES" in i.get("message", "") for i in env_check["issues"]):
            print("  • Verificar ConfigMap do gateway-intencoes")
            print("  • Verificar se Redis Cluster está acessível")
    
    print(f"\n{Colors.OKCYAN}Para mais informações, verifique os logs:{Colors.ENDC}")
    print(f"  kubectl logs -n {args.namespace} {pod_name} --tail=100")


if __name__ == "__main__":
    main()
