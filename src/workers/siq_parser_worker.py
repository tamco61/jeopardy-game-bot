"""Воркер для парсинга SIQ файлов."""

from __future__ import annotations

from typing import Any

from anyio import Path

from src.application.siq_parser import SiqParser
from src.infrastructure.database.postgres_repo import PostgresGameRepository
from src.workers.base import BaseWorker


class SiqParserWorker(BaseWorker):
    """Слушает очередь задач на парсинг и добавляет пакеты в БД."""

    def __init__(
        self,
        rabbitmq_url: str,
        game_repo: PostgresGameRepository,
    ) -> None:
        super().__init__(
            rabbitmq_url=rabbitmq_url,
            queue_name="siq_parse_tasks",
            name="siq_parser",
        )
        self._repo = game_repo
        self._parser = SiqParser()

    async def _process_message(self, message: dict[str, Any]) -> None:
        """Обработать сообщение с путем к файлу .siq."""
        file_path = message.get("file_path")

        if not file_path or not await Path(file_path).exists():
            self._log.error("Файл не найден или путь не указан: %s", file_path)
            return

        self._log.info("Начало парсинга файла: %s", file_path)

        try:
            # 1. Парсинг SIQ
            package_dto = self._parser.parse(file_path)
            self._log.info(
                "Файл %s успешно распарсен. Название: '%s', Раундов: %d",
                file_path,
                package_dto.title,
                len(package_dto.rounds),
            )

            # 2. Проверка на дубликаты
            exists = await self._repo.check_package_exists(package_dto.title, package_dto.author)
            if exists:
                self._log.warning(
                    "Пакет '%s' (Автор: '%s') уже существует в БД! Пропускаем сохранение.",
                    package_dto.title,
                    package_dto.author,
                )
                return

            # 3. Сохранение в БД
            package_id = await self._repo.save_package(package_dto)
            self._log.info(
                "Пакет '%s' успешно сохранен в БД с ID %d",
                package_dto.title,
                package_id,
            )

        except Exception as e:
            self._log.exception(
                "Ошибка при парсинге/сохранении пакета %s: %s", file_path, e
            )
            raise
        finally:
            if file_path and await Path(file_path).exists():
                await Path(file_path).unlink()
                self._log.info("Временный файл %s удален.", file_path)
