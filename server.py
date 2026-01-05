from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI
from fastapi.responses import FileResponse
from typing import Dict, Any
from datetime import datetime, timedelta
from screenController import ScreenController
from init import init_screen

app = FastAPI()
controller = ScreenController(init_screen)

@app.get("/update")
async def update():
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
