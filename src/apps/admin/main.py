import os
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.shared.config import AppSettings
from src.shared.logger import get_logger
from src.infrastructure.redis_repo import RedisStateRepository
from src.infrastructure.database.base import build_engine, build_session_factory
from src.infrastructure.database.repositories.package import PackageRepository

logger = get_logger(__name__)

# Singletons
settings = AppSettings()
state_repo: RedisStateRepository | None = None
package_repo: PackageRepository | None = None
redis_client = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global state_repo, package_repo, redis_client
    logger.info("🚀 Запуск Admin Service...")
    
    # Redis
    redis_client = aioredis.from_url(settings.redis_url)
    state_repo = RedisStateRepository(redis_client)
    
    # Postgres
    engine = build_engine(settings.database_url)
    session_factory = build_session_factory(engine)
    package_repo = PackageRepository(session_factory)
    
    logger.info("✅ Подключено к инфраструктуре")
    yield
    if redis_client:
        await redis_client.close()
    logger.info("👋 Admin Service остановлен")

app = FastAPI(title="Jeopardy Admin Service", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/stats")
async def get_stats():
    """Общая статистика системы."""
    if not state_repo or not package_repo:
        raise HTTPException(status_code=503, detail="Service initializing")
        
    rooms = await state_repo.get_all_rooms()
    packages = await package_repo.get_all_packages()
    
    return {
        "active_rooms": len(rooms),
        "total_packages": len(packages),
        "total_players": sum(len(r.players) for r in rooms)
    }

@app.get("/rooms")
async def list_rooms():
    """Список всех активных игровых комнат (исключая завершённые игры)."""
    if not state_repo:
        return []
    rooms = await state_repo.get_all_rooms()
    return [
        {
            "room_id": r.room_id,
            "chat_id": r.chat_id,
            "phase": r.phase,
            "player_count": len(r.players),
            "current_round": r.round_number,
            "players": [p.display_name for p in r.players.values()]
        }
        for r in rooms
        if r.phase != "results"
    ]

@app.post("/rooms/clear/{room_id}")
async def clear_room(room_id: str):
    """Принудительная очистка состояния комнаты."""
    if not state_repo:
        raise HTTPException(status_code=503)
    
    await state_repo.delete_room(room_id)
    return {"status": "success", "message": f"Room {room_id} cleared"}

@app.get("/packages")
async def list_packages():
    """Список всех загруженных пакетов."""
    if not package_repo:
        return []
    return await package_repo.get_all_packages()

@app.delete("/packages/{package_id}")
async def delete_package(package_id: int):
    """Удалить пакет из базы."""
    if not package_repo:
        raise HTTPException(status_code=503)
    
    success = await package_repo.delete_package(package_id)
    if not success:
        raise HTTPException(status_code=404, detail="Package not found")
    
    return {"status": "success"}

# Serve Admin UI
static_path = os.path.join(os.path.dirname(__file__), "static")
if not os.path.exists(static_path):
    os.makedirs(static_path, exist_ok=True)

app.mount("/", StaticFiles(directory=static_path, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.apps.admin.main:app", host="0.0.0.0", port=8001, reload=True)
