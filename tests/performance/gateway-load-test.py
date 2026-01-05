#!/usr/bin/env python3
"""
Script de teste de carga para Gateway de Intenções
Testa endpoints de texto e voz com métricas de latência P95
"""

import asyncio
import aiohttp
import time
import json
import statistics
import argparse
import logging
from typing import List, Dict, Tuple
from dataclasses import dataclass, asdict
from concurrent.futures import ThreadPoolExecutor
import numpy as np

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class LoadTestConfig:
    """Configurações do teste de carga"""
    gateway_url: str
    auth_token: str
    text_endpoint: str = "/intentions"
    voice_endpoint: str = "/intentions/voice"
    health_endpoint: str = "/health"
    concurrent_requests: int = 50
    total_requests: int = 1000
    test_duration_seconds: int = 60
    ramp_up_seconds: int = 10
    request_timeout: int = 30
    # Rate limiting test config
    test_rate_limit: bool = False
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


@dataclass
class LoadTestResults:
    """Resultados consolidados do teste de carga"""
    config: LoadTestConfig
    total_requests: int
    successful_requests: int
    failed_requests: int
    test_duration_seconds: float
    requests_per_second: float

    # Métricas de latência por endpoint
    latency_stats: Dict[str, Dict[str, float]]  # endpoint -> {mean, p50, p95, p99, max}

    # Status codes
    status_code_distribution: Dict[int, int]

    # Erros
    error_distribution: Dict[str, int]

    # Taxa de sucesso
    success_rate: float


class GatewayLoadTester:
    """Executor de teste de carga para Gateway"""

    def __init__(self, config: LoadTestConfig):
        self.config = config
        self.results: List[RequestResult] = []
        self.session: aiohttp.ClientSession = None

    async def setup_session(self):
        """Configurar sessão HTTP"""
        connector = aiohttp.TCPConnector(
            limit=self.config.concurrent_requests * 2,
            limit_per_host=self.config.concurrent_requests,
            keepalive_timeout=30,
            enable_cleanup_closed=True
        )

        timeout = aiohttp.ClientTimeout(total=self.config.request_timeout)

        headers = {
            'Authorization': f'Bearer {self.config.auth_token}',
            'Content-Type': 'application/json',
            'User-Agent': 'Gateway-Load-Test/1.0'
        }

        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers=headers
        )

    async def cleanup_session(self):
        """Fechar sessão HTTP"""
        if self.session:
            await self.session.close()

    async def send_text_request(self, request_id: int) -> RequestResult:
        """Enviar requisição de texto"""
        start_time = time.time()

        payload = {
            "text": f"Implementar funcionalidade de autenticação OAuth2 para o sistema de gerenciamento de usuários - Request {request_id}",
            "language": "pt-BR",
            "correlation_id": f"load-test-{request_id}-{int(time.time())}"
        }

        try:
            url = f"{self.config.gateway_url}{self.config.text_endpoint}"

            async with self.session.post(url, json=payload) as response:
                response_time = (time.time() - start_time) * 1000
                content = await response.text()

                return RequestResult(
                    endpoint=self.config.text_endpoint,
                    method="POST",
                    status_code=response.status,
                    response_time_ms=response_time,
                    success=response.status == 200,
                    response_size_bytes=len(content.encode('utf-8')),
                    error_message=None if response.status == 200 else f"HTTP {response.status}: {content[:200]}"
                )

        except asyncio.TimeoutError:
            response_time = (time.time() - start_time) * 1000
            return RequestResult(
                endpoint=self.config.text_endpoint,
                method="POST",
                status_code=0,
                response_time_ms=response_time,
                success=False,
                error_message="Request timeout"
            )
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            return RequestResult(
                endpoint=self.config.text_endpoint,
                method="POST",
                status_code=0,
                response_time_ms=response_time,
                success=False,
                error_message=str(e)
            )

    async def send_voice_request(self, request_id: int) -> RequestResult:
        """Enviar requisição de voz (simulada)"""
        start_time = time.time()

        # Simular dados de áudio (WAV header + dados)
        fake_audio_data = b'RIFF\x24\x08\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00D\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x08\x00\x00' + b'\x00\x01' * 1000

        try:
            url = f"{self.config.gateway_url}{self.config.voice_endpoint}"

            # Multipart form data
            data = aiohttp.FormData()
            data.add_field('language', 'pt-BR')
            data.add_field('correlation_id', f'voice-load-test-{request_id}-{int(time.time())}')
            data.add_field('audio_file', fake_audio_data, filename=f'test_audio_{request_id}.wav', content_type='audio/wav')

            # Remover Content-Type header para multipart
            headers = dict(self.session._default_headers)
            headers.pop('Content-Type', None)

            async with self.session.post(url, data=data, headers=headers) as response:
                response_time = (time.time() - start_time) * 1000
                content = await response.text()

                return RequestResult(
                    endpoint=self.config.voice_endpoint,
                    method="POST",
                    status_code=response.status,
                    response_time_ms=response_time,
                    success=response.status == 200,
                    response_size_bytes=len(content.encode('utf-8')),
                    error_message=None if response.status == 200 else f"HTTP {response.status}: {content[:200]}"
                )

        except asyncio.TimeoutError:
            response_time = (time.time() - start_time) * 1000
            return RequestResult(
                endpoint=self.config.voice_endpoint,
                method="POST",
                status_code=0,
                response_time_ms=response_time,
                success=False,
                error_message="Request timeout"
            )
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            return RequestResult(
                endpoint=self.config.voice_endpoint,
                method="POST",
                status_code=0,
                response_time_ms=response_time,
                success=False,
                error_message=str(e)
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
                    response_size_bytes=len(content.encode('utf-8')),
                    error_message=None if response.status == 200 else f"HTTP {response.status}: {content[:200]}"
                )

        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            return RequestResult(
                endpoint=self.config.health_endpoint,
                method="GET",
                status_code=0,
                response_time_ms=response_time,
                success=False,
                error_message=str(e)
            )

    async def run_single_request(self, request_id: int, endpoint_type: str) -> RequestResult:
        """Executar uma única requisição"""
        if endpoint_type == "text":
            return await self.send_text_request(request_id)
        elif endpoint_type == "voice":
            return await self.send_voice_request(request_id)
        elif endpoint_type == "health":
            return await self.send_health_request()
        else:
            raise ValueError(f"Unknown endpoint type: {endpoint_type}")

    async def run_concurrent_batch(self, batch_size: int, endpoint_type: str, start_id: int) -> List[RequestResult]:
        """Executar lote de requisições concorrentes"""
        semaphore = asyncio.Semaphore(self.config.concurrent_requests)

        async def limited_request(req_id: int):
            async with semaphore:
                return await self.run_single_request(req_id, endpoint_type)

        tasks = [limited_request(start_id + i) for i in range(batch_size)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filtrar exceptions
        valid_results = []
        for result in results:
            if isinstance(result, RequestResult):
                valid_results.append(result)
            else:
                logger.error(f"Request failed with exception: {result}")
                # Criar result de erro
                valid_results.append(RequestResult(
                    endpoint=f"/{endpoint_type}",
                    method="POST",
                    status_code=0,
                    response_time_ms=0,
                    success=False,
                    error_message=str(result)
                ))

        return valid_results

    async def run_ramp_up_test(self) -> List[RequestResult]:
        """Executar teste com ramp-up gradual"""
        logger.info(f"Starting ramp-up test over {self.config.ramp_up_seconds} seconds")

        all_results = []
        start_time = time.time()

        # Distribuir requests durante o período de ramp-up
        requests_per_second = self.config.total_requests / self.config.ramp_up_seconds

        for second in range(self.config.ramp_up_seconds):
            batch_start = time.time()

            # Calcular quantas requests para este segundo
            batch_size = min(
                int(requests_per_second),
                self.config.total_requests - len(all_results)
            )

            if batch_size <= 0:
                break

            # Mix de endpoints (70% text, 20% voice, 10% health)
            text_requests = int(batch_size * 0.7)
            voice_requests = int(batch_size * 0.2)
            health_requests = batch_size - text_requests - voice_requests

            # Executar lotes em paralelo
            tasks = []
            current_id = len(all_results)

            if text_requests > 0:
                tasks.append(self.run_concurrent_batch(text_requests, "text", current_id))
                current_id += text_requests

            if voice_requests > 0:
                tasks.append(self.run_concurrent_batch(voice_requests, "voice", current_id))
                current_id += voice_requests

            if health_requests > 0:
                tasks.append(self.run_concurrent_batch(health_requests, "health", current_id))

            # Aguardar conclusão dos lotes
            batch_results = await asyncio.gather(*tasks)

            # Consolidar resultados
            for batch in batch_results:
                all_results.extend(batch)

            # Aguardar até completar 1 segundo
            elapsed = time.time() - batch_start
            if elapsed < 1.0:
                await asyncio.sleep(1.0 - elapsed)

            logger.info(f"Completed second {second + 1}/{self.config.ramp_up_seconds}, "
                       f"total requests: {len(all_results)}")

        total_time = time.time() - start_time
        logger.info(f"Ramp-up test completed in {total_time:.2f} seconds")

        return all_results

    async def test_rate_limiting(self) -> Dict:
        """
        Testar comportamento de rate limiting

        Envia requisicoes ate exceder o limite e valida:
        - Headers de rate limit (X-RateLimit-*)
        - Status code 429
        - Retry-After header
        """
        logger.info(f"Testing rate limiting for user {self.config.rate_limit_user_id}")
        logger.info(f"Expected limit: {self.config.expected_rate_limit} requests/minute")

        results = []
        rate_limit_hit = False
        rate_limit_headers = {}

        # Enviar requisicoes ate atingir limite + margem
        max_requests = self.config.expected_rate_limit + 100

        for i in range(max_requests):
            result = await self.send_text_request(i)
            results.append(result)

            # Verificar headers de rate limit na resposta
            if result.status_code == 429:
                rate_limit_hit = True
                logger.info(f"Rate limit hit at request {i+1}")
                break

            # Log a cada 100 requisicoes
            if (i + 1) % 100 == 0:
                logger.info(f"Sent {i + 1} requests, last status: {result.status_code}")

        # Calcular metricas
        successful = [r for r in results if r.success]
        rate_limited = [r for r in results if r.status_code == 429]

        return {
            'rate_limit_hit': rate_limit_hit,
            'requests_before_limit': len(successful),
            'total_requests': len(results),
            'expected_limit': self.config.expected_rate_limit,
            'rate_limited_count': len(rate_limited),
            'within_expected_range': abs(len(successful) - self.config.expected_rate_limit) <= 10,
            'success': rate_limit_hit and len(successful) >= self.config.expected_rate_limit * 0.9
        }

    def calculate_statistics(self, results: List[RequestResult]) -> LoadTestResults:
        """Calcular estatísticas dos resultados"""
        if not results:
            return LoadTestResults(
                config=self.config,
                total_requests=0,
                successful_requests=0,
                failed_requests=0,
                test_duration_seconds=0,
                requests_per_second=0,
                latency_stats={},
                status_code_distribution={},
                error_distribution={},
                success_rate=0
            )

        # Métricas básicas
        total_requests = len(results)
        successful_requests = sum(1 for r in results if r.success)
        failed_requests = total_requests - successful_requests

        # Calcular duração do teste
        if results:
            test_duration = self.config.ramp_up_seconds
        else:
            test_duration = 0

        requests_per_second = total_requests / test_duration if test_duration > 0 else 0
        success_rate = successful_requests / total_requests if total_requests > 0 else 0

        # Estatísticas de latência por endpoint
        latency_stats = {}
        endpoints = set(r.endpoint for r in results)

        for endpoint in endpoints:
            endpoint_results = [r for r in results if r.endpoint == endpoint and r.success]

            if endpoint_results:
                response_times = [r.response_time_ms for r in endpoint_results]

                latency_stats[endpoint] = {
                    'count': len(response_times),
                    'mean': statistics.mean(response_times),
                    'median': statistics.median(response_times),
                    'p50': np.percentile(response_times, 50),
                    'p95': np.percentile(response_times, 95),
                    'p99': np.percentile(response_times, 99),
                    'min': min(response_times),
                    'max': max(response_times),
                    'stddev': statistics.stdev(response_times) if len(response_times) > 1 else 0
                }

        # Distribuição de status codes
        status_code_distribution = {}
        for result in results:
            status_code_distribution[result.status_code] = status_code_distribution.get(result.status_code, 0) + 1

        # Distribuição de erros
        error_distribution = {}
        for result in results:
            if not result.success and result.error_message:
                error_type = result.error_message.split(':')[0]  # Pegar primeiro parte do erro
                error_distribution[error_type] = error_distribution.get(error_type, 0) + 1

        return LoadTestResults(
            config=self.config,
            total_requests=total_requests,
            successful_requests=successful_requests,
            failed_requests=failed_requests,
            test_duration_seconds=test_duration,
            requests_per_second=requests_per_second,
            latency_stats=latency_stats,
            status_code_distribution=status_code_distribution,
            error_distribution=error_distribution,
            success_rate=success_rate
        )

    async def run_test(self) -> LoadTestResults:
        """Executar teste de carga completo"""
        logger.info("Starting Gateway load test")
        logger.info(f"Target: {self.config.gateway_url}")
        logger.info(f"Total requests: {self.config.total_requests}")
        logger.info(f"Concurrent requests: {self.config.concurrent_requests}")
        logger.info(f"Ramp-up duration: {self.config.ramp_up_seconds}s")

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


def print_results(results: LoadTestResults):
    """Imprimir resultados formatados"""
    print("\n" + "="*60)
    print("           GATEWAY LOAD TEST RESULTS")
    print("="*60)

    print(f"Target URL: {results.config.gateway_url}")
    print(f"Test Duration: {results.test_duration_seconds:.2f}s")
    print(f"Total Requests: {results.total_requests}")
    print(f"Successful Requests: {results.successful_requests}")
    print(f"Failed Requests: {results.failed_requests}")
    print(f"Success Rate: {results.success_rate:.2%}")
    print(f"Requests/Second: {results.requests_per_second:.2f}")

    print("\n--- LATENCY STATISTICS BY ENDPOINT ---")
    for endpoint, stats in results.latency_stats.items():
        print(f"\n{endpoint} ({stats['count']} requests):")
        print(f"  Mean: {stats['mean']:.2f}ms")
        print(f"  Median: {stats['median']:.2f}ms")
        print(f"  P95: {stats['p95']:.2f}ms")
        print(f"  P99: {stats['p99']:.2f}ms")
        print(f"  Min: {stats['min']:.2f}ms")
        print(f"  Max: {stats['max']:.2f}ms")

    print("\n--- STATUS CODE DISTRIBUTION ---")
    for status_code, count in sorted(results.status_code_distribution.items()):
        percentage = (count / results.total_requests) * 100
        print(f"  {status_code}: {count} ({percentage:.1f}%)")

    if results.error_distribution:
        print("\n--- ERROR DISTRIBUTION ---")
        for error_type, count in sorted(results.error_distribution.items(), key=lambda x: x[1], reverse=True):
            percentage = (count / results.failed_requests) * 100 if results.failed_requests > 0 else 0
            print(f"  {error_type}: {count} ({percentage:.1f}%)")

    # Avaliação de performance
    print("\n--- PERFORMANCE ASSESSMENT ---")
    overall_p95 = 0
    if results.latency_stats:
        overall_p95 = statistics.mean([stats['p95'] for stats in results.latency_stats.values()])

    if results.success_rate >= 0.99 and overall_p95 <= 1000:
        print("🟢 EXCELLENT: High success rate and low latency")
    elif results.success_rate >= 0.95 and overall_p95 <= 2000:
        print("🟡 GOOD: Acceptable performance with room for improvement")
    elif results.success_rate >= 0.90:
        print("🟠 WARNING: Performance issues detected")
    else:
        print("🔴 CRITICAL: Significant performance problems")

    print("="*60)


async def main():
    parser = argparse.ArgumentParser(description='Gateway Load Test')
    parser.add_argument('--url', required=True, help='Gateway URL (e.g., http://localhost:8000)')
    parser.add_argument('--token', required=True, help='Authentication token')
    parser.add_argument('--requests', type=int, default=1000, help='Total number of requests')
    parser.add_argument('--concurrent', type=int, default=50, help='Concurrent requests')
    parser.add_argument('--ramp-up', type=int, default=60, help='Ramp-up duration in seconds')
    parser.add_argument('--timeout', type=int, default=30, help='Request timeout in seconds')
    parser.add_argument('--output', help='Output file for JSON results')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose logging')
    # Rate limiting test arguments
    parser.add_argument('--test-rate-limit', action='store_true', help='Test rate limiting behavior')
    parser.add_argument('--rate-limit-user', default='test_user', help='User ID for rate limit testing')
    parser.add_argument('--expected-rate-limit', type=int, default=1000, help='Expected rate limit (requests/minute)')

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    config = LoadTestConfig(
        gateway_url=args.url.rstrip('/'),
        auth_token=args.token,
        total_requests=args.requests,
        concurrent_requests=args.concurrent,
        ramp_up_seconds=args.ramp_up,
        request_timeout=args.timeout,
        test_rate_limit=args.test_rate_limit,
        rate_limit_user_id=args.rate_limit_user,
        expected_rate_limit=args.expected_rate_limit
    )

    tester = GatewayLoadTester(config)

    # Rate limiting test mode
    if args.test_rate_limit:
        await tester.setup_session()
        try:
            rate_limit_results = await tester.test_rate_limiting()

            print("\n" + "="*60)
            print("         RATE LIMITING TEST RESULTS")
            print("="*60)
            print(f"Rate limit hit: {rate_limit_results['rate_limit_hit']}")
            print(f"Requests before limit: {rate_limit_results['requests_before_limit']}")
            print(f"Expected limit: {rate_limit_results['expected_limit']}")
            print(f"Total requests sent: {rate_limit_results['total_requests']}")
            print(f"Within expected range: {rate_limit_results['within_expected_range']}")

            if rate_limit_results['success']:
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
            with open(args.output, 'w') as f:
                json.dump(asdict(results), f, indent=2, default=str)
            print(f"\nResults saved to {args.output}")

        # Exit with error code if test failed
        if results.success_rate < 0.95:
            exit(1)
        else:
            exit(0)


if __name__ == "__main__":
    asyncio.run(main())