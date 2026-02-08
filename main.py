import os
import shutil
import base64
import asyncio
from pathlib import Path
from uuid import uuid4
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, UploadFile, Depends, Response
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import aiofiles

from chatkit.server import StreamingResult
from chatkit.types import FileAttachment, ImageAttachment

from app.server import MyChatKitServer
from app.store import SQLiteStore
from app.types import RequestContext

load_dotenv()

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# Initialize store globally, but connect in lifespan
store = SQLiteStore()
server = MyChatKitServer(store=store, attachment_store=store)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Connect to DB
    await store.connect()
    yield
    # Shutdown: Close DB
    await store.close()

app = FastAPI(lifespan=lifespan)

# --- Enable CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_user(request: Request) -> RequestContext:
    user_id = request.headers.get("x-chatkit-user")
    if not user_id:
        user_id = "anonymous-default"
    return RequestContext(user_id=user_id)

@app.post("/chatkit")
async def handle_chatkit(request: Request, ctx: RequestContext = Depends(get_user)):
    try:
        body = await request.body()
        result = await server.process(body, ctx)
        
        if isinstance(result, StreamingResult):
            return StreamingResponse(result, media_type="text/event-stream")
        else:
            return Response(content=result.json, media_type="application/json")
            
    except Exception as e:
        print(f"Error processing request: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/upload")
async def upload_file(file: UploadFile, ctx: RequestContext = Depends(get_user)):
    file_id = f"file_{uuid4().hex}"
    ext = Path(file.filename).suffix
    safe_filename = f"{file_id}{ext}"
    file_path = UPLOAD_DIR / safe_filename
    
    # Non-blocking file write
    async with aiofiles.open(file_path, "wb") as f:
        while content := await file.read(1024 * 1024):  # Read in 1MB chunks
            await f.write(content)
        
    is_image = file.content_type.startswith("image/")
    
    if is_image:
        # Non-blocking read for preview generation
        async with aiofiles.open(file_path, "rb") as f:
            file_bytes = await f.read()
            b64_data = base64.b64encode(file_bytes).decode("utf-8")
            preview_data_url = f"data:{file.content_type};base64,{b64_data}"
            
        attachment = ImageAttachment(
            type="image", 
            id=file_id, 
            name=file.filename,
            mime_type=file.content_type, 
            preview_url=preview_data_url, 
            url=f"http://localhost:8000/files/{safe_filename}"
        )
    else:
        attachment = FileAttachment(
            type="file", 
            id=file_id, 
            name=file.filename,
            mime_type=file.content_type, 
            url=f"http://localhost:8000/files/{safe_filename}"
        )
        
    await store.save_attachment(attachment, ctx)
    return attachment.model_dump(mode="json")

app.mount("/files", StaticFiles(directory=UPLOAD_DIR), name="files")
app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    # Workers=1 is fine for async, but ensure reload is off in actual production
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)