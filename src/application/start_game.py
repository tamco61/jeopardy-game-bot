import logging

from pydantic import BaseModel

from src.domain.errors import DomainError
from src.infrastructure.database.repositories.game_session import (
    GameSessionRepository,
)
from src.infrastructure.database.repositories.package import PackageRepository
from src.infrastructure.database.repositories.round import RoundRepository
from src.infrastructure.redis_repo import RedisStateRepository


class StartGameDTO(BaseModel):
    """Входные данные для старта игры."""

    lobby_id: str
    chat_id: int
    host_player_id: str
    host_telegram_id: int
    pack_id: int


class StartGameResultDTO(BaseModel):
    """Результат старта игры."""

    lobby_id: str
    chat_id: int
    phase: str
    message: str


class StartGameUseCase:
    """Сценарий запуска нового раунда / игры.

    Оркестрация:
    1. Получить пакет вопросов из PostgresGameRepository.
    2. Инициализировать доменную сущность Room (переход из LOBBY в BOARD_VIEW).
    3. Сохранить начальное состояние в RedisStateRepository.
    4. Вернуть DTO с результатом.
    """

    def __init__(
        self,
        package_repo: PackageRepository,
        round_repo: RoundRepository,
        state_repo: RedisStateRepository,
        session_repo: GameSessionRepository | None = None,
    ) -> None:
        self._package_repo = package_repo
        self._round_repo = round_repo
        self._state_repo = state_repo
        self._session_repo = session_repo

    async def execute(self, dto: StartGameDTO) -> StartGameResultDTO:
        """Инициализация комнаты на основе пакета вопросов."""
        # 1. Проверяем существование пакета в Postgres
        pack_exists = await self._package_repo.get_package_by_id(dto.pack_id)

        if not pack_exists:
            raise ValueError(f"Пакет вопросов с ID {dto.pack_id} не найден в БД.")

        rounds = await self._round_repo.get_rounds_by_package(dto.pack_id)
        if not rounds:
            raise ValueError(f"В пакете {dto.pack_id} нет раундов.")

        first_round = rounds[0]
        first_round_id = first_round["id"]
        first_round_name = first_round["name"]

        # 2. Инициализация сущности Room
        room = await self._state_repo.get_room(dto.lobby_id)
        if not room:
            raise DomainError(f"Лобби {dto.lobby_id} не найдено.")

        # Переводим фазу через FSM
        room.start_game()
        
        # Привязываем пакет и текущий раунд
        room.package_id = dto.pack_id
        room.current_round_id = first_round_id
        room.current_round_name = first_round_name
        room.round_number = 1
        room.total_rounds = len(rounds)

        # 3. Сохраняем состояние в Redis
        await self._state_repo.save_room(room)

        # 4. Создаём запись в Postgres (для восстановления после блэкаута)
        if self._session_repo:
            try:
                await self._session_repo.create_session(room)
            except Exception as e:
                # Не ломаем игру из-за ошибки персистентности
                logging.getLogger(__name__).error(
                    "Ошибка create_session: %s", e
                )

        # 5. Возвращаем DTO
        return StartGameResultDTO(
            lobby_id=room.room_id,
            chat_id=room.chat_id,
            phase=room.phase.value,
            message="Игра успешно начата, табло готово.",
        )
