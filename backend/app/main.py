from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router
from app.core.config import get_settings
from app.core.database import Base, engine
import app.models
@asynccontextmanager
async def lifespan(app):
    if get_settings().app_env in {"development","test"} or get_settings().database_url.startswith("sqlite"):
        Base.metadata.create_all(engine)
    yield
app=FastAPI(title="电竞馆智能选址系统 API",version="0.1.0",lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=["http://localhost:5173"],allow_methods=["*"],allow_headers=["*"])
app.include_router(router)

