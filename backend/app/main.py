from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router
from app.chat import router as chat_router
from app.core.config import get_settings
from app.core.database import Base, engine
from app.data_source.router import router as data_source_router
from app.data_source.competitor.router import router as competitor_data_router
from app.data_source.supporting.router import router as supporting_data_router
from app.data_source.rent.router import router as rent_data_router
from app.llm import router as llm_router
from app.manual_input import router as manual_input_router
from app.map_data import router as map_data_router
from app.projects import router as projects_router
from app.scoring_engine import router as scoring_engine_router
from app.system_config import router as system_config_router
import app.models
@asynccontextmanager
async def lifespan(app):
    if get_settings().app_env in {"development","test"} or get_settings().database_url.startswith("sqlite"):
        Base.metadata.create_all(engine)
    yield
app=FastAPI(title="电竞馆智能选址系统 API",version="1.0.0-beta",lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=["http://localhost:5173"],allow_methods=["*"],allow_headers=["*"])
app.include_router(router)
app.include_router(data_source_router)
app.include_router(competitor_data_router)
app.include_router(supporting_data_router)
app.include_router(rent_data_router)
app.include_router(projects_router)
app.include_router(map_data_router)
app.include_router(manual_input_router)
app.include_router(scoring_engine_router)
app.include_router(llm_router)
app.include_router(chat_router)
app.include_router(system_config_router)
