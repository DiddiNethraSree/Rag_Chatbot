# 🎬 Video RAG Analyst

A full-stack RAG (Retrieval-Augmented Generation) chatbot application to ingest, compare, and analyze YouTube videos and Instagram Reels side-by-side.

🔗 **Live Frontend Demo:** [https://rag-chatbot-phi-six.vercel.app/](https://rag-chatbot-phi-six.vercel.app/)  
🔗 **Live Backend API:** [https://rag-chatbot-backend-4tkb.onrender.com/](https://rag-chatbot-backend-4tkb.onrender.com/)

---

## ✨ Features

- **Cross-Platform Ingestion**: Scrapes video transcripts and metadata from YouTube and Instagram Reels.
- **RAG Chatbot**: Utilizes LangChain and Google's Gemini AI (`gemini-embedding-001` & `gemini-flash-lite-latest`) for precise comparative analysis.
- **Vector Search**: Automatically chunks, embeds, and stores video contexts in ChromaDB for semantic retrieval.
- **Data Overrides**: Includes an interactive modal to edit or input metrics manually if automated scraping is blocked.
- **Premium UI**: Modern, fully responsive dark-mode dashboard with real-time markdown streaming and source citations.

---

## 🛠️ Tech Stack

- **Backend**: FastAPI, Python, Uvicorn, yt-dlp
- **RAG Engine**: LangChain, ChromaDB, Google Generative AI (Gemini)
- **Frontend**: React.js, CSS Grid & Flexbox

---

## 🚀 Quick Start (Local Setup)

### 1. Backend Setup
```bash
cd backend
pip install -r requirements.txt
```
Create a `.env` file in the `backend/` folder:
```env
GEMINI_API_KEY=your_gemini_api_key
SERVER_PORT=8000
SERVER_HOST=127.0.0.1
```
Run the backend server:
```bash
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

### 2. Frontend Setup
```bash
cd frontend
npm install
npm start
```
The application will open automatically at `http://localhost:3000`.
