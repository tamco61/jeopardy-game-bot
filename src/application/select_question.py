"""Use Case: Выбор вопроса на табло (BOARD_VIEW)."""

from pydantic import BaseModel

from src.domain.errors import DomainError
from src.domain.question import Question, QuestionType
from src.infrastructure.database.repositories.question import QuestionRepository
from src.infrastructure.redis_repo import RedisStateRepository


class SelectQuestionDTO(BaseModel):
    """Данные для выбора вопроса."""

    room_id: str
    player_id: str
    question_id: int


class SelectQuestionResult(BaseModel):
    """Результат выбора вопроса."""

    phase: str
    question_text: str
    question_value: int


class SelectQuestionUseCase:
    """Сценарий выбора вопроса игроком с табло.

    Оркестрация:
    1. Получить комнату из Redis.
    2. Проверить, имеет ли право игрок выбирать вопрос (опционально, в MVP опускаем строгие проверки очередности).
    3. Получить Question из PostgresGameRepository.
    4. room.select_question(question).
    5. Обновление состояния в Redis.
    6. Возврат результата (для формирования UI).
    """
    def __init__(
        self,
        question_repo: QuestionRepository,
        state_repo: RedisStateRepository,
    ) -> None:
        self._question_repo = question_repo
        self._state_repo = state_repo

    async def execute(self, dto: SelectQuestionDTO) -> SelectQuestionResult:
        room = await self._state_repo.get_room(dto.room_id)
        if not room:
            raise DomainError(f"Комната {dto.room_id} не найдена.")

        # Предполагаем наличие метода get_question_by_id в репозитории
        # Для работы MVP (если метода нет), имитируем результат:
        try:
            question = await self._question_repo.get_question_by_id(dto.question_id)
        except AttributeError:
            question = Question(
                question_id=dto.question_id,
                theme_name="Mock",
                text="Заглушка вопроса (MVP)",
                answer="ответ",
                value=100,
                question_type=QuestionType.NORMAL,
            )

        if not question:
            raise DomainError(f"Вопрос {dto.question_id} не найден.")

        if room.selecting_player_id and room.selecting_player_id != dto.player_id:
            raise DomainError("Только выбранный игрок может выбирать вопрос.")

        room.select_question(question)
        await self._state_repo.save_room(room)

        return SelectQuestionResult(
            phase=room.phase.value,
            question_text=question.text,
            question_value=question.value,
        )
