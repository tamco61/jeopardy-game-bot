"""Базовый класс для фоновых воркеров-потребителей очередей."""

from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from typing import Any

import aio_pika

from src.shared.logger import get_logger


class BaseWorker(ABC):
    """Абстракция воркера, потребляющего сообщения из RabbitMQ через aio_pika."""

    def __init__(self, rabbitmq_url: str, queue_name: str, name: str) -> None:
        self._url = rabbitmq_url
        self.queue_name = queue_name
        self.name = name
        self._running = False
        self._log = get_logger(f"worker.{name}")

    async def start(self) -> None:
        """Запустить цикл обработки."""
        self._running = True
        self._log.info(
            "Воркер %s подключается к очереди %s...", self.name, self.queue_name
        )

        try:
            # aio_pika.connect_robust автоматически переподключается при обрыве связи
            connection = await aio_pika.connect_robust(self._url)
            channel = await connection.channel()

            # Устанавливаем prefetch_count, чтобы не перегрузить воркер
            await channel.set_qos(prefetch_count=10)

            queue = await channel.declare_queue(self.queue_name, durable=True)

            self._log.info("Воркер %s начал прослушивание", self.name)

            async with queue.iterator() as queue_iter:
                async for message in queue_iter:
                    if not self._running:
                        self._log.info(
                            "Остановка прослушивания воркером %s", self.name
                        )
                        break

                    async with message.process(requeue=False):
                        body = json.loads(message.body.decode())
                        try:
                            await self._process_message(body)
                        except Exception as e:
                            self._log.exception(
                                "Ошибка при обработке сообщения в воркере %s: %s",
                                self.name,
                                e,
                            )
                            # message.process() сам вернет сообщение в очередь (nack/reject) если мы поднимем исключение
                            raise
        except asyncio.CancelledError:
            self._log.info("Воркер %s остановлен (CancelledError)", self.name)
        except Exception as e:
            self._log.exception(
                "Критическая ошибка в воркере %s: %s", self.name, e
            )
        finally:
            self._running = False

    async def stop(self) -> None:
        """Остановить воркер."""
        self._running = False
        self._log.info("Воркер %s: запрошена остановка", self.name)

    @abstractmethod
    async def _process_message(self, message: dict[str, Any]) -> None:
        """Обработать одно сообщение из очереди."""
        ...
