"""Сервис проверки ответов через LLM (OpenRouter API)."""

import aiohttp

from src.shared.config import AppSettings
from src.shared.logger import get_logger

logger = get_logger(__name__)


class LlmAnswerVerifier:
    """Проверка ответов игроков через OpenRouter API."""

    def __init__(self, config: AppSettings) -> None:
        self._api_key = config.openrouter_api_key
        self._model = config.openrouter_model
        self._base_url = "https://openrouter.ai/api/v1/chat/completions"

    async def verify_answer(
        self,
        question_text: str,
        correct_answer: str,
        player_answer: str,
    ) -> bool:
        """
        Проверить ответ игрока через LLM.

        Args:
            question_text: Текст вопроса
            correct_answer: Правильный ответ (эталон)
            player_answer: Ответ игрока

        Returns:
            True если ответ верный, False если неверный
        """
        if not self._api_key:
            logger.warning("OpenRouter API ключ не задан, ответ считается неверным")
            return False

        prompt = self._build_prompt(question_text, correct_answer, player_answer)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self._base_url,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://github.com/jeopardy-game-bot",
                        "X-Title": "Jeopardy Game Bot",
                    },
                    json={
                        "model": self._model,
                        "messages": [
                            {
                                "role": "system",
                                "content": (
                                    "Ты — строгий, но справедливый ведущий викторины «Своя Игра». "
                                    "Твоя задача — проверять ответы игроков. "
                                    "Сравнивай ответ игрока с правильным ответом и определяй, "
                                    "можно ли засчитать ответ как верный. "
                                    "Синонимы, близкие по смыслу формулировки и небольшие неточности "
                                    "можно засчитывать, если смысл сохранён. "
                                    "Если ответ игрока принципиально отличается по смыслу — считай его неверным. "
                                    "ВЕРНИ ТОЛЬКО ОДНО СЛОВО: YES или NO."
                                ),
                            },
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.1,
                        "max_tokens": 10,
                    },
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as response:
                    if response.status != 200:
                        logger.error(
                            "OpenRouter API error: %d %s",
                            response.status,
                            await response.text(),
                        )
                        return False

                    data = await response.json()
                    llm_response = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip().upper()

                    logger.info("LLM вердикт: %s", llm_response)

                    return "YES" in llm_response

        except aiohttp.ClientError as e:
            logger.error("Ошибка подключения к OpenRouter API: %s", e)
            return False
        except TimeoutError:
            logger.error("Таймаут при обращении к OpenRouter API")
            return False
        except Exception as e:
            logger.exception("Неожиданная ошибка при проверке ответа через LLM: %s", e)
            return False

    def _build_prompt(
        self,
        question_text: str,
        correct_answer: str,
        player_answer: str,
    ) -> str:
        """Сформировать промпт для LLM."""
        return (
            f"ВОПРОС: {question_text}\n\n"
            f"ПРАВИЛЬНЫЙ ОТВЕТ: {correct_answer}\n\n"
            f"ОТВЕТ ИГРОКА: {player_answer}\n\n"
            f"Засчитать ли ответ игрока как верный? (YES/NO):"
        )
