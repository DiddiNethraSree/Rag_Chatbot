import uuid
import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from video_fetcher import fetch_video_data
from rag_engine import rag_engine
 
app = FastAPI(title="Video RAG Chatbot API")
 
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
 
current_videos: dict = {}
 
 
class IngestRequest(BaseModel):
    url_a: str
    url_b: str
    api_key: str  # passed from frontend directly
 
 
class ChatRequest(BaseModel):
    question: str
    session_id: str
 
 
@app.get("/")
def root():
    return {"status": "Video RAG Chatbot API is running"}
 
 
@app.post("/ingest")
async def ingest_videos(req: IngestRequest):
    try:
        video_a = fetch_video_data(req.url_a, "A")
        video_b = fetch_video_data(req.url_b, "B")
        rag_engine.ingest_videos(video_a, video_b, req.api_key)
        current_videos["A"] = video_a
        current_videos["B"] = video_b
        return {
            "status": "success",
            "video_a": {k: video_a[k] for k in ["title","creator","views","likes","comments","followers","engagement_rate","duration","upload_date","hashtags","platform","hook_first_5s"]},
            "video_b": {k: video_b[k] for k in ["title","creator","views","likes","comments","followers","engagement_rate","duration","upload_date","hashtags","platform","hook_first_5s"]},
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
 
 
@app.get("/videos")
def get_videos():
    if not current_videos:
        raise HTTPException(status_code=404, detail="No videos ingested yet.")
    return current_videos
 
 
@app.post("/chat/stream")
def chat_stream(req: ChatRequest):
    if not current_videos:
        raise HTTPException(status_code=400, detail="Please ingest videos first.")
    def generate():
        for token in rag_engine.chat_stream(req.question, req.session_id):
            yield token
    return StreamingResponse(generate(), media_type="text/plain")
 
 
@app.post("/chat/sources")
def chat_sources(req: ChatRequest):
    sources = rag_engine.get_source_docs(req.question)
    return {"sources": sources}
 
 
@app.get("/session/new")
def new_session():
    return {"session_id": str(uuid.uuid4())}
 
 
@app.delete("/session/{session_id}")
def clear_session(session_id: str):
    from rag_engine import session_store
    if session_id in session_store:
        del session_store[session_id]
    return {"status": "cleared"}