#!/usr/bin/env python3
"""
Script de teste de carga para Unified Gateway (:7999)
Valida requisitos de performance:
- Latência adicional <20ms p95
- Throughput >200 req/s
- Rate limiting functionality
"""

import asyncio
import aiohttp
import time
import json
import statistics
import argparse
import logging
from typing import List, Dict
from dataclasses import dataclass, asdict
import numpy as np

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class UnifiedGatewayLoadTestConfig:
    """Configurações do teste de carga do Unified Gateway"""

    gateway_url: str
    auth_token: str = "test-token"
    nhm_endpoint: str = "/api/v1/nhm/request"
    health_endpoint: str = "/health"
    metrics_endpoint: str = "/metrics"
    concurrent_requests: int = 50
    total_requests: int = 1000
    test_duration_seconds: int = 60
    ramp_up_seconds: int = 10
    request_timeout: int = 30

    # Requisitos de performance da spec
    target_throughput: int = 200  # req/s
    max_p95_latency_ms: float = 20.0  # latência adicional

    # Rate limiting test config
    test_rate_limit: bool = False
    rate_limit_tenant_id: str = "test_tenant"
    rate_limit_user_id: str = "test_user"
    expected_rate_limit: int = 1000


@dataclass
class RequestResult:
    """Resultado de uma requisição individual"""

    endpoint: str
    method: str
    status_code: int
    response_time_ms: float
    success: bool
    error_message: str = None
    response_size_bytes: int = 0
    flow_classification: str = None
    request_id: str = None


@dataclass
class UnifiedGatewayLoadTestResults:
    """Resultados consolidados do teste de carga"""

    config: UnifiedGatewayLoadTestConfig
    total_requests: int
    successful_requests: int
    failed_requests: int
    test_duration_seconds: float
    requests_per_second: float

    # Métricas de latência
    latency_stats: Dict[str, Dict[str, float]]

    # Classificação de fluxos
    flow_distribution: Dict[str, int]

    # Status codes
    status_code_distribution: Dict[int, int]

    # Erros
    error_distribution: Dict[str, int]

    # Taxa de sucesso
    success_rate: float

    # Avaliação vs requisitos
    meets_throughput_requirement: bool
    meets_latency_requirement: bool


class UnifiedGatewayLoadTester:
    """Executor de teste de carga para Unified Gateway"""

    # Amostras de intents para teste
    SAMPLE_INTENTS = [
        {"text": "Listar todos os usuários do sistema", "language": "pt-BR", "expected_flow": "G"},
        {
            "text": "Criar novo usuário com permissões de admin",
            "language": "pt-BR",
            "expected_flow": "G",
        },
        {
            "text": "Resetar senha do usuário joao@empresa.com",
            "language": "pt-BR",
            "expected_flow": "A",
        },
        {
            "text": "Relatório de vendas do último trimestre",
            "language": "pt-BR",
            "expected_flow": "F",
        },
        {"text": "Deploy da versão 2.0 para produção", "language": "pt-BR", "expected_flow": "H"},
        {
            "text": "Analisar dados de transações bancárias",
            "language": "pt-BR",
            "expected_flow": "F",
        },
        {"text": "Configurar autenticação two-factor", "language": "pt-BR", "expected_flow": "A"},
        {
            "text": "Gerar dashboard de métricas do sistema",
            "language": "pt-BR",
            "expected_flow": "F",
        },
    ]

    def __init__(self, config: UnifiedGatewayLoadTestConfig):
        self.config = config
        self.results: List[RequestResult] = []
        self.session: aiohttp.ClientSession = None

    async def setup_session(self):
        """Configurar sessão HTTP"""
        connector = aiohttp.TCPConnector(
            limit=self.config.concurrent_requests * 2,
            limit_per_host=self.config.concurrent_requests,
            keepalive_timeout=30,
            enable_cleanup_closed=True,
        )

        timeout = aiohttp.ClientTimeout(total=self.config.request_timeout)

        headers = {
            "Authorization": f"Bearer {self.config.auth_token}",
            "Content-Type": "application/json",
            "X-Tenant-ID": self.config.rate_limit_tenant_id,
            "X-User-ID": self.config.rate_limit_user_id,
            "User-Agent": "Unified-Gateway-Load-Test/1.0",
        }

        self.session = aiohttp.ClientSession(connector=connector, timeout=timeout, headers=headers)

    async def cleanup_session(self):
        """Fechar sessão HTTP"""
        if self.session:
            await self.session.close()

    async def send_nhm_request(self, request_id: int) -> RequestResult:
        """Enviar requisição POST /api/v1/nhm/request"""
        start_time = time.time()

        # Selecionar intent aleatório
        sample = self.SAMPLE_INTENTS[request_id % len(self.SAMPLE_INTENTS)]

        payload = {
            "text": sample["text"],
            "language": sample["language"],
            "correlation_id": f"load-test-{request_id}-{int(time.time() * 1000)}",
            "context": {
                "tenant_id": self.config.rate_limit_tenant_id,
                "user_id": self.config.rate_limit_user_id,
                "session_id": f"session-{request_id}",
            },
        }

        try:
            url = f"{self.config.gateway_url}{self.config.nhm_endpoint}"

            async with self.session.post(url, json=payload) as response:
                response_time = (time.time() - start_time) * 1000

                if response.status == 200:
                    content = await response.json()

                    return RequestResult(
                        endpoint=self.config.nhm_endpoint,
                        method="POST",
                        status_code=response.status,
                        response_time_ms=response_time,
                        success=True,
                        response_size_bytes=len(json.dumps(content).encode("utf-8")),
                        flow_classification=content.get("flow_classification"),
                        request_id=content.get("request_id"),
                    )
                else:
                    content_text = await response.text()

                    return RequestResult(
                        endpoint=self.config.nhm_endpoint,
                        method="POST",
                        status_code=response.status,
                        response_time_ms=response_time,
                        success=False,
                        response_size_bytes=len(content_text.encode("utf-8")),
                        error_message=f"HTTP {response.status}: {content_text[:200]}",
                    )

        except asyncio.TimeoutError:
            response_time = (time.time() - start_time) * 1000
            return RequestResult(
                endpoint=self.config.nhm_endpoint,
                method="POST",
                status_code=0,
                response_time_ms=response_time,
                success=False,
                error_message="Request timeout",
            )
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            return RequestResult(
                endpoint=self.config.nhm_endpoint,
                method="POST",
                status_code=0,
                response_time_ms=response_time,
                success=False,
                error_message=str(e),
            )

    async def send_health_request(self) -> RequestResult:
        """Enviar requisição de health check"""
        start_time = time.time()

        try:
            url = f"{self.config.gateway_url}{self.config.health_endpoint}"

            async with self.session.get(url) as response:
                response_time = (time.time() - start_time) * 1000
                content = await response.text()

                return RequestResult(
                    endpoint=self.config.health_endpoint,
                    method="GET",
                    status_code=response.status,
                    response_time_ms=response_time,
                    success=response.status == 200,
                    response_size_bytes=len(content.encode("utf-8")),
                    error_message=None if response.status == 200 else f"HTTP {response.status}",
                )

        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            return RequestResult(
                endpoint=self.config.health_endpoint,
                method="GET",
                status_code=0,
                response_time_ms=response_time,
                success=False,
                error_message=str(e),
            )

    async def run_concurrent_batch(self, batch_size: int, start_id: int) -> List[RequestResult]:
        """Executar lote de requisições concorrentes"""
        semaphore = asyncio.Semaphore(self.config.concurrent_requests)

        async def limited_request(req_id: int):
            async with semaphore:
                return await self.send_nhm_request(req_id)

        tasks = [limited_request(start_id + i) for i in range(batch_size)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filtrar exceptions
        valid_results = []
        for result in results:
            if isinstance(result, RequestResult):
                valid_results.append(result)
            else:
                logger.error(f"Request failed with exception: {result}")
                valid_results.append(
                    RequestResult(
                        endpoint=self.config.nhm_endpoint,
                        method="POST",
                        status_code=0,
                        response_time_ms=0,
                        success=False,
                        error_message=str(result),
                    )
                )

        return valid_results

    async def run_ramp_up_test(self) -> List[RequestResult]:
        """Executar teste com ramp-up gradual"""
        logger.info(f"Starting ramp-up test over {self.config.ramp_up_seconds} seconds")
        logger.info(f"Target: {self.config.total_requests} total requests")
        logger.info(f"Concurrent limit: {self.config.concurrent_requests}")

        all_results = []
        start_time = time.time()

        # Distribuir requests durante o período de ramp-up
        requests_per_second = self.config.total_requests / self.config.ramp_up_seconds

        for second in range(self.config.ramp_up_seconds):
            batch_start = time.time()

            # Calcular quantas requests para este segundo
            batch_size = min(
                int(requests_per_second), self.config.total_requests - len(all_results)
            )

            if batch_size <= 0:
                break

            # Executar lote
            current_id = len(all_results)
            batch_results = await self.run_concurrent_batch(batch_size, current_id)
            all_results.extend(batch_results)

            # Aguardar até completar 1 segundo
            elapsed = time.time() - batch_start
            if elapsed < 1.0:
                await asyncio.sleep(1.0 - elapsed)

            logger.info(
                f"Completed second {second + 1}/{self.config.ramp_up_seconds}, "
                f"batch: {batch_size} requests, total: {len(all_results)}"
            )

        total_time = time.time() - start_time
        actual_rps = len(all_results) / total_time if total_time > 0 else 0

        logger.info(f"Ramp-up test completed in {total_time:.2f} seconds")
        logger.info(f"Actual throughput: {actual_rps:.2f} req/s")

        return all_results

    async def test_rate_limiting(self) -> Dict:
        """
        Testar comportamento de rate limiting

        Envia requisições até exceder o limite e valida:
        - Status code 429
        - Headers de rate limit (X-RateLimit-*)
        """
        logger.info(f"Testing rate limiting for tenant {self.config.rate_limit_tenant_id}")
        logger.info(f"Expected limit: {self.config.expected_rate_limit} requests/minute")

        results = []
        rate_limit_hit = False
        rate_limit_headers = {}

        # Enviar requisições até atingir limite + margem
        max_requests = self.config.expected_rate_limit + 100

        for i in range(max_requests):
            result = await self.send_nhm_request(i)
            results.append(result)

            # Verificar se atingiu rate limit
            if result.status_code == 429:
                rate_limit_hit = True
                logger.info(f"Rate limit hit at request {i+1}")
                break

            # Log a cada 100 requisições
            if (i + 1) % 100 == 0:
                logger.info(f"Sent {i + 1} requests, last status: {result.status_code}")

        # Calcular métricas
        successful = [r for r in results if r.success]
        rate_limited = [r for r in results if r.status_code == 429]

        return {
            "rate_limit_hit": rate_limit_hit,
            "requests_before_limit": len(successful),
            "total_requests": len(results),
            "expected_limit": self.config.expected_rate_limit,
            "rate_limited_count": len(rate_limited),
            "within_expected_range": abs(len(successful) - self.config.expected_rate_limit) <= 50,
            "success": rate_limit_hit and len(successful) >= self.config.expected_rate_limit * 0.9,
        }

    def calculate_statistics(self, results: List[RequestResult]) -> UnifiedGatewayLoadTestResults:
        """Calcular estatísticas dos resultados"""
        if not results:
            return UnifiedGatewayLoadTestResults(
                config=self.config,
                total_requests=0,
                successful_requests=0,
                failed_requests=0,
                test_duration_seconds=0,
                requests_per_second=0,
                latency_stats={},
                flow_distribution={},
                status_code_distribution={},
                error_distribution={},
                success_rate=0,
                meets_throughput_requirement=False,
                meets_latency_requirement=False,
            )

        # Métricas básicas
        total_requests = len(results)
        successful_requests = sum(1 for r in results if r.success)
        failed_requests = total_requests - successful_requests

        # Calcular duração do teste
        test_duration = self.config.ramp_up_seconds
        requests_per_second = total_requests / test_duration if test_duration > 0 else 0
        success_rate = successful_requests / total_requests if total_requests > 0 else 0

        # Estatísticas de latência
        latency_stats = {}
        successful_results = [r for r in results if r.success]

        if successful_results:
            response_times = [r.response_time_ms for r in successful_results]

            latency_stats["overall"] = {
                "count": len(response_times),
                "mean": statistics.mean(response_times),
                "median": statistics.median(response_times),
                "p50": np.percentile(response_times, 50),
                "p90": np.percentile(response_times, 90),
                "p95": np.percentile(response_times, 95),
                "p99": np.percentile(response_times, 99),
                "min": min(response_times),
                "max": max(response_times),
                "stddev": statistics.stdev(response_times) if len(response_times) > 1 else 0,
            }

        # Distribuição de fluxos
        flow_distribution = {}
        for result in successful_results:
            if result.flow_classification:
                flow_distribution[result.flow_classification] = (
                    flow_distribution.get(result.flow_classification, 0) + 1
                )

        # Distribuição de status codes
        status_code_distribution = {}
        for result in results:
            status_code_distribution[result.status_code] = (
                status_code_distribution.get(result.status_code, 0) + 1
            )

        # Distribuição de erros
        error_distribution = {}
        for result in results:
            if not result.success and result.error_message:
                error_type = result.error_message.split(":")[0]
                error_distribution[error_type] = error_distribution.get(error_type, 0) + 1

        # Avaliação vs requisitos da spec
        meets_throughput = requests_per_second >= self.config.target_throughput
        p95_latency = latency_stats.get("overall", {}).get("p95", float("inf"))
        meets_latency = p95_latency <= self.config.max_p95_latency_ms

        return UnifiedGatewayLoadTestResults(
            config=self.config,
            total_requests=total_requests,
            successful_requests=successful_requests,
            failed_requests=failed_requests,
            test_duration_seconds=test_duration,
            requests_per_second=requests_per_second,
            latency_stats=latency_stats,
            flow_distribution=flow_distribution,
            status_code_distribution=status_code_distribution,
            error_distribution=error_distribution,
            success_rate=success_rate,
            meets_throughput_requirement=meets_throughput,
            meets_latency_requirement=meets_latency,
        )

    async def run_test(self) -> UnifiedGatewayLoadTestResults:
        """Executar teste de carga completo"""
        logger.info("=" * 60)
        logger.info("  UNIFIED GATEWAY LOAD TEST")
        logger.info("=" * 60)
        logger.info(f"Target URL: {self.config.gateway_url}")
        logger.info(f"Total requests: {self.config.total_requests}")
        logger.info(f"Concurrent requests: {self.config.concurrent_requests}")
        logger.info(f"Ramp-up duration: {self.config.ramp_up_seconds}s")
        logger.info(f"Target throughput: {self.config.target_throughput} req/s")
        logger.info(f"Max P95 latency: {self.config.max_p95_latency_ms}ms")
        logger.info("=" * 60)

        await self.setup_session()

        try:
            # Verificar health primeiro
            health_result = await self.send_health_request()
            if not health_result.success:
                logger.warning(f"Gateway health check failed: {health_result.error_message}")

            # Executar teste principal
            results = await self.run_ramp_up_test()

            # Calcular estatísticas
            return self.calculate_statistics(results)

        finally:
            await self.cleanup_session()


def print_results(results: UnifiedGatewayLoadTestResults):
    """Imprimir resultados formatados"""
    print("\n" + "=" * 60)
    print("       UNIFIED GATEWAY LOAD TEST RESULTS")
    print("=" * 60)

    print(f"\nTarget URL: {results.config.gateway_url}")
    print(f"Test Duration: {results.test_duration_seconds:.2f}s")
    print(f"Total Requests: {results.total_requests}")
    print(f"Successful Requests: {results.successful_requests}")
    print(f"Failed Requests: {results.failed_requests}")
    print(f"Success Rate: {results.success_rate:.2%}")
    print(f"Requests/Second: {results.requests_per_second:.2f}")

    # Requisitos da spec
    print("\n--- SPEC REQUIREMENTS VALIDATION ---")
    throughput_status = "✅ PASS" if results.meets_throughput_requirement else "❌ FAIL"
    print(
        f"  Throughput >{results.config.target_throughput} req/s: {throughput_status} ({results.requests_per_second:.2f} req/s)"
    )

    p95_latency = results.latency_stats.get("overall", {}).get("p95", "N/A")
    latency_status = "✅ PASS" if results.meets_latency_requirement else "❌ FAIL"
    print(
        f"  P95 Latency <{results.config.max_p95_latency_ms}ms: {latency_status} ({p95_latency} ms)"
    )

    print("\n--- LATENCY STATISTICS ---")
    if results.latency_stats.get("overall"):
        stats = results.latency_stats["overall"]
        print(f"  Requests: {stats['count']}")
        print(f"  Mean: {stats['mean']:.2f}ms")
        print(f"  Median: {stats['median']:.2f}ms")
        print(f"  P50: {stats['p50']:.2f}ms")
        print(f"  P90: {stats['p90']:.2f}ms")
        print(f"  P95: {stats['p95']:.2f}ms")
        print(f"  P99: {stats['p99']:.2f}ms")
        print(f"  Min: {stats['min']:.2f}ms")
        print(f"  Max: {stats['max']:.2f}ms")
        print(f"  StdDev: {stats['stddev']:.2f}ms")

    print("\n--- FLOW CLASSIFICATION DISTRIBUTION ---")
    if results.flow_distribution:
        for flow, count in sorted(results.flow_distribution.items()):
            percentage = (count / results.successful_requests) * 100
            print(f"  Flow {flow}: {count} ({percentage:.1f}%)")
    else:
        print("  No flow classification data available")

    print("\n--- STATUS CODE DISTRIBUTION ---")
    for status_code, count in sorted(results.status_code_distribution.items()):
        percentage = (count / results.total_requests) * 100
        print(f"  {status_code}: {count} ({percentage:.1f}%)")

    if results.error_distribution:
        print("\n--- ERROR DISTRIBUTION ---")
        for error_type, count in sorted(
            results.error_distribution.items(), key=lambda x: x[1], reverse=True
        ):
            percentage = (
                (count / results.failed_requests) * 100 if results.failed_requests > 0 else 0
            )
            print(f"  {error_type}: {count} ({percentage:.1f}%)")

    # Avaliação de performance
    print("\n--- PERFORMANCE ASSESSMENT ---")

    all_requirements_met = (
        results.meets_throughput_requirement and results.meets_latency_requirement
    )

    if all_requirements_met and results.success_rate >= 0.99:
        print("🟢 EXCELLENT: All requirements met, high success rate")
    elif results.success_rate >= 0.95:
        print("🟡 GOOD: Acceptable performance")
    elif results.success_rate >= 0.90:
        print("🟠 WARNING: Performance issues detected")
    else:
        print("🔴 CRITICAL: Significant performance problems")

    print("=" * 60)


async def main():
    parser = argparse.ArgumentParser(description="Unified Gateway Load Test")
    parser.add_argument("--url", required=True, help="Gateway URL (e.g., http://localhost:7999)")
    parser.add_argument("--token", default="test-token", help="Authentication token")
    parser.add_argument("--requests", type=int, default=1000, help="Total number of requests")
    parser.add_argument("--concurrent", type=int, default=50, help="Concurrent requests")
    parser.add_argument("--ramp-up", type=int, default=60, help="Ramp-up duration in seconds")
    parser.add_argument("--timeout", type=int, default=30, help="Request timeout in seconds")
    parser.add_argument("--output", help="Output file for JSON results")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    parser.add_argument(
        "--target-throughput", type=int, default=200, help="Target throughput (req/s)"
    )
    parser.add_argument("--max-p95-latency", type=float, default=20.0, help="Max P95 latency (ms)")
    # Rate limiting test arguments
    parser.add_argument(
        "--test-rate-limit", action="store_true", help="Test rate limiting behavior"
    )
    parser.add_argument("--tenant-id", default="test_tenant", help="Tenant ID for testing")
    parser.add_argument("--user-id", default="test_user", help="User ID for testing")
    parser.add_argument("--expected-rate-limit", type=int, default=1000, help="Expected rate limit")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    config = UnifiedGatewayLoadTestConfig(
        gateway_url=args.url.rstrip("/"),
        auth_token=args.token,
        total_requests=args.requests,
        concurrent_requests=args.concurrent,
        ramp_up_seconds=args.ramp_up,
        request_timeout=args.timeout,
        target_throughput=args.target_throughput,
        max_p95_latency_ms=args.max_p95_latency,
        test_rate_limit=args.test_rate_limit,
        rate_limit_tenant_id=args.tenant_id,
        rate_limit_user_id=args.user_id,
        expected_rate_limit=args.expected_rate_limit,
    )

    tester = UnifiedGatewayLoadTester(config)

    # Rate limiting test mode
    if args.test_rate_limit:
        await tester.setup_session()
        try:
            rate_limit_results = await tester.test_rate_limiting()

            print("\n" + "=" * 60)
            print("         RATE LIMITING TEST RESULTS")
            print("=" * 60)
            print(f"Rate limit hit: {rate_limit_results['rate_limit_hit']}")
            print(f"Requests before limit: {rate_limit_results['requests_before_limit']}")
            print(f"Expected limit: {rate_limit_results['expected_limit']}")
            print(f"Total requests sent: {rate_limit_results['total_requests']}")
            print(f"Within expected range: {rate_limit_results['within_expected_range']}")

            if rate_limit_results["success"]:
                print("\n🟢 Rate limiting test PASSED")
                exit(0)
            else:
                print("\n🔴 Rate limiting test FAILED")
                exit(1)
        finally:
            await tester.cleanup_session()
    else:
        # Normal load test
        results = await tester.run_test()

        # Print results
        print_results(results)

        # Save to file if requested
        if args.output:
            with open(args.output, "w") as f:
                json.dump(asdict(results), f, indent=2, default=str)
            print(f"\nResults saved to {args.output}")

        # Exit with error code if test failed
        if not (results.meets_throughput_requirement and results.meets_latency_requirement):
            exit(1)
        elif results.success_rate < 0.95:
            exit(1)
        else:
            exit(0)


if __name__ == "__main__":
    asyncio.run(main())
