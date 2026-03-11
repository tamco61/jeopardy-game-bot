import aiohttp

from src.domain.room import Room
from src.shared.interfaces import MessageGateway
from src.shared.logger import get_logger
from src.bot.callback import (
    SelectQuestionCallback,
    SkipRoundCallback,
    PressButtonCallback,
    SelectPackCallback,
)

logger = get_logger(__name__)


class JeopardyUI:
    """Презентер для управления UI «Своей Игры» в Telegram."""

    def __init__(self, tg_client: MessageGateway) -> None:
        self._tg = tg_client

    async def render_board(self, chat_id: int, room: Room, board_data: list[dict]) -> dict | None:
        """Отрисовывает актуальное табло команде через Inline Keyboard."""
        keyboard = []
        for theme in board_data:
            row = []
            name = theme["theme"]
            theme_name = (name[:15] + "..") if len(name) > 17 else name
            row.append({"text": theme_name, "callback_data": "ignore"})

            for q in theme["questions"]:
                if q["id"] in room.closed_questions:
                    row.append({"text": "❌", "callback_data": "ignore"})
                else:
                    row.append({"text": str(q["value"]), "callback_data": SelectQuestionCallback(room_id=str(room.room_id), question_id=q['id']).pack()})
            keyboard.append(row)

        # Кнопка пропуска раунда (внизу табло)
        keyboard.append([{"text": "⏩ Пропустить раунд", "callback_data": SkipRoundCallback(room_id=str(room.room_id)).pack()}])

        scoreboard = self.format_scoreboard(room)
        text = f"🎮 **Табло: {room.current_round_name} ({room.round_number}/{room.total_rounds})**" + scoreboard

        # Пытаемся редактировать предыдущее сообщение, чтобы не спамить
        if room.last_board_message_id:
            try:
                return await self._tg.edit_message_text(
                    chat_id=chat_id,
                    message_id=room.last_board_message_id,
                    text=text,
                    reply_markup={"inline_keyboard": keyboard},
                )
            except aiohttp.ClientError as e:
                logger.debug(f"Could not edit board message: {e}")

        sent_msg = await self._tg.send_message(
            chat_id,
            text,
            reply_markup={"inline_keyboard": keyboard},
        )
        return sent_msg

    def format_scoreboard(self, room: Room) -> str:
        """Форматирует текущий счет игроков."""
        scoreboard = "\n\n📊 **Счет:**\n"
        for p in room.players.values():
            prefix = "👉" if p.player_id == room.selecting_player_id else "👤"
            scoreboard += f"{prefix} {p.display_name}: {p.score}\n"

        if room.selecting_player_id:
            try:
                picker = room.get_player(room.selecting_player_id)
                scoreboard += f"\n🤔 Командует @{picker.username}!"
            except Exception:
                logger.warning("Не удалось получить выбирающего игрока", exc_info=True)
        return scoreboard

    # ── Публичные делегаты к Telegram API ───────────

    async def send_message(
        self,
        chat_id: int,
        text: str,
        reply_markup: dict | None = None,
    ) -> dict:
        """Отправить сообщение."""
        return await self._tg.send_message(chat_id, text, reply_markup=reply_markup)

    async def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: dict | None = None,
    ) -> dict:
        """Отредактировать сообщение."""
        return await self._tg.edit_message_text(
            chat_id, message_id, text, reply_markup=reply_markup
        )

    async def answer_callback_query(
        self,
        callback_query_id: str,
        text: str = "",
        show_alert: bool = False,
    ) -> dict:
        """Ответить на callback_query."""
        return await self._tg.answer_callback_query(
            callback_query_id, text, show_alert
        )

    async def show_question(self, chat_id: int, text: str, value: int, reply_markup: dict | None = None) -> dict:
        """Показать текст вопроса в чате."""
        return await self._tg.send_message(
            chat_id,
            f"💰 Вопрос за {value}\n\n{text}",
            reply_markup=reply_markup
        )

    async def show_verdict(self, chat_id: int, verdict_text: str) -> None:
        """Объявить вердикт ведущего в группе."""
        await self._tg.send_message(
            chat_id,
            f"⚖️ Ведущий вынес вердикт: {verdict_text}",
        )

    async def render_buzzer(self, chat_id: int, message_id: int, text: str = "Жмите кнопку!") -> None:
        """Восстановить кнопку ответа на сообщении."""
        markup = {"inline_keyboard": [[{"text": "🟢 Ответить", "callback_data": PressButtonCallback(chat_id=chat_id).pack()}]]}
        await self._tg.edit_message_text(chat_id, message_id, text, reply_markup=markup)

    async def render_results(self, chat_id: int, room: Room) -> str:
        """Показать финальные результаты игры и вернуть текст для архива."""
        scoreboard = self.format_scoreboard(room)
        text = "🏆 **ИГРА ОКОНЧЕНА!** 🏆\n" + scoreboard
        await self._tg.send_message(chat_id, text)
        return text

    async def render_pack_selection(self, chat_id: int, packs: list[dict], room_id: str) -> None:
        """Отрисовывает меню выбора пакета вопросов."""
        keyboard = []
        for p in packs:
            keyboard.append([{"text": p["title"], "callback_data": SelectPackCallback(room_id=str(room_id), pack_id=p['id']).pack()}])
        
        await self._tg.send_message(
            chat_id,
            "📦 **Выберите пакет вопросов для игры:**",
            reply_markup={"inline_keyboard": keyboard}
        )
