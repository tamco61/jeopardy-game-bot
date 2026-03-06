"""Адаптер базы данных (Postgres).

- ``base.py``                — Base, build_engine, build_session_factory
- ``models.py``              — ORM-модели (SQLAlchemy)
- ``postgres_game_repo.py``  — PostgresGameRepository (реализует IGameRepository)
"""

from src.infrastructure.database.postgres_game_repo import PostgresGameRepository

__all__: list[str] = ["PostgresGameRepository"]
