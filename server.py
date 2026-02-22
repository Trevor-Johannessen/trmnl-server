from dotenv import load_dotenv
load_dotenv()
from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict, Optional
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi_cache.decorator import cache
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
from typing import Dict, Any
from datetime import datetime, timedelta
from screenController import ScreenController
from init import init_screen

@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    FastAPICache.init(InMemoryBackend())
    yield

app = FastAPI(lifespan=lifespan)
controller = ScreenController(init_screen)

@app.get("/update")
@cache(namespace="cache", expire=30)
async def update():
    print("Update cache expired!")
    return controller.render()

@app.post("/update/ai")
async def test(data: Dict[str, Any]):
    controller.update("ChatbotWindow", data)

i=0
@app.get("/image")
async def image():
    global i
    i+=1
    if i%2:
        return FileResponse("pg-coral.png")
    return FileResponse("ia-forrest.png")

@app.get("/")
async def test():
    return "This is a test message"
