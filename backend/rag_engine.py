import os
import google.generativeai as genai
from typing import List, Generator
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain.schema import Document
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.chains import create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_community.chat_message_histories import ChatMessageHistory

# Session store
session_store: dict = {}

def get_session_history(session_id: str) -> ChatMessageHistory:
    if session_id not in session_store:
        session_store[session_id] = ChatMessageHistory()
    return session_store[session_id]


class RAGEngine:
    def __init__(self):
        # Lazy init — don't call Gemini at startup
        self.embeddings = None
        self.llm = None
        self.vectorstore = None
        self.retriever = None
        self.chain_with_history = None
        self.video_metadata = {}

    def _init_models(self, api_key: str):
        """Initialize Gemini models only when needed."""
        os.environ["GOOGLE_API_KEY"] = api_key
        genai.configure(api_key=api_key)
        self.embeddings = GoogleGenerativeAIEmbeddings(
            model="models/embedding-001",
            google_api_key=api_key,
        )
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-1.5-flash",
            google_api_key=api_key,
            temperature=0.3,
            streaming=True,
        )

    def ingest_videos(self, video_a: dict, video_b: dict, api_key: str):
        self._init_models(api_key)
        self.video_metadata = {"A": video_a, "B": video_b}

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=50,
        )

        docs: List[Document] = []

        for video in [video_a, video_b]:
            label = video["label"]
            transcript = video.get("transcript", "") or ""
            if not transcript or "not available" in transcript.lower():
                transcript = f"No transcript available for video {label}."

            chunks = splitter.split_text(transcript)
            for i, chunk in enumerate(chunks):
                docs.append(Document(
                    page_content=chunk,
                    metadata={
                        "video_id": label,
                        "platform": video.get("platform", "unknown"),
                        "creator": video.get("creator", "Unknown"),
                        "title": video.get("title", "Unknown"),
                        "source": f"Video {label} - chunk {i}",
                    }
                ))

            # Metadata summary doc
            meta_summary = f"""Video {label} Metadata:
Title: {video.get('title', 'N/A')}
Creator: {video.get('creator', 'N/A')}
Platform: {video.get('platform', 'N/A')}
Followers: {video.get('followers', 0):,}
Views: {video.get('views', 0):,}
Likes: {video.get('likes', 0):,}
Comments: {video.get('comments', 0):,}
Engagement Rate: {video.get('engagement_rate', 0)}%
Upload Date: {video.get('upload_date', 'N/A')}
Duration: {video.get('duration', 0)} seconds
Hashtags: {', '.join(video.get('hashtags', []))}
Hook (first 5s): {video.get('hook_first_5s', 'N/A')}""".strip()

            docs.append(Document(
                page_content=meta_summary,
                metadata={
                    "video_id": label,
                    "platform": video.get("platform", "unknown"),
                    "creator": video.get("creator", "Unknown"),
                    "title": video.get("title", "Unknown"),
                    "source": f"Video {label} - metadata",
                }
            ))

        self.vectorstore = Chroma.from_documents(
            documents=docs,
            embedding=self.embeddings,
            collection_name="video_rag",
        )
        self.retriever = self.vectorstore.as_retriever(
            search_type="similarity",
            search_kwargs={"k": 6},
        )
        self._build_chain()

    def _build_chain(self):
        system_prompt = """You are an expert social media analyst and content strategist.
You are analyzing two videos (Video A and Video B) for a creator.

Use ONLY the context provided to answer. Always cite which video your answer comes from.
Be specific with numbers (views, likes, engagement rates).
When suggesting improvements, be actionable.

Context:
{context}

Rules:
- Always cite sources as [Video A - metadata] or [Video B - chunk N]
- If data is missing, say so clearly
- Be concise but insightful
"""
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
        ])
        combine_docs_chain = create_stuff_documents_chain(self.llm, prompt)
        chain = create_retrieval_chain(self.retriever, combine_docs_chain)
        self.chain_with_history = RunnableWithMessageHistory(
            chain,
            get_session_history,
            input_messages_key="input",
            history_messages_key="chat_history",
            output_messages_key="answer",
        )

    def chat_stream(self, question: str, session_id: str) -> Generator:
        if not self.chain_with_history:
            yield "Error: Please ingest videos first."
            return
        config = {"configurable": {"session_id": session_id}}
        for chunk in self.chain_with_history.stream({"input": question}, config=config):
            if "answer" in chunk:
                yield chunk["answer"]

    def get_source_docs(self, question: str) -> list:
        if not self.retriever:
            return []
        docs = self.retriever.get_relevant_documents(question)
        return [
            {
                "source": d.metadata.get("source", "unknown"),
                "video_id": d.metadata.get("video_id", "?"),
                "content_preview": d.page_content[:150] + "...",
            }
            for d in docs
        ]


rag_engine = RAGEngine()