"""Адаптер кэша (Redis).

- ``redis_state_repo.py`` — RedisStateRepository (реализует IStateRepository)
"""

from src.infrastructure.cache.redis_state_repo import RedisStateRepository

__all__: list[str] = ["RedisStateRepository"]
