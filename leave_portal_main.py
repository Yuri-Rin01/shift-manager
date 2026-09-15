"""職員向け休み希望ポータル（別ポート起動用）。

管理者用アプリ（main.py）とは別プロセスで起動し、同じ shift.db を共有します。

起動例:
  uvicorn leave_portal_main:app --host 127.0.0.1 --port 8004
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app_paths import resource_root
from db.database import init_db
from routers.leave_portal import router as leave_portal_router

BASE_DIR = resource_root()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="休み希望入力ポータル",
    description="職員が休み希望を登録するための別ポート用アプリ",
    lifespan=lifespan,
)
app.include_router(leave_portal_router)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
