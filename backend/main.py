import uuid
import os
import asyncio
import logging
from functools import partial
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from video_fetcher import fetch_video_data
from rag_engine import rag_engine

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Video RAG Chatbot API", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global state
current_videos: dict = {}


from typing import Optional, List

class VideoDataInput(BaseModel):
    title: str
    creator: str
    views: int
    likes: int
    comments: int
    followers: int
    engagement_rate: float
    duration: int
    upload_date: str
    hashtags: List[str] = []
    platform: str
    hook_first_5s: str = ""
    transcript: str = ""

class IngestRequest(BaseModel):
    """Request model for video ingestion."""
    url_a: str
    url_b: str
    api_key: str
    video_a_custom: Optional[VideoDataInput] = None
    video_b_custom: Optional[VideoDataInput] = None


class ChatRequest(BaseModel):
    """Request model for chat messages."""
    question: str
    session_id: str


@app.get("/")
def root():
    """Root endpoint for health check."""
    return {
        "status": "Video RAG Chatbot API is running",
        "version": "1.0.0",
        "endpoints": {
            "ingest": "POST /ingest",
            "chat_stream": "POST /chat/stream",
            "chat_sources": "POST /chat/sources",
            "get_videos": "GET /videos",
            "new_session": "GET /session/new",
            "clear_session": "DELETE /session/{session_id}",
        }
    }


def _build_video_response(video: dict) -> dict:
    """Extract safe response fields from video metadata."""
    return {
        "title": video.get("title", "Unknown"),
        "creator": video.get("creator", "Unknown"),
        "views": video.get("views", 0),
        "likes": video.get("likes", 0),
        "comments": video.get("comments", 0),
        "followers": video.get("followers", 0),
        "engagement_rate": video.get("engagement_rate", 0),
        "engagement_note": video.get("engagement_note"),
        "data_note": video.get("data_note"),
        "duration": video.get("duration", 0),
        "upload_date": video.get("upload_date", "Unknown"),
        "hashtags": video.get("hashtags", []),
        "platform": video.get("platform", "unknown"),
        "hook_first_5s": video.get("hook_first_5s", "N/A"),
        "description": video.get("description", ""),
        "isCustom": video.get("isCustom", False),
    }


def _model_to_dict(model) -> Optional[dict]:
    """Convert model to dictionary safely."""
    if not model:
        return None
    return model.model_dump() if hasattr(model, "model_dump") else model.dict()


def _ingest_videos_sync(
    url_a: str,
    url_b: str,
    api_key: str,
    video_a_custom: Optional[dict] = None,
    video_b_custom: Optional[dict] = None,
) -> dict:
    """Blocking ingest work — run in a thread pool from the async endpoint."""
    if not url_a or not url_a.strip():
        raise ValueError("Video A URL is required")
    if not url_b or not url_b.strip():
        raise ValueError("Video B URL is required")
    # Fallback to server environment key if none is provided in the payload
    resolved_api_key = api_key.strip() if api_key else ""
    if not resolved_api_key:
        resolved_api_key = os.getenv("GEMINI_API_KEY", "").strip()
        
    if not resolved_api_key:
        raise ValueError("Gemini API key is required. Enter it in the UI or configure GEMINI_API_KEY on the server.")

    logger.info(f"Starting ingestion for URLs: {url_a[:50]}... and {url_b[:50]}...")

    try:
        if video_a_custom:
            video_a = video_a_custom
            video_a["label"] = "A"
        else:
            video_a = fetch_video_data(url_a, "A")
        logger.info(f"✓ Video A fetched/provided: {video_a.get('title', 'Unknown')}")
    except Exception as e:
        logger.error(f"Error fetching video A: {str(e)}")
        raise ValueError(f"Failed to fetch Video A: {str(e)[:100]}")

    try:
        if video_b_custom:
            video_b = video_b_custom
            video_b["label"] = "B"
        else:
            video_b = fetch_video_data(url_b, "B")
        logger.info(f"✓ Video B fetched/provided: {video_b.get('title', 'Unknown')}")
    except Exception as e:
        logger.error(f"Error fetching video B: {str(e)}")
        raise ValueError(f"Failed to fetch Video B: {str(e)[:100]}")

    success = rag_engine.ingest_videos(video_a, video_b, resolved_api_key)
    if not success:
        error_msg = rag_engine.last_error or "Unknown ingestion error"
        logger.error(f"RAG ingestion failed: {error_msg}")
        raise ValueError(error_msg)

    logger.info("✓ Videos successfully ingested into RAG engine")
    current_videos["A"] = video_a
    current_videos["B"] = video_b

    response = {
        "status": "success",
        "message": "Videos loaded and indexed successfully",
        "video_a": _build_video_response(video_a),
        "video_b": _build_video_response(video_b),
    }
    logger.info("✓ Ingest request completed successfully")
    return response


@app.post("/ingest")
async def ingest_videos(req: IngestRequest):
    """
    Ingest two videos (YouTube + Instagram) and prepare RAG system.

    Video fetching and embedding are CPU/network-bound, so they run in a
    thread pool to avoid blocking the event loop.
    """
    try:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            partial(
                _ingest_videos_sync,
                req.url_a,
                req.url_b,
                req.api_key,
                _model_to_dict(req.video_a_custom),
                _model_to_dict(req.video_b_custom),
            ),
        )
    except ValueError as e:
        logger.warning(f"Validation error in ingest: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in ingest: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"An unexpected error occurred: {str(e)[:100]}",
        )


@app.get("/videos")
def get_videos():
    """Get currently loaded videos."""
    try:
        if not current_videos or not current_videos.get("A") or not current_videos.get("B"):
            raise HTTPException(
                status_code=404,
                detail="No videos loaded. Please use /ingest to load videos first."
            )
        return current_videos
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting videos: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve videos")


@app.post("/chat/stream")
def chat_stream(req: ChatRequest):
    """Stream RAG response for a question about the videos."""
    try:
        if not current_videos.get("A") or not current_videos.get("B"):
            raise HTTPException(
                status_code=400,
                detail="Please ingest videos first using /ingest endpoint"
            )

        if not req.question or not req.question.strip():
            raise HTTPException(status_code=400, detail="Question cannot be empty")

        if not req.session_id or not req.session_id.strip():
            raise HTTPException(status_code=400, detail="Session ID is required")

        logger.info(f"Streaming response for question: {req.question[:50]}...")

        def generate():
            """Generator function for streaming responses."""
            try:
                for token in rag_engine.chat_stream(req.question, req.session_id):
                    if token:
                        yield token
                logger.info("✓ Stream completed successfully")
            except Exception as e:
                logger.error(f"Error during streaming: {str(e)}")
                yield f"\n\n⚠️ Error: {str(e)[:100]}"

        return StreamingResponse(generate(), media_type="text/plain")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in chat_stream: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Streaming error: {str(e)[:100]}"
        )


@app.post("/chat/sources")
def chat_sources(req: ChatRequest):
    """Get source documents for a question."""
    try:
        if not req.question or not req.question.strip():
            return {"sources": []}

        sources = rag_engine.get_source_docs(req.question)
        return {"sources": sources}

    except Exception as e:
        logger.error(f"Error getting sources: {str(e)}")
        return {"sources": [], "error": str(e)[:100]}


@app.get("/session/new")
def new_session():
    """Generate a new session ID for conversation history."""
    try:
        session_id = str(uuid.uuid4())
        logger.info(f"New session created: {session_id}")
        return {"session_id": session_id}
    except Exception as e:
        logger.error(f"Error creating session: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to create session")


@app.delete("/session/{session_id}")
def clear_session(session_id: str):
    """Clear session history."""
    try:
        from rag_engine import session_store

        if not session_id or not session_id.strip():
            raise HTTPException(status_code=400, detail="Session ID is required")

        if session_id in session_store:
            del session_store[session_id]
            logger.info(f"Session cleared: {session_id}")

        return {"status": "cleared", "session_id": session_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error clearing session: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to clear session")


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "Video RAG Chatbot API",
        "videos_loaded": bool(current_videos.get("A") and current_videos.get("B")),
    }


