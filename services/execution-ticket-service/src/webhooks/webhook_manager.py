"""
Webhook Manager para notificações push de Worker Agents.
"""
import asyncio
import hashlib
import hmac
import logging
import time
from typing import Optional

import aiohttp

from ..config import get_settings
from ..models import WebhookEvent
from ..observability.metrics import TicketServiceMetrics

logger = logging.getLogger(__name__)


class WebhookManager:
    """Gerenciador de webhooks com fila assíncrona e retry."""

    def __init__(self, settings, metrics: TicketServiceMetrics):
        """Inicializa webhook manager."""
        self.settings = settings
        self.metrics = metrics
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self.workers = []
        self.running = False
        self.http_session: Optional[aiohttp.ClientSession] = None

    async def start(self):
        """Inicia webhook manager e workers."""
        # Criar sessão HTTP
        timeout = aiohttp.ClientTimeout(total=self.settings.webhook_timeout_seconds)
        self.http_session = aiohttp.ClientSession(timeout=timeout)

        # Iniciar workers
        self.running = True
        for i in range(self.settings.webhook_worker_count):
            worker = asyncio.create_task(self._worker_loop(i))
            self.workers.append(worker)

        logger.info(
            f"Webhook manager started",
            workers=self.settings.webhook_worker_count,
            queue_size=self.queue.maxsize
        )

    async def stop(self):
        """Para webhook manager gracefully."""
        logger.info("Stopping webhook manager...")
        self.running = False

        # Processar eventos restantes na fila
        while not self.queue.empty():
            try:
                event = self.queue.get_nowait()
                await self._send_webhook(event)
            except asyncio.QueueEmpty:
                break
            except Exception as e:
                logger.error(f"Error processing remaining webhook: {e}")

        # Cancelar workers
        for worker in self.workers:
            worker.cancel()

        # Aguardar workers terminarem
        await asyncio.gather(*self.workers, return_exceptions=True)

        # Fechar sessão HTTP
        if self.http_session:
            await self.http_session.close()

        logger.info("Webhook manager stopped")

    async def enqueue_webhook(self, event: WebhookEvent):
        """
        Adiciona webhook event na fila.

        Args:
            event: WebhookEvent para processar
        """
        try:
            self.queue.put_nowait(event)
            self.metrics.webhooks_enqueued_total.inc()
            self.metrics.webhook_queue_size.set(self.queue.qsize())

            logger.debug(
                f"Webhook enqueued",
                event_id=event.event_id,
                ticket_id=event.ticket_id,
                queue_size=self.queue.qsize()
            )

        except asyncio.QueueFull:
            logger.warning(
                f"Webhook queue full, dropping event",
                event_id=event.event_id,
                ticket_id=event.ticket_id
            )
            self.metrics.webhooks_failed_total.inc()

    async def _worker_loop(self, worker_id: int):
        """
        Loop de processamento de worker.

        Args:
            worker_id: ID do worker
        """
        logger.info(f"Webhook worker {worker_id} started")

        while self.running:
            try:
                # Aguardar evento com timeout
                event = await asyncio.wait_for(self.queue.get(), timeout=1.0)

                # Processar webhook
                await self._send_webhook(event)

                # Atualizar métrica de queue size
                self.metrics.webhook_queue_size.set(self.queue.qsize())

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                logger.info(f"Webhook worker {worker_id} cancelled")
                break
            except Exception as e:
                logger.error(
                    f"Worker {worker_id} error: {e}",
                    exc_info=True
                )

        logger.info(f"Webhook worker {worker_id} stopped")

    async def _send_webhook(self, event: WebhookEvent):
        """
        Envia webhook HTTP POST.

        Args:
            event: WebhookEvent para enviar
        """
        start_time = time.time()

        try:
            # Preparar payload
            payload = event.to_http_payload()

            # Calcular assinatura HMAC
            signature = self._calculate_signature(payload)

            # Headers
            headers = {
                'Content-Type': 'application/json',
                'X-Neural-Hive-Event': event.event_type,
                'X-Neural-Hive-Ticket-Id': event.ticket_id,
                'X-Neural-Hive-Signature': signature,
                'User-Agent': 'Neural-Hive-Execution-Ticket-Service/1.0'
            }

            # Enviar POST
            async with self.http_session.post(
                str(event.webhook_url),
                json=payload,
                headers=headers
            ) as response:
                event.response_status_code = response.status
                event.response_body = await response.text()

                if 200 <= response.status < 300:
                    event.status = 'sent'
                    self.metrics.webhooks_sent_total.inc()

                    logger.info(
                        f"Webhook sent successfully",
                        event_id=event.event_id,
                        ticket_id=event.ticket_id,
                        url=event.webhook_url,
                        status_code=response.status
                    )
                else:
                    raise Exception(f"HTTP {response.status}: {event.response_body}")

        except Exception as e:
            event.error_message = str(e)
            event.status = 'failed'

            logger.error(
                f"Webhook failed",
                event_id=event.event_id,
                ticket_id=event.ticket_id,
                url=event.webhook_url,
                error=str(e)
            )

            self.metrics.webhooks_failed_total.inc()

            # Retry logic
            if event.should_retry():
                event.retry_count += 1
                event.next_retry_at = event.calculate_next_retry()

                # Calcular delay
                delay_seconds = (event.next_retry_at - int(time.time() * 1000)) / 1000.0

                logger.info(
                    f"Scheduling webhook retry",
                    event_id=event.event_id,
                    ticket_id=event.ticket_id,
                    retry_count=event.retry_count,
                    delay_seconds=delay_seconds
                )

                # Aguardar e re-enfileirar
                await asyncio.sleep(delay_seconds)
                await self.enqueue_webhook(event)
            else:
                logger.warning(
                    f"Webhook max retries exceeded",
                    event_id=event.event_id,
                    ticket_id=event.ticket_id,
                    retry_count=event.retry_count
                )

        finally:
            # Métrica de duração
            duration = time.time() - start_time
            self.metrics.webhook_duration_seconds.observe(duration)

    def _calculate_signature(self, payload: dict) -> str:
        """
        Calcula assinatura HMAC-SHA256 do payload.

        Args:
            payload: Payload do webhook

        Returns:
            Assinatura hexadecimal
        """
        import json

        # Serializar payload
        payload_str = json.dumps(payload, sort_keys=True)

        # Calcular HMAC
        signature = hmac.new(
            self.settings.jwt_secret_key.encode('utf-8'),
            payload_str.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        return signature


async def start_webhook_manager(metrics: TicketServiceMetrics) -> WebhookManager:
    """
    Factory function para criar e iniciar webhook manager.

    Args:
        metrics: Instância de TicketServiceMetrics

    Returns:
        WebhookManager iniciado
    """
    settings = get_settings()
    manager = WebhookManager(settings, metrics)
    await manager.start()
    return manager
