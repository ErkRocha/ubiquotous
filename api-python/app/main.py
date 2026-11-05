from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db import pool
from app.error_handlers import registrar_error_handlers
from app.routers import health, users


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool.open(wait=True)  # falha logo na subida se o banco não estiver acessível
    yield
    pool.close()


app = FastAPI(title="API de Usuários - Python", lifespan=lifespan)

app.include_router(health.router)
app.include_router(users.router)

registrar_error_handlers(app)
