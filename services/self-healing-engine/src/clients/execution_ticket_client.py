"""
Execution Ticket Service client for Self-Healing Engine.

Provides ticket reallocation and status update capabilities
for automated remediation workflows.
"""

import asyncio
from datetime import datetime
from typing import Dict, List, Any, Optional
from uuid import uuid4

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from prometheus_client import Counter, Histogram
from neural_hive_observability import get_tracer

logger = structlog.get_logger(__name__)
tracer = get_tracer()

# Prometheus Metrics
TICKET_REALLOCATION_TOTAL = Counter(
    'self_healing_ticket_reallocation_total',
    'Total ticket reallocations by self-healing engine',
    ['status', 'reason']
)

TICKET_REALLOCATION_DURATION = Histogram(
    'self_healing_ticket_reallocation_duration_seconds',
    'Duration of ticket reallocation operations',
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

TICKET_STATUS_UPDATE_TOTAL = Counter(
    'self_healing_ticket_status_update_total',
    'Total ticket status updates by self-healing engine',
    ['status', 'new_status']
)


class CircuitBreakerOpen(Exception):
    """Circuit breaker is open, refusing requests."""
    pass


class SelfHealingTicketClient:
    """
    Extended Execution Ticket Client for Self-Healing Engine operations.

    Provides ticket reallocation and batch operations with:
    - Retry with exponential backoff
    - Circuit breaker pattern
    - Prometheus metrics
    - OpenTelemetry tracing
    """

    def __init__(
        self,
        base_url: str = 'http://execution-ticket-service.neural-hive-orchestration:8000',
        timeout: int = 30,
        circuit_breaker_threshold: int = 5,
        circuit_breaker_reset_seconds: int = 60,
    ):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.client: Optional[httpx.AsyncClient] = None

        # Circuit breaker state
        self._circuit_breaker_threshold = circuit_breaker_threshold
        self._circuit_breaker_reset_seconds = circuit_breaker_reset_seconds
        self._failure_count = 0
        self._circuit_open = False
        self._circuit_opened_at: Optional[datetime] = None

        logger.info(
            'self_healing_ticket_client.initialized',
            base_url=base_url,
            timeout=timeout,
            circuit_breaker_threshold=circuit_breaker_threshold
        )

    async def initialize(self):
        """Initialize HTTP client with connection pooling."""
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20)
        )
        logger.info('self_healing_ticket_client.http_client_initialized')

    async def close(self):
        """Close HTTP client gracefully."""
        if self.client:
            await self.client.aclose()
            self.client = None
            logger.info('self_healing_ticket_client.closed')

    def _check_circuit_breaker(self):
        """Check if circuit breaker allows request."""
        if not self._circuit_open:
            return

        # Check if reset timeout has passed
        if self._circuit_opened_at:
            elapsed = (datetime.now() - self._circuit_opened_at).total_seconds()
            if elapsed >= self._circuit_breaker_reset_seconds:
                # Half-open: allow one request
                logger.info(
                    'self_healing_ticket_client.circuit_breaker_half_open',
                    elapsed_seconds=elapsed
                )
                self._circuit_open = False
                self._failure_count = 0
                return

        raise CircuitBreakerOpen(
            f'Circuit breaker open after {self._failure_count} failures'
        )

    def _record_success(self):
        """Record successful request."""
        self._failure_count = 0
        if self._circuit_open:
            self._circuit_open = False
            self._circuit_opened_at = None
            logger.info('self_healing_ticket_client.circuit_breaker_closed')

    def _record_failure(self):
        """Record failed request and potentially open circuit breaker."""
        self._failure_count += 1
        if self._failure_count >= self._circuit_breaker_threshold:
            self._circuit_open = True
            self._circuit_opened_at = datetime.now()
            logger.warning(
                'self_healing_ticket_client.circuit_breaker_opened',
                failure_count=self._failure_count
            )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.HTTPError, asyncio.TimeoutError))
    )
    async def _make_request(
        self,
        method: str,
        path: str,
        json: Optional[Dict] = None,
        params: Optional[Dict] = None
    ) -> httpx.Response:
        """Make HTTP request with retry and circuit breaker."""
        self._check_circuit_breaker()

        if not self.client:
            raise RuntimeError('Client not initialized. Call initialize() first.')

        try:
            response = await self.client.request(
                method=method,
                url=path,
                json=json,
                params=params
            )
            response.raise_for_status()
            self._record_success()
            return response
        except (httpx.HTTPError, asyncio.TimeoutError) as e:
            self._record_failure()
            raise

    async def get_ticket(self, ticket_id: str) -> Dict[str, Any]:
        """
        Get ticket by ID.

        Args:
            ticket_id: Ticket identifier

        Returns:
            Ticket data dictionary
        """
        with tracer.start_as_current_span('self_healing.get_ticket') as span:
            span.set_attribute('ticket.id', ticket_id)

            response = await self._make_request('GET', f'/api/v1/tickets/{ticket_id}')
            return response.json()

    async def update_ticket_status(
        self,
        ticket_id: str,
        status: str,
        result: Optional[Dict[str, Any]] = None,
        assigned_worker: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Update ticket status.

        Args:
            ticket_id: Ticket identifier
            status: New status (pending, in_progress, completed, failed)
            result: Execution result (optional)
            assigned_worker: Worker ID (optional, use None to unassign)
            metadata: Additional metadata (optional)

        Returns:
            Updated ticket data
        """
        with tracer.start_as_current_span('self_healing.update_ticket_status') as span:
            span.set_attribute('ticket.id', ticket_id)
            span.set_attribute('ticket.status', status)

            payload: Dict[str, Any] = {'status': status}
            if result is not None:
                payload['result'] = result
            if assigned_worker is not None:
                payload['assigned_worker'] = assigned_worker
            if metadata:
                payload['metadata'] = metadata

            logger.info(
                'self_healing_ticket_client.updating_status',
                ticket_id=ticket_id,
                status=status
            )

            start_time = datetime.now()
            try:
                response = await self._make_request(
                    'PATCH',
                    f'/api/v1/tickets/{ticket_id}',
                    json=payload
                )

                TICKET_STATUS_UPDATE_TOTAL.labels(
                    status='success',
                    new_status=status
                ).inc()

                logger.info(
                    'self_healing_ticket_client.status_updated',
                    ticket_id=ticket_id,
                    status=status
                )

                return response.json()

            except Exception as e:
                TICKET_STATUS_UPDATE_TOTAL.labels(
                    status='error',
                    new_status=status
                ).inc()
                raise

    async def reallocate_ticket(
        self,
        ticket_id: str,
        reason: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Reallocate a single ticket for re-execution.

        This operation:
        1. Updates ticket status to PENDING
        2. Removes assigned_worker
        3. Adds reallocation metadata

        Args:
            ticket_id: Ticket identifier
            reason: Reason for reallocation (e.g., 'worker_failure', 'timeout')
            metadata: Additional context for reallocation

        Returns:
            Updated ticket data
        """
        with tracer.start_as_current_span('self_healing.reallocate_ticket') as span:
            span.set_attribute('ticket.id', ticket_id)
            span.set_attribute('reallocation.reason', reason)

            reallocation_id = str(uuid4())
            span.set_attribute('reallocation.id', reallocation_id)

            # Build reallocation metadata
            reallocation_metadata = {
                'reallocation_id': reallocation_id,
                'reallocation_reason': reason,
                'reallocation_timestamp': datetime.utcnow().isoformat(),
                'reallocation_source': 'self-healing-engine',
                **(metadata or {})
            }

            # Get current ticket to capture previous worker
            try:
                current_ticket = await self.get_ticket(ticket_id)
                previous_worker = current_ticket.get('assigned_worker')
                if previous_worker:
                    reallocation_metadata['previous_worker'] = previous_worker
            except Exception as e:
                logger.warning(
                    'self_healing_ticket_client.get_ticket_failed',
                    ticket_id=ticket_id,
                    error=str(e)
                )
                previous_worker = None

            logger.info(
                'self_healing_ticket_client.reallocating_ticket',
                ticket_id=ticket_id,
                reason=reason,
                reallocation_id=reallocation_id,
                previous_worker=previous_worker
            )

            start_time = datetime.now()
            try:
                # Update ticket: set to PENDING and remove assigned_worker
                result = await self.update_ticket_status(
                    ticket_id=ticket_id,
                    status='pending',
                    assigned_worker=None,  # Explicit None to unassign
                    metadata=reallocation_metadata
                )

                duration = (datetime.now() - start_time).total_seconds()
                TICKET_REALLOCATION_DURATION.observe(duration)
                TICKET_REALLOCATION_TOTAL.labels(
                    status='success',
                    reason=reason
                ).inc()

                logger.info(
                    'self_healing_ticket_client.ticket_reallocated',
                    ticket_id=ticket_id,
                    reallocation_id=reallocation_id,
                    duration_seconds=duration
                )

                return {
                    **result,
                    'reallocation_id': reallocation_id,
                    'previous_worker': previous_worker,
                    'reallocated': True
                }

            except Exception as e:
                duration = (datetime.now() - start_time).total_seconds()
                TICKET_REALLOCATION_DURATION.observe(duration)
                TICKET_REALLOCATION_TOTAL.labels(
                    status='error',
                    reason=reason
                ).inc()

                logger.error(
                    'self_healing_ticket_client.reallocation_failed',
                    ticket_id=ticket_id,
                    error=str(e)
                )
                raise

    async def reallocate_multiple_tickets(
        self,
        ticket_ids: List[str],
        reason: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Reallocate multiple tickets in batch.

        Uses concurrent requests with controlled parallelism.

        Args:
            ticket_ids: List of ticket identifiers
            reason: Reason for reallocation
            metadata: Additional context

        Returns:
            Summary of reallocation results
        """
        with tracer.start_as_current_span('self_healing.reallocate_multiple_tickets') as span:
            span.set_attribute('tickets.count', len(ticket_ids))
            span.set_attribute('reallocation.reason', reason)

            batch_id = str(uuid4())
            span.set_attribute('batch.id', batch_id)

            logger.info(
                'self_healing_ticket_client.reallocating_batch',
                batch_id=batch_id,
                ticket_count=len(ticket_ids),
                reason=reason
            )

            start_time = datetime.now()

            # Create tasks for concurrent reallocation (with semaphore for rate limiting)
            semaphore = asyncio.Semaphore(10)  # Max 10 concurrent requests

            async def reallocate_with_semaphore(ticket_id: str) -> Dict[str, Any]:
                async with semaphore:
                    try:
                        result = await self.reallocate_ticket(
                            ticket_id=ticket_id,
                            reason=reason,
                            metadata={
                                **(metadata or {}),
                                'batch_id': batch_id
                            }
                        )
                        return {'ticket_id': ticket_id, 'success': True, 'result': result}
                    except Exception as e:
                        return {'ticket_id': ticket_id, 'success': False, 'error': str(e)}

            # Execute all reallocations concurrently
            results = await asyncio.gather(
                *[reallocate_with_semaphore(tid) for tid in ticket_ids],
                return_exceptions=False
            )

            duration = (datetime.now() - start_time).total_seconds()

            # Summarize results
            successful = [r for r in results if r['success']]
            failed = [r for r in results if not r['success']]

            logger.info(
                'self_healing_ticket_client.batch_reallocation_complete',
                batch_id=batch_id,
                total=len(ticket_ids),
                successful=len(successful),
                failed=len(failed),
                duration_seconds=duration
            )

            return {
                'batch_id': batch_id,
                'total': len(ticket_ids),
                'successful': len(successful),
                'failed': len(failed),
                'duration_seconds': duration,
                'results': results
            }

    async def list_tickets_by_worker(
        self,
        worker_id: str,
        status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        List all tickets assigned to a specific worker.

        Args:
            worker_id: Worker identifier
            status: Optional status filter

        Returns:
            List of tickets
        """
        with tracer.start_as_current_span('self_healing.list_tickets_by_worker') as span:
            span.set_attribute('worker.id', worker_id)
            if status:
                span.set_attribute('filter.status', status)

            params = {'assigned_worker': worker_id}
            if status:
                params['status'] = status

            response = await self._make_request(
                'GET',
                '/api/v1/tickets',
                params=params
            )

            tickets = response.json()
            logger.info(
                'self_healing_ticket_client.tickets_listed',
                worker_id=worker_id,
                ticket_count=len(tickets)
            )

            return tickets

    async def health_check(self) -> bool:
        """
        Check if Execution Ticket Service is healthy.

        Returns:
            True if service is healthy, False otherwise
        """
        try:
            response = await self._make_request('GET', '/health')
            return response.status_code == 200
        except Exception as e:
            logger.warning(
                'self_healing_ticket_client.health_check_failed',
                error=str(e)
            )
            return False

    def get_circuit_breaker_state(self) -> Dict[str, Any]:
        """
        Get current circuit breaker state.

        Returns:
            Circuit breaker status information
        """
        return {
            'open': self._circuit_open,
            'failure_count': self._failure_count,
            'threshold': self._circuit_breaker_threshold,
            'opened_at': self._circuit_opened_at.isoformat() if self._circuit_opened_at else None
        }
