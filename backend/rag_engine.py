import os
import logging
from typing import List, Generator
from dotenv import load_dotenv

# Load environment variables FIRST
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Check API key exists
API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    logger.warning("⚠️ GEMINI_API_KEY not found in .env file! The application will require an API key to be supplied dynamically via the UI.")
else:
    logger.info(f"✅ API Key loaded: {API_KEY[:20]}...")

# Import after env is loaded
try:
    import google.generativeai as genai
    from langchain.text_splitter import RecursiveCharacterTextSplitter
    from langchain_community.vectorstores import Chroma
    from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
    from langchain.schema import Document
    from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
    from langchain.chains import create_retrieval_chain
    from langchain.chains.combine_documents import create_stuff_documents_chain
    from langchain_core.runnables.history import RunnableWithMessageHistory
    from langchain_community.chat_message_histories import ChatMessageHistory
    logger.info("✅ All imports successful")
except ImportError as e:
    logger.error(f"❌ Import error: {e}")
    raise

# Session store
session_store: dict = {}


def get_session_history(session_id: str) -> ChatMessageHistory:
    """Get or create session history for conversation memory."""
    if session_id not in session_store:
        session_store[session_id] = ChatMessageHistory()
    return session_store[session_id]


class RAGEngine:
    def __init__(self):
        """Initialize RAG Engine with lazy model loading."""
        self.embeddings = None
        self.llm = None
        self.vectorstore = None
        self.retriever = None
        self.chain_with_history = None
        self.video_metadata = {}
        self.last_error = None

    def _init_models(self, api_key: str) -> bool:
        """Initialize Gemini models with error handling."""
        try:
            api_key = str(api_key).strip()
            if not api_key:
                self.last_error = "Invalid API key: API key cannot be empty"
                logger.error(self.last_error)
                return False

            logger.info("🔑 Setting up Gemini API...")

            # Configure directly without pydantic issues
            os.environ["GOOGLE_API_KEY"] = api_key
            os.environ["GEMINI_API_KEY"] = api_key
            genai.configure(api_key=api_key)
            
            logger.info("Testing embeddings model (this may take a moment)...")
            try:
                # Test with simple text
                self.embeddings = GoogleGenerativeAIEmbeddings(
                    model="models/gemini-embedding-001",
                    task_type="RETRIEVAL_DOCUMENT",
                )

                test_result = self.embeddings.embed_query("test")
                logger.info(f"✅ Embeddings ready! Dimension: {len(test_result)}")

            except Exception as e:
                error_msg = str(e)
                logger.error(f"❌ Embedding failed: {error_msg}")

                if "SecretStr" in error_msg:
                    self.last_error = "API key configuration error. Please re-enter your Gemini API key."
                elif "504" in error_msg or "Deadline" in error_msg:
                    self.last_error = "Google API timeout. Wait 30 seconds and try again."
                elif "API key" in error_msg or "403" in error_msg or "401" in error_msg:
                    self.last_error = "Invalid API key. Get a free key at https://aistudio.google.com"
                elif "429" in error_msg or "quota" in error_msg.lower():
                    self.last_error = "Gemini API rate limit reached. Wait a minute and try again."
                else:
                    self.last_error = f"Embedding error: {error_msg[:100]}"

                logger.error(self.last_error)
                return False

            llm_model = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")
            logger.info(f"Initializing LLM ({llm_model})...")
            self.llm = ChatGoogleGenerativeAI(
                model=llm_model,
                temperature=0.3,
                streaming=True,
                max_retries=2,
                timeout=120,
            )
            logger.info("✅ LLM ready")
            return True

        except Exception as e:
            self.last_error = f"Model setup failed: {str(e)[:100]}"
            logger.error(self.last_error)
            return False

    def ingest_videos(self, video_a: dict, video_b: dict, api_key: str) -> bool:
        """Ingest videos with comprehensive error handling."""
        try:
            logger.info("=" * 70)
            logger.info("STARTING VIDEO INGESTION")
            logger.info("=" * 70)
            
            # Initialize models
            if not self._init_models(api_key):
                logger.error(f"Failed: {self.last_error}")
                raise Exception(self.last_error or "Failed to initialize AI models")

            self.video_metadata = {"A": video_a, "B": video_b}

            # Validate video data
            if not video_a or not video_b:
                self.last_error = "Invalid video data"
                raise Exception(self.last_error)

            logger.info(f"Video A: {video_a.get('title', 'Unknown')[:50]}")
            logger.info(f"Video B: {video_b.get('title', 'Unknown')[:50]}")

            # Create text splitter
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=500,
                chunk_overlap=50,
            )

            docs: List[Document] = []

            # Authoritative metrics doc (single source of truth for numbers)
            docs.append(Document(
                page_content=self._build_metrics_summary(),
                metadata={
                    "video_id": "both",
                    "doc_type": "authoritative_metrics",
                    "source": "Official Video Metrics Summary",
                },
            ))

            # Process each video — transcript chunks only (metrics live in summary above)
            for video in [video_a, video_b]:
                try:
                    label = video.get("label", "Unknown")
                    transcript = video.get("transcript", "") or ""

                    if not transcript or len(transcript.strip()) < 10:
                        transcript = (
                            f"Video {label}: {video.get('title', 'N/A')} "
                            f"by {video.get('creator', 'N/A')}"
                        )

                    chunks = splitter.split_text(transcript) or [transcript]
                    for chunk in chunks:
                        if chunk.strip():
                            docs.append(Document(
                                page_content=chunk,
                                metadata={
                                    "video_id": label,
                                    "platform": video.get("platform", "unknown"),
                                    "creator": video.get("creator", "Unknown"),
                                    "title": video.get("title", "Unknown"),
                                    "source": f"Video {label} — Transcript",
                                },
                            ))

                except Exception as e:
                    logger.warning(f"Error processing video {label}: {e}")

            if not docs:
                self.last_error = "No documents created from videos"
                raise Exception(self.last_error)

            logger.info(f"📄 Created {len(docs)} documents")

            # Create vector store
            logger.info("Creating vector store...")
            self.vectorstore = Chroma.from_documents(
                documents=docs,
                embedding=self.embeddings,
                collection_name="video_rag",
            )
            logger.info("✅ Vector store ready")

            # Create retriever
            self.retriever = self.vectorstore.as_retriever(
                search_type="similarity",
                search_kwargs={"k": 8},
            )

            # Build chain
            self._build_chain()

            logger.info("=" * 70)
            logger.info("✅ INGESTION COMPLETE - READY FOR ANALYSIS")
            logger.info("=" * 70)
            return True

        except Exception as e:
            self.last_error = str(e)
            logger.error(f"❌ INGESTION FAILED: {self.last_error}")
            return False

    def _build_metrics_summary(self) -> str:
        """Build a single authoritative metrics block for both videos."""
        lines = ["=== OFFICIAL VIDEO METRICS (use these exact numbers) ==="]
        for label in ("A", "B"):
            video = self.video_metadata.get(label, {})
            engagement = video.get("engagement_rate", 0)
            engagement_line = f"{engagement}%"
            if video.get("engagement_note"):
                engagement_line = video["engagement_note"]
            elif video.get("views", 0) == 0 and video.get("likes", 0) > 0:
                engagement_line = (
                    f"{video.get('likes', 0):,} likes, {video.get('comments', 0):,} comments "
                    "(view count not available)"
                )

            lines.append(f"""
Video {label} ({video.get('platform', 'unknown').upper()}):
  Title: {video.get('title', 'N/A')}
  Creator: @{video.get('creator', 'Unknown')} ({video.get('followers', 0):,} followers)
  Views: {video.get('views', 0):,} | Likes: {video.get('likes', 0):,} | Comments: {video.get('comments', 0):,}
  Engagement: {engagement_line}
  Duration: {video.get('duration', 0)}s
  Hook (first 5s): {(video.get('hook_first_5s') or 'N/A')[:150]}
  Caption/Description: {(video.get('description') or 'N/A')[:200]}""".strip())

            if video.get("data_note"):
                lines.append(f"  Note: {video['data_note']}")

        lines.append("=== END METRICS ===")
        return "\n".join(lines)

    def _build_chain(self):
        """Build RAG chain."""
        try:
            if not self.llm or not self.retriever:
                raise Exception("LLM or Retriever not initialized")

            system_prompt = """You are an expert social media video analyst comparing Video A and Video B.

Rules:
1. ALWAYS address BOTH Video A and Video B when the question compares them or asks about "each" video.
2. Use the OFFICIAL VIDEO METRICS section for all numbers — report ONE engagement value per video, never list duplicates.
3. For Instagram (Video B), view counts are often hidden — report likes and comments instead of inventing a rate.
4. If data is missing or zero, say so clearly rather than guessing.
5. Be concise, structured (use bullet points), and cite Video A or Video B by name.
6. For engagement rate questions: give one line per video with the official metric or note.

Context:
{context}"""

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
            logger.info("✅ Chain built")

        except Exception as e:
            logger.error(f"Chain error: {e}")
            raise

    def chat_stream(self, question: str, session_id: str) -> Generator:
        """Stream RAG responses with authoritative metrics injected."""
        try:
            if not self.chain_with_history:
                yield "Error: Videos not loaded yet"
                return

            logger.info(f"💬 Question: {question[:50]}")
            metrics = self._build_metrics_summary()
            augmented = (
                f"{metrics}\n\n"
                f"User question: {question}\n"
                "Remember: answer for BOTH videos when relevant. Use one engagement value per video."
            )
            config = {"configurable": {"session_id": session_id}}

            for chunk in self.chain_with_history.stream({"input": augmented}, config=config):
                if "answer" in chunk:
                    yield chunk["answer"]

        except Exception as e:
            logger.error(f"Stream error: {e}")
            error_msg = str(e)
            if "429" in error_msg or "quota" in error_msg.lower():
                yield "⚠️ Gemini API rate limit reached. Please wait a minute and try again."
            else:
                yield f"⚠️ Error: {error_msg[:150]}"

    def get_source_docs(self, question: str) -> list:
        """Get source documents."""
        try:
            if not self.retriever:
                return []
            docs = self.retriever.get_relevant_documents(question)
            return [
                {
                    "source": d.metadata.get("source", "unknown"),
                    "video_id": d.metadata.get("video_id", "?"),
                }
                for d in docs
            ]
        except Exception as e:
            logger.error(f"Source error: {e}")
            return []


# Global instance
rag_engine = RAGEngine()
