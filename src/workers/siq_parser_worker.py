"""Воркер для парсинга SIQ файлов и загрузки медиа."""

from __future__ import annotations

import asyncio
from typing import Any

from anyio import Path

from src.application.parser.siq_parser import SiqParser
from src.infrastructure.database.repositories.package import PackageRepository
from src.workers.base import BaseWorker
from src.application.media_uploader import TelegramMediaUploader


class SiqParserWorker(BaseWorker):
    """Слушает очередь задач на парсинг, загружает медиа и добавляет пакеты в БД."""

    def __init__(
            self,
            rabbitmq_url: str,
            package_repo: PackageRepository,
            media_uploader: TelegramMediaUploader,
    ) -> None:
        super().__init__(
            rabbitmq_url=rabbitmq_url,
            queue_name="siq_parse_tasks",
            name="parser",
        )
        self._repo = package_repo
        self._parser = SiqParser()
        self._uploader = media_uploader  # Сервис для работы с Telegram

    async def _process_message(self, message: dict[str, Any]) -> None:
        """Обработать сообщение с путем к файлу .siq."""
        file_path = message.get("file_path")

        if not file_path or not await Path(file_path).exists():
            self._log.error("Файл не найден или путь не указан: %s", file_path)
            return

        self._log.info("Начало парсинга файла: %s", file_path)

        try:
            # 1. Парсинг SIQ (извлечение структуры и байтов в память)
            package_dto = await asyncio.to_thread(self._parser.parse, file_path)

            # 2. Проверка на дубликаты (Делаем ДО загрузки медиа!)
            exists = await self._repo.check_package_exists(package_dto.title, package_dto.author)
            if exists:
                self._log.warning(
                    "Пакет '%s' (Автор: '%s') уже существует в БД! Пропускаем загрузку медиа и сохранение.",
                    package_dto.title,
                    package_dto.author,
                )
                return

            self._log.info(
                "Файл %s распаршен. Название: '%s', Раундов: %d. Начинаю загрузку медиа в Telegram...",
                file_path,
                package_dto.title,
                len(package_dto.rounds),
            )

            # 3. Загрузка медиа в секретный чат Telegram
            package_dto = await self._uploader.upload_package_media(package_dto)
            self._log.info("Все медиафайлы для пакета '%s' успешно загружены.", package_dto.title)

            # 4. Сохранение структуры в БД (с заполненными telegram_file_id)
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
            # Независимо от исхода (успех или ошибка) удаляем тяжелый исходник
            if file_path and await Path(file_path).exists():
                await Path(file_path).unlink()
                self._log.info("Временный файл %s удален.", file_path)