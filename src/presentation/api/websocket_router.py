"""WebSocket-роутер для фронтенда «Своей игры»."""

from __future__ import annotations


class WebSocketRouter:
    """Обработчик WebSocket-соединений.

    Принимает подключения от фронтенда, парсит WebSocketMessageDTO
    и направляет в соответствующий Use Case.

    TODO: реализовать подключение, рассылку состояния комнаты,
    обработку нажатий кнопки и ответов через WebSocket.
    """

    async def handle_connection(self, ws: object) -> None:
        """Обработать одно WS-соединение.

        TODO: реализовать.
        """
        raise NotImplementedError
