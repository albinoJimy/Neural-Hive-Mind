"""Kafka consumer for remediation actions"""
import json
import asyncio
from typing import Optional, TYPE_CHECKING
from aiokafka import AIOKafkaConsumer
import structlog

if TYPE_CHECKING:
    from src.services.playbook_executor import PlaybookExecutor

logger = structlog.get_logger()


class RemediationConsumer:
    """Consumes remediation actions from Kafka"""

    def __init__(
        self,
        bootstrap_servers: str,
        group_id: str,
        topic: str,
        playbook_executor: "PlaybookExecutor"
    ):
        self.bootstrap_servers = bootstrap_servers
        self.group_id = group_id
        self.topic = topic
        self.playbook_executor = playbook_executor

        self.consumer: Optional[AIOKafkaConsumer] = None
        self._consume_task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self):
        """Start consuming remediation actions"""
        try:
            self.consumer = AIOKafkaConsumer(
                self.topic,
                bootstrap_servers=self.bootstrap_servers,
                group_id=self.group_id,
                auto_offset_reset="earliest",
                enable_auto_commit=False
            )
            await self.consumer.start()

            self._running = True
            self._consume_task = asyncio.create_task(self._consume_loop())

            logger.info("remediation_consumer.started", topic=self.topic)
        except Exception as e:
            logger.error("remediation_consumer.start_failed", error=str(e))
            raise

    async def _consume_loop(self):
        """Main consumption loop"""
        try:
            async for msg in self.consumer:
                if not self._running:
                    break

                try:
                    remediation_action = json.loads(msg.value.decode('utf-8'))

                    logger.info(
                        "remediation_consumer.action_received",
                        action_id=remediation_action.get("action_id"),
                        playbook=remediation_action.get("playbook")
                    )

                    # Execute playbook
                    playbook_name = remediation_action.get("playbook")
                    context = remediation_action.get("context", {})

                    result = await self.playbook_executor.execute_playbook(playbook_name, context)

                    logger.info(
                        "remediation_consumer.action_completed",
                        action_id=remediation_action.get("action_id"),
                        result=result
                    )

                    await self.consumer.commit()

                except Exception as e:
                    logger.error("remediation_consumer.processing_failed", error=str(e))

        except Exception as e:
            logger.error("remediation_consumer.consume_loop_failed", error=str(e))

    async def stop(self):
        """Stop consuming"""
        self._running = False
        if self._consume_task:
            self._consume_task.cancel()
            try:
                await self._consume_task
            except asyncio.CancelledError:
                pass

        if self.consumer:
            await self.consumer.stop()

        logger.info("remediation_consumer.stopped")
