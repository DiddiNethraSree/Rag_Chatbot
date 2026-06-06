# 🎬 Video RAG Analyst

A full-stack RAG chatbot that compares two social media videos (YouTube + Instagram) using LangChain, ChromaDB, and Gemini AI — with streaming responses, memory, and source citations.

## Architecture

```
Frontend (React)  →  FastAPI Backend  →  LangChain RAG
                                              ↓
                                     ChromaDB (vector store)
                                              ↓
                                     Gemini 1.5 Flash (LLM)
                                     Gemini Embeddings (embedding-001)
```

## Tech Stack

| Layer | Choice | Why |
|---|---|---|
| Frontend | React 18 | Fast, component-based UI with streaming support |
| Backend | FastAPI | Async support, automatic OpenAPI docs, streaming |
| Orchestration | LangChain | RunnableWithMessageHistory for memory, retrieval chain |
| Embeddings | Gemini embedding-001 | Free, high quality, 768-dim embeddings |
| Vector DB | ChromaDB | In-memory, zero infra cost, fast similarity search |
| LLM | Gemini 1.5 Flash | Free tier, fast, 1M context window |
| Transcripts | youtube-transcript-api + yt-dlp | Free, no API key needed |

## Cost & Scalability Analysis

**Why this stack is optimal for 1000 creators/day:**

- **Gemini Flash** = ~$0.075/1M input tokens (vs GPT-4o at $5/1M) — 66x cheaper
- **ChromaDB in-memory** = $0 vector storage cost per session
- **youtube-transcript-api** = free, no rate limits for standard use
- **Chunking strategy**: 500-char chunks with 50-char overlap — tested optimal for transcript retrieval without semantic drift

**Bottleneck at scale**: ChromaDB in-memory resets on restart. For production at 1000/day, swap to **Qdrant Cloud** (free tier: 1GB) or **Pinecone Serverless** (pay per query, ~$0.001/query). This keeps costs under $1/day for 1000 users.

**Better alternative at true scale**: Replace yt-dlp metadata with YouTube Data API v3 (10,000 free quota/day) for more reliable likes/comments data — Instagram metadata is limited due to platform restrictions.

## Setup

### Prerequisites
- Python 3.10+
- Node.js 18+
- Gemini API key (free at https://aistudio.google.com)

### Backend

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
# Add your GEMINI_API_KEY to .env
uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm start
# Opens at http://localhost:3000
```

## How It Works

1. User pastes YouTube URL (Video A) + Instagram Reel URL (Video B)
2. Backend fetches transcripts via `youtube-transcript-api` / `yt-dlp`
3. Metadata (views, likes, comments, followers) fetched via `yt-dlp --dump-json`
4. Engagement rate computed: `(likes + comments) / views × 100`
5. Transcripts chunked (500 chars, 50 overlap) → embedded via Gemini → stored in ChromaDB
6. Metadata summaries also embedded as separate documents
7. RAG chain (LangChain) retrieves top-6 chunks per query
8. Gemini 1.5 Flash streams response with source citations
9. Memory maintained via `RunnableWithMessageHistory` (per session UUID)

## Chunk Size Decision

500-char chunks chosen because:
- Transcript sentences average 80-120 chars
- 500 chars ≈ 4-5 sentences → enough context for semantic meaning
- Too large (>1000) = irrelevant context bleeds in; too small (<200) = loses sentence context
- 50-char overlap prevents context loss at boundaries

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | /ingest | Fetch videos, embed, store in ChromaDB |
| POST | /chat/stream | Stream RAG response |
| POST | /chat/sources | Get source chunks for a query |
| GET | /videos | Get current video metadata |
| GET | /session/new | Generate new session ID |
| DELETE | /session/{id} | Clear chat history |

## Example Questions

- "Why did Video A get more engagement than Video B?"
- "What's the engagement rate of each video?"
- "Compare the hooks in the first 5 seconds."
- "Who's the creator of Video B and what's their follower count?"
- "Suggest improvements for B based on what worked in A."
