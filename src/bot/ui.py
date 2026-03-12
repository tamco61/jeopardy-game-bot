import asyncio

import aiohttp

from src.bot.callback import (
    LobbyLeaveCallback,
    LobbyNotReadyCallback,
    LobbyReadyCallback,
    PressButtonCallback,
    SelectPackCallback,
    SelectQuestionCallback,
    SkipRoundCallback,
    StartGameCallback,
    StakeCallback,
)
from src.domain.room import Phase, Room
from src.infrastructure.rabbit import RabbitMQPublisher
from src.shared.interfaces import MessageGateway
from src.shared.logger import get_logger
from src.shared.messages import WebUIUpdate

logger = get_logger(__name__)


class JeopardyUI:
    """Презентер для управления UI «Своей Игры» в Telegram."""

    def __init__(self, tg_client: MessageGateway, rabbit_publisher: RabbitMQPublisher | None = None) -> None:
        self._tg = tg_client
        self._rabbit = rabbit_publisher

    async def _broadcast_ui(self, room_id: str, event_type: str, payload: dict) -> None:
        """Отправить обновление в RabbitMQ для трансляции на Web (Proxy)."""
        if not self._rabbit:
            return
        
        update = WebUIUpdate(
            room_id=room_id,
            event_type=event_type,
            payload=payload
        )
        try:
            await self._rabbit.publish("ui_updates", update.model_dump())
        except Exception as e:
            logger.error("❌ Ошибка бродкаста UI: %s", e)

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

        # Бродкастим состояние табло для веба — всегда, до отправки в TG
        await self._broadcast_ui(str(room.room_id), "board_updated", {
            "round_name": room.current_round_name,
            "round_number": room.round_number,
            "board": board_data,
            "closed_questions": list(room.closed_questions),
            "scores": {p.player_id: {"name": p.display_name, "score": p.score} for p in room.players.values()}
        })

        # Пытаемся редактировать предыдущее сообщение
        if room.last_board_message_id:
            try:
                await self._tg.edit_message_text(
                    chat_id=chat_id,
                    message_id=room.last_board_message_id,
                    text=text,
                    reply_markup={"inline_keyboard": keyboard},
                )
                return None  # message_id не изменился
            except aiohttp.ClientError as e:
                logger.debug("Не удалось отредактировать табло: %s", e)
                await self.delete_message(chat_id, room.last_board_message_id)

        sent_msg = await self._tg.send_message(
            chat_id,
            text,
            reply_markup={"inline_keyboard": keyboard},
        )
        if sent_msg and "result" in sent_msg:
            return sent_msg["result"]["message_id"]
        return None

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

    async def show_question(
        self,
        chat_id: int,
        room_id: str,
        text: str,
        value: int,
        reply_markup: dict | None = None,
    ) -> int | None:
        """Показать текст вопроса в чате. Возвращает message_id."""
        await self._broadcast_ui(room_id, "question_opened", {
            "text": text,
            "value": value,
        })
        sent = await self._tg.send_message(
            chat_id,
            f"💰 Вопрос за {value}\n\n{text}",
            reply_markup=reply_markup,
        )
        if sent and "result" in sent:
            return sent["result"]["message_id"]
        return None

    async def show_verdict(
        self,
        chat_id: int,
        room_id: str,
        verdict_text: str,
        buzzer_message_id: int | None = None,
    ) -> None:
        """Объявить вердикт ведущего — редактирует buzzer-сообщение."""
        await self._broadcast_ui(room_id, "verdict_announced", {
            "verdict": verdict_text,
        })
        if buzzer_message_id:
            try:
                await self._tg.edit_message_text(
                    chat_id,
                    buzzer_message_id,
                    f"⚖️ {verdict_text}",
                )
                asyncio.create_task(
                    self._delete_after(chat_id, buzzer_message_id, delay=4.0)
                )
                return
            except aiohttp.ClientError as e:
                logger.debug("Не удалось отредактировать buzzer для вердикта: %s", e)
        await self.send_temporary(chat_id, f"⚖️ {verdict_text}", delay=4.0)

    async def delete_message(self, chat_id: int, message_id: int) -> None:
        """Тихо удалить сообщение (игнорирует ошибки)."""
        try:
            await self._tg.delete_message(chat_id, message_id)
        except Exception as e:
            logger.debug("Не удалось удалить сообщение %d: %s", message_id, e)

    async def send_temporary(
        self, chat_id: int, text: str, delay: float = 5.0
    ) -> None:
        """Отправить сообщение и удалить его через delay секунд."""
        sent = await self._tg.send_message(chat_id, text)
        if sent and "result" in sent:
            msg_id = sent["result"]["message_id"]
            asyncio.create_task(self._delete_after(chat_id, msg_id, delay))

    async def _delete_after(
        self, chat_id: int, message_id: int, delay: float
    ) -> None:
        try:
            await asyncio.sleep(delay)
            await self.delete_message(chat_id, message_id)
        except asyncio.CancelledError:
            pass

    async def render_buzzer(self, chat_id: int, room_id: str, message_id: int, text: str = "Жмите кнопку!") -> None:
        """Восстановить кнопку ответа на сообщении."""
        await self._broadcast_ui(room_id, "buzzer_activated", {})
        markup = {"inline_keyboard": [[{"text": "🟢 Ответить", "callback_data": PressButtonCallback(chat_id=chat_id).pack()}]]}
        await self._tg.edit_message_text(chat_id, message_id, text, reply_markup=markup)

    async def render_answering_view(self, room_id: str, player_id: str, name: str) -> None:
        """Уведомить веб-клиентов о начале ввода ответа."""
        await self._broadcast_ui(room_id, "answering_started", {
            "player_id": player_id,
            "name": name
        })

    async def render_results(self, chat_id: int, room: Room) -> str:
        """Показать финальные результаты игры и вернуть текст для архива."""
        scoreboard = self.format_scoreboard(room)
        text = "🏆 **ИГРА ОКОНЧЕНА!** 🏆\n" + scoreboard
        await self._tg.send_message(chat_id, text)
        await self._broadcast_ui(str(room.room_id), "game_finished", {
            "scores": [
                {"name": p.display_name, "score": p.score}
                for p in sorted(room.players.values(), key=lambda p: p.score, reverse=True)
            ]
        })
        return text

    async def send_game_snapshot(self, room: Room, board_data: list[dict] | None = None) -> None:
        """Отправить снимок текущего состояния игры в web (для переподключившихся клиентов)."""
        room_id = str(room.room_id)

        if room.phase == Phase.LOBBY:
            await self._broadcast_ui(room_id, "lobby_updated", {
                "players": [
                    {"id": p.player_id, "name": p.display_name, "is_ready": p.is_ready}
                    for p in room.players.values()
                ]
            })
        elif room.phase == Phase.BOARD_VIEW and board_data:
            await self._broadcast_ui(room_id, "board_updated", {
                "round_name": room.current_round_name,
                "round_number": room.round_number,
                "board": board_data,
                "closed_questions": list(room.closed_questions),
                "scores": {
                    p.player_id: {"name": p.display_name, "score": p.score}
                    for p in room.players.values()
                }
            })
        elif room.phase in (Phase.READING, Phase.WAITING_FOR_PUSH):
            if room.current_question:
                await self._broadcast_ui(room_id, "question_opened", {
                    "text": room.current_question.text,
                    "value": room.current_question.value,
                })
            if room.phase == Phase.WAITING_FOR_PUSH:
                await self._broadcast_ui(room_id, "buzzer_activated", {})
        elif room.phase == Phase.ANSWERING:
            if room.current_question:
                await self._broadcast_ui(room_id, "question_opened", {
                    "text": room.current_question.text,
                    "value": room.current_question.value,
                })
            if room.answering_player_id:
                player = room.players.get(room.answering_player_id)
                await self._broadcast_ui(room_id, "answering_started", {
                    "player_id": room.answering_player_id,
                    "name": player.display_name if player else room.answering_player_id,
                })
        elif room.phase == Phase.RESULTS:
            await self._broadcast_ui(room_id, "game_finished", {
                "scores": [
                    {"name": p.display_name, "score": p.score}
                    for p in sorted(room.players.values(), key=lambda p: p.score, reverse=True)
                ]
            })

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

    async def render_lobby_update(self, chat_id: int, room: Room) -> int | None:
        """Отрисовывает состояние лобби для всех платформ (TG + Web).

        Returns:
            message_id нового сообщения или None если было редактирование.
        """
        host = room.players.get(room.host_id)
        host_line = (
            f"🎙 Ведущий: @{host.username}\n\n" if host else ""
        )

        lines = []
        for p in room.players.values():
            icon = "✅" if p.is_ready else "⏳"
            lines.append(f"{icon} @{p.username}: {p.score}")

        players_block = "\n".join(lines) if lines else "Пока никого нет"
        text = (
            f"🎮 **Лобби игры**\n\n"
            f"{host_line}"
            f"👥 Игроки ({len(lines)}):\n{players_block}\n\n"
            f"Нажми **Готов**, когда будешь готов к игре!"
        )

        keyboard = {
            "inline_keyboard": [
                [
                    {
                        "text": "✅ Готов",
                        "callback_data": LobbyReadyCallback().pack(),
                    },
                    {
                        "text": "❌ Не готов",
                        "callback_data": LobbyNotReadyCallback().pack(),
                    },
                    {
                        "text": "🚪 Выйти",
                        "callback_data": LobbyLeaveCallback().pack(),
                    },
                ],
                [
                    {
                        "text": "🚀 Начать игру",
                        "callback_data": StartGameCallback().pack(),
                    }
                ],
            ]
        }

        # Бродкастим в Web
        await self._broadcast_ui(str(room.room_id), "lobby_updated", {
            "players": [
                {"id": p.player_id, "name": p.display_name, "is_ready": p.is_ready}
                for p in room.players.values()
            ]
        })

        # Редактируем существующее сообщение или отправляем новое
        if room.last_lobby_message_id:
            try:
                await self._tg.edit_message_text(
                    chat_id=chat_id,
                    message_id=room.last_lobby_message_id,
                    text=text,
                    reply_markup=keyboard,
                )
                return None
            except aiohttp.ClientError as e:
                logger.debug("Не удалось отредактировать лобби-сообщение: %s", e)

        sent = await self._tg.send_message(chat_id, text, reply_markup=keyboard)
        if sent and "result" in sent:
            return sent["result"]["message_id"]
        return None

    async def send_stake_options(
        self, player_telegram_id: int, room_id: str, score: int
    ) -> None:
        """Отправить игроку в ЛС кнопки с вариантами ставок."""
        if score > 0:
            opts = sorted({
                max(1, score // 4),
                max(1, score // 2),
                max(1, 3 * score // 4),
                score,
            })
        else:
            opts = [0]

        buttons = [
            {
                "text": f"{o} 💰",
                "callback_data": StakeCallback(room_id=room_id, amount=o).pack(),
            }
            for o in opts[:4]
        ]
        kb = {"inline_keyboard": [buttons]}
        await self._tg.send_message(
            player_telegram_id,
            f"💰 **Финальная ставка!**\nВаш счёт: **{score}**\nСделайте ставку:",
            reply_markup=kb,
        )
