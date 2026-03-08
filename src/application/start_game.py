from pydantic import BaseModel

from src.domain.room import Phase, Room
from src.infrastructure.database.postgres_repo import PostgresGameRepository
from src.infrastructure.redis_repo import RedisStateRepository


class StartGameDTO(BaseModel):
    """Входные данные для старта игры."""

    lobby_id: str
    chat_id: int
    host_player_id: str
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
        game_repo: PostgresGameRepository,
        state_repo: RedisStateRepository,
    ) -> None:
        self._game_repo = game_repo
        self._state_repo = state_repo

    async def execute(self, dto: StartGameDTO) -> StartGameResultDTO:
        """Инициализация комнаты на основе пакета вопросов."""
        # 1. Загружаем пакет вопросов из Postgres (предполагаем наличие метода)
        game_pack = await self._game_repo.get_game_pack(dto.pack_id)

        if not game_pack:
            raise ValueError(f"Пакет вопросов с ID {dto.pack_id} не найден.")

        # 2. Инициализация сущности Room (начинаем с LOBBY, затем переходим в BOARD_VIEW)
        room = Room(
            room_id=dto.lobby_id, chat_id=dto.chat_id, phase=Phase.LOBBY
        )

        # В реальном приложении здесь происходило бы добавление игроков,
        # и переход в BOARD_VIEW через room.start_game(). В целях текущего MVP
        # мы можем сразу выставить фазу BOARD_VIEW (либо сымитировать готовность).
        room.phase = Phase.BOARD_VIEW

        # В будущем здесь можно сохранять game_pack внутрь комнаты,
        # чтобы формировать табло. Для начала просто сохраняем стейт.

        # 3. Сохраняем состояние в Redis
        await self._state_repo.save_room(room)

        # 4. Возвращаем DTO
        return StartGameResultDTO(
            lobby_id=room.room_id,
            chat_id=room.chat_id,
            phase=room.phase.value,
            message="Игра успешно начата, табло готово.",
        )
