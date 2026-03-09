from src.domain.room import Room
from src.infrastructure.telegram import TelegramHttpClient
from src.shared.logger import get_logger

logger = get_logger(__name__)


class JeopardyUI:
    """Презентер для управления UI «Своей Игры» в Telegram."""

    def __init__(self, tg_client: TelegramHttpClient) -> None:
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
                    row.append({"text": str(q["value"]), "callback_data": f"select_question:{q['id']}"})
            keyboard.append(row)

        scoreboard = self.format_scoreboard(room)
        text = f"🎮 **Табло (Раунд {room.current_round_id})**" + scoreboard

        # Пытаемся редактировать предыдущее сообщение, чтобы не спамить
        if room.last_board_message_id:
            try:
                return await self._tg.edit_message_text(
                    chat_id=chat_id,
                    message_id=room.last_board_message_id,
                    text=text,
                    reply_markup={"inline_keyboard": keyboard},
                )
            except Exception as e:
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
                pass
        return scoreboard

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
