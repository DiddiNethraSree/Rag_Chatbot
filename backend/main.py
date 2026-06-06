import uuid
import os
import logging
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


class IngestRequest(BaseModel):
    """Request model for video ingestion."""
    url_a: str
    url_b: str
    api_key: str


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


@app.post("/ingest")
async def ingest_videos(req: IngestRequest):
    """
    Ingest two videos (YouTube + Instagram) and prepare RAG system.
    
    Args:
        req: IngestRequest with url_a, url_b, and api_key
    
    Returns:
        Dictionary with video metadata and status
    """
    try:
        # Validate input
        if not req.url_a or not req.url_a.strip():
            raise ValueError("Video A URL is required")
        if not req.url_b or not req.url_b.strip():
            raise ValueError("Video B URL is required")
        if not req.api_key or not req.api_key.strip():
            raise ValueError("Gemini API key is required")

        logger.info(f"Starting ingestion for URLs: {req.url_a[:50]}... and {req.url_b[:50]}...")

        # Fetch video data
        try:
            video_a = fetch_video_data(req.url_a, "A")
            logger.info(f"✓ Video A fetched: {video_a.get('title', 'Unknown')}")
        except Exception as e:
            logger.error(f"Error fetching video A: {str(e)}")
            raise ValueError(f"Failed to fetch Video A: {str(e)[:100]}")

        try:
            video_b = fetch_video_data(req.url_b, "B")
            logger.info(f"✓ Video B fetched: {video_b.get('title', 'Unknown')}")
        except Exception as e:
            logger.error(f"Error fetching video B: {str(e)}")
            raise ValueError(f"Failed to fetch Video B: {str(e)[:100]}")

        # Ingest into RAG engine
        try:
            success = rag_engine.ingest_videos(video_a, video_b, req.api_key)
            if not success:
                error_msg = rag_engine.last_error or "Unknown ingestion error"
                logger.error(f"RAG ingestion failed: {error_msg}")
                raise ValueError(error_msg)
            logger.info("✓ Videos successfully ingested into RAG engine")
        except Exception as e:
            logger.error(f"RAG ingestion error: {str(e)}")
            raise ValueError(f"Failed to process videos in RAG system: {str(e)[:100]}")

        # Store videos in current session
        current_videos["A"] = video_a
        current_videos["B"] = video_b

        # Prepare response with safe field extraction
        video_a_response = {
            "title": video_a.get("title", "Unknown"),
            "creator": video_a.get("creator", "Unknown"),
            "views": video_a.get("views", 0),
            "likes": video_a.get("likes", 0),
            "comments": video_a.get("comments", 0),
            "followers": video_a.get("followers", 0),
            "engagement_rate": video_a.get("engagement_rate", 0),
            "duration": video_a.get("duration", 0),
            "upload_date": video_a.get("upload_date", "Unknown"),
            "hashtags": video_a.get("hashtags", []),
            "platform": video_a.get("platform", "unknown"),
            "hook_first_5s": video_a.get("hook_first_5s", "N/A"),
        }

        video_b_response = {
            "title": video_b.get("title", "Unknown"),
            "creator": video_b.get("creator", "Unknown"),
            "views": video_b.get("views", 0),
            "likes": video_b.get("likes", 0),
            "comments": video_b.get("comments", 0),
            "followers": video_b.get("followers", 0),
            "engagement_rate": video_b.get("engagement_rate", 0),
            "duration": video_b.get("duration", 0),
            "upload_date": video_b.get("upload_date", "Unknown"),
            "hashtags": video_b.get("hashtags", []),
            "platform": video_b.get("platform", "unknown"),
            "hook_first_5s": video_b.get("hook_first_5s", "N/A"),
        }

        response = {
            "status": "success",
            "message": "Videos loaded and indexed successfully",
            "video_a": video_a_response,
            "video_b": video_b_response,
        }

        logger.info("✓ Ingest request completed successfully")
        return response

    except ValueError as e:
        # Expected validation errors
        logger.warning(f"Validation error in ingest: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Unexpected errors
        logger.error(f"Unexpected error in ingest: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"An unexpected error occurred: {str(e)[:100]}"
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


# Error handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Handle HTTP exceptions."""
    logger.error(f"HTTP error {exc.status_code}: {exc.detail}")
    return {
        "error": exc.detail,
        "status_code": exc.status_code,
    }


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Handle general exceptions."""
    logger.error(f"Unexpected error: {str(exc)}")
    return {
        "error": "An unexpected error occurred. Please try again.",
        "detail": str(exc)[:100],
    }
