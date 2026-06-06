import os
import google.generativeai as genai
import logging
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

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
            if not api_key or not isinstance(api_key, str) or len(api_key.strip()) == 0:
                self.last_error = "Invalid API key: API key cannot be empty"
                logger.error(self.last_error)
                return False

            os.environ["GOOGLE_API_KEY"] = api_key
            genai.configure(api_key=api_key)
            
            # Test API key validity by making a simple call
            try:
                self.embeddings = GoogleGenerativeAIEmbeddings(
                    model="models/embedding-001",
                    google_api_key=api_key,
                )
                # Test the embedding model
                self.embeddings.embed_query("test")
                logger.info("✓ Gemini Embeddings initialized successfully")
            except Exception as e:
                error_msg = str(e)
                if "API key not valid" in error_msg or "403" in error_msg:
                    self.last_error = "Invalid Gemini API key. Get a free key at https://aistudio.google.com"
                else:
                    self.last_error = f"Embedding model error: {error_msg[:100]}"
                logger.error(self.last_error)
                return False

            self.llm = ChatGoogleGenerativeAI(
                model="gemini-1.5-flash",
                google_api_key=api_key,
                temperature=0.3,
                streaming=True,
                max_retries=2,
            )
            logger.info("✓ Gemini LLM initialized successfully")
            return True

        except Exception as e:
            self.last_error = f"Model initialization failed: {str(e)[:100]}"
            logger.error(self.last_error)
            return False

    def ingest_videos(self, video_a: dict, video_b: dict, api_key: str) -> bool:
        """Ingest videos with comprehensive error handling."""
        try:
            # Initialize models with validation
            if not self._init_models(api_key):
                logger.error(f"Failed to initialize models: {self.last_error}")
                raise Exception(self.last_error or "Failed to initialize AI models")

            self.video_metadata = {"A": video_a, "B": video_b}

            # Validate video data
            if not video_a or not video_b:
                self.last_error = "Invalid video data received"
                logger.error(self.last_error)
                raise Exception(self.last_error)

            # Check for errors in video fetching
            errors = []
            if video_a.get("error"):
                errors.append(f"Video A: {video_a['error']}")
            if video_b.get("error"):
                errors.append(f"Video B: {video_b['error']}")

            if errors:
                logger.warning(f"Video fetch issues: {', '.join(errors)}")
                # Continue anyway - we have partial data

            # Create text splitter
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=500,
                chunk_overlap=50,
            )

            docs: List[Document] = []

            # Process each video
            for video in [video_a, video_b]:
                try:
                    label = video.get("label", "Unknown")
                    transcript = video.get("transcript", "") or ""
                    
                    # Ensure transcript has content
                    if not transcript or len(transcript.strip()) < 10:
                        transcript = f"No detailed transcript available for video {label}. "
                        transcript += f"Title: {video.get('title', 'N/A')}. "
                        transcript += f"Creator: {video.get('creator', 'N/A')}"
                    
                    # Split transcript into chunks
                    try:
                        chunks = splitter.split_text(transcript)
                        if not chunks:
                            chunks = [transcript]  # Fallback if splitting produces empty list
                    except Exception as e:
                        logger.warning(f"Text splitting error for video {label}: {str(e)}")
                        chunks = [transcript]

                    # Add transcript chunks
                    for i, chunk in enumerate(chunks):
                        if chunk.strip():  # Only add non-empty chunks
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

                    # Create metadata summary document
                    try:
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
                    except Exception as e:
                        logger.warning(f"Metadata document creation error for video {label}: {str(e)}")

                except Exception as e:
                    logger.error(f"Error processing video {label}: {str(e)}")
                    # Continue to next video

            # Validate that we have documents
            if not docs:
                self.last_error = "No documents could be created from video data"
                logger.error(self.last_error)
                raise Exception(self.last_error)

            # Create vector store
            try:
                self.vectorstore = Chroma.from_documents(
                    documents=docs,
                    embedding=self.embeddings,
                    collection_name="video_rag",
                )
                logger.info(f"✓ Vector store created with {len(docs)} documents")
            except Exception as e:
                self.last_error = f"Vector store creation failed: {str(e)[:100]}"
                logger.error(self.last_error)
                raise Exception(self.last_error)

            # Create retriever
            try:
                self.retriever = self.vectorstore.as_retriever(
                    search_type="similarity",
                    search_kwargs={"k": 6},
                )
                logger.info("✓ Retriever created")
            except Exception as e:
                self.last_error = f"Retriever creation failed: {str(e)[:100]}"
                logger.error(self.last_error)
                raise Exception(self.last_error)

            # Build RAG chain
            try:
                self._build_chain()
                logger.info("✓ RAG chain built successfully")
            except Exception as e:
                self.last_error = f"Chain building failed: {str(e)[:100]}"
                logger.error(self.last_error)
                raise Exception(self.last_error)

            return True

        except Exception as e:
            self.last_error = str(e)
            logger.error(f"Ingest failed: {self.last_error}")
            return False

    def _build_chain(self):
        """Build LangChain RAG chain with error handling."""
        try:
            if not self.llm or not self.retriever:
                raise Exception("LLM or Retriever not initialized")

            system_prompt = """You are an expert social media analyst and content strategist.
You are analyzing two videos (Video A and Video B) for a creator.

Use ONLY the context provided to answer. Always cite which video your answer comes from.
Be specific with numbers (views, likes, engagement rates).
When suggesting improvements, be actionable and specific.

Context:
{context}

Rules:
- Always cite sources as [Video A - metadata] or [Video B - chunk N]
- If data is missing, say so clearly
- Be concise but insightful
- Focus on actionable insights
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
            logger.info("✓ RAG chain with history created")

        except Exception as e:
            logger.error(f"Chain building error: {str(e)}")
            raise Exception(f"Failed to build RAG chain: {str(e)[:100]}")

    def chat_stream(self, question: str, session_id: str) -> Generator:
        """Stream RAG responses with error handling."""
        try:
            if not self.chain_with_history:
                error_msg = "Videos not ingested yet. Please analyze videos first."
                logger.warning(error_msg)
                yield error_msg
                return

            if not question or len(question.strip()) == 0:
                yield "Error: Please ask a valid question."
                return

            config = {"configurable": {"session_id": session_id}}
            
            try:
                for chunk in self.chain_with_history.stream({"input": question}, config=config):
                    if "answer" in chunk:
                        yield chunk["answer"]
            except Exception as e:
                error_msg = f"Error generating response: {str(e)[:100]}"
                logger.error(error_msg)
                yield error_msg

        except Exception as e:
            error_msg = f"Streaming error: {str(e)[:100]}"
            logger.error(error_msg)
            yield error_msg

    def get_source_docs(self, question: str) -> list:
        """Get source documents with error handling."""
        try:
            if not self.retriever or not question:
                return []

            docs = self.retriever.get_relevant_documents(question)
            return [
                {
                    "source": d.metadata.get("source", "unknown"),
                    "video_id": d.metadata.get("video_id", "?"),
                    "content_preview": (d.page_content[:150] + "...") if len(d.page_content) > 150 else d.page_content,
                }
                for d in docs
            ]

        except Exception as e:
            logger.error(f"Source retrieval error: {str(e)}")
            return []


# Global RAG engine instance
rag_engine = RAGEngine()
