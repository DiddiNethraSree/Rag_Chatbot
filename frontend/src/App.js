import React, { useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import "./App.css";

// Backend URL — defaults to 8001 (8000 can get stuck on Windows after crashes)
const API = process.env.REACT_APP_API_URL || "http://localhost:8001";

console.log("🔗 API Endpoint:", API);

function StatBadge({ label, value, icon }) {
  return (
    <div className="stat-badge">
      <span className="stat-icon">{icon}</span>
      <div className="stat-content">
        <span className="stat-label">{label}</span>
        <span className="stat-value">{value}</span>
      </div>
    </div>
  );
}

function VideoCard({ label, data, loading, onEdit }) {
  if (loading) return (
    <div className="video-card loading">
      <div className="spinner"></div>
      <p>⏳ Fetching Video {label}...</p>
    </div>
  );

  if (!data) return (
    <div className="video-card empty">
      <div className="card-label">Video {label}</div>
      <p className="empty-text">📝 Enter URL above to load</p>
    </div>
  );

  const formatNum = (n) => n >= 1000000
    ? (n / 1000000).toFixed(1) + "M"
    : n >= 1000 ? (n / 1000).toFixed(1) + "K" : String(n);

  const platformEmoji = data.platform === "youtube" ? "▶️" : "📷";
  const isInstagramFail = data.platform === "instagram" && data.likes === 0 && data.creator === "Unknown";
  const engagementDisplay = data.engagement_note
    ? data.engagement_note
    : data.views > 0
      ? `${data.engagement_rate}%`
      : data.likes > 0
        ? `${formatNum(data.likes)} likes`
        : "N/A";

  return (
    <div className={`video-card loaded ${label === "A" ? "card-a" : "card-b"} ${data.isCustom ? "custom-edited" : ""}`}>
      <div className="card-header">
        <span className="card-label-badge">{label} {data.isCustom && "(Edited)"}</span>
        <span className="platform-badge">{platformEmoji} {data.platform}</span>
      </div>

      <h3 className="video-title" title={data.title}>{data.title || "Unknown Title"}</h3>
      <p className="creator-name">👤 @{data.creator}</p>

      {isInstagramFail && (
        <div className="scrape-fail-warning">
          <span>⚠️ Could not fetch Instagram data automatically.</span>
          <p>Run <code>pip install -U yt-dlp</code> in the backend folder, or click &quot;Edit Video Data&quot; to enter metrics manually.</p>
        </div>
      )}

      {data.data_note && !isInstagramFail && (
        <div className="scrape-fail-warning mild">
          <span>ℹ️ {data.data_note}</span>
        </div>
      )}

      <div className="stats-grid">
        <StatBadge label="Views" value={(data.views === 0 && data.likes > 0) ? "N/A" : formatNum(data.views)} icon="👁️" />
        <StatBadge label="Likes" value={formatNum(data.likes)} icon="❤️" />
        <StatBadge label="Comments" value={formatNum(data.comments)} icon="💬" />
        <StatBadge label="Followers" value={formatNum(data.followers)} icon="👥" />
        <StatBadge label="Engagement" value={engagementDisplay} icon="🔥" />
        <StatBadge label="Duration" value={`${data.duration}s`} icon="⏱️" />
      </div>

      {data.hook_first_5s && (
        <div className="hook-box">
          <span className="hook-label">⚡ Hook (first 5s)</span>
          <p className="hook-text">{data.hook_first_5s.slice(0, 120)}...</p>
        </div>
      )}

      {data.hashtags?.length > 0 && (
        <div className="hashtags">
          {data.hashtags.slice(0, 5).map((tag, i) => (
            <span key={i} className="hashtag">#{tag}</span>
          ))}
        </div>
      )}

      <button className="edit-video-btn" onClick={() => onEdit(label)}>
        ✏️ Edit Video Data
      </button>
    </div>
  );
}

function ChatMessage({ msg }) {
  const [copied, setCopied] = React.useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(msg.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className={`chat-message ${msg.role}`}>
      <div className="message-header-row">
        <div className="message-role">
          {msg.role === "user" ? "👤 You" : "🤖 AI Analyst"}
        </div>
        {msg.role === "assistant" && msg.content && (
          <button className="copy-msg-btn" onClick={handleCopy}>
            {copied ? "✓ Copied" : "📋 Copy"}
          </button>
        )}
      </div>
      <div className="message-content">
        <ReactMarkdown>{msg.content}</ReactMarkdown>
        {msg.streaming && msg.content === "" && (
          <div className="typing-indicator">
            <span></span>
            <span></span>
            <span></span>
          </div>
        )}
      </div>
      {msg.sources?.length > 0 && (
        <div className="sources">
          <span className="sources-label">📎 Sources:</span>
          <div className="sources-list">
            {msg.sources.map((s, i) => (
              <span key={i} className="source-chip">{s.source}</span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default function App() {
  const [urlA, setUrlA] = useState("");
  const [urlB, setUrlB] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [videoA, setVideoA] = useState(null);
  const [videoB, setVideoB] = useState(null);
  const [loadingVideos, setLoadingVideos] = useState(false);
  const [ingested, setIngested] = useState(false);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [sessionId, setSessionId] = useState("");
  const [error, setError] = useState("");
  const chatEndRef = useRef(null);
  const [backendReady, setBackendReady] = useState(false);

  // Edit Video Modal State
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [editingLabel, setEditingLabel] = useState("");
  const [editTitle, setEditTitle] = useState("");
  const [editCreator, setEditCreator] = useState("");
  const [editViews, setEditViews] = useState("");
  const [editLikes, setEditLikes] = useState("");
  const [editComments, setEditComments] = useState("");
  const [editFollowers, setEditFollowers] = useState("");
  const [editDuration, setEditDuration] = useState("");
  const [editTranscript, setEditTranscript] = useState("");

  // Check if backend is running
  useEffect(() => {
    const checkBackend = async () => {
      try {
        const response = await fetch(`${API}/health`, {
          method: "GET",
          headers: { "Content-Type": "application/json" },
        });
        if (response.ok) {
          setBackendReady(true);
          console.log("✅ Backend is running!");
        }
      } catch (e) {
        setBackendReady(false);
        console.error("❌ Backend not available:", e.message);
      }
    };

    checkBackend();
    const interval = setInterval(checkBackend, 5000);
    return () => clearInterval(interval);
  }, []);

  // Initialize session
  useEffect(() => {
    fetch(`${API}/session/new`)
      .then((r) => r.json())
      .then((d) => setSessionId(d.session_id))
      .catch(() => setSessionId("session-" + Date.now()));
  }, []);

  // Auto-scroll to latest message
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const validateInputs = () => {
    if (!urlA.trim()) {
      setError("❌ Please enter Video A URL (YouTube)");
      return false;
    }
    if (!urlB.trim()) {
      setError("❌ Please enter Video B URL (Instagram Reel)");
      return false;
    }
    if (!apiKey.trim()) {
      setError("❌ Please enter your Gemini API key");
      return false;
    }

    // URL validation
    const isValidUrlA = urlA.includes("youtube.com") || urlA.includes("youtu.be");
    const isValidUrlB = urlB.includes("instagram.com") || urlB.includes("instagr.am");

    if (!isValidUrlA) {
      setError("❌ Video A must be a YouTube URL");
      return false;
    }
    if (!isValidUrlB) {
      setError("❌ Video B must be an Instagram URL");
      return false;
    }

    if (!backendReady) {
      setError("❌ Backend not ready. Make sure to run: uvicorn main:app --reload --host 127.0.0.1 --port 8001");
      return false;
    }

    return true;
  };

  const handleIngest = async () => {
    if (!validateInputs()) return;

    // Capture custom data overrides if they exist in current state
    const customVidA = videoA && videoA.isCustom ? videoA : null;
    const customVidB = videoB && videoB.isCustom ? videoB : null;

    setError("");
    setLoadingVideos(true);
    setIngested(false);
    
    if (!customVidA) setVideoA(null);
    if (!customVidB) setVideoB(null);
    
    setMessages([]);

    try {
      const body = {
        url_a: urlA,
        url_b: urlB,
        api_key: apiKey,
      };

      if (customVidA) body.video_a_custom = customVidA;
      if (customVidB) body.video_b_custom = customVidB;

      const res = await fetch(`${API}/ingest`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      let data;
      try {
        data = await res.json();
      } catch {
        throw new Error(`Server returned ${res.status} without a JSON body`);
      }

      if (!res.ok) {
        const detail = data?.detail || data?.error || "Failed to analyze videos";
        setError(`❌ ${typeof detail === "string" ? detail : JSON.stringify(detail)}`);
        return;
      }

      setVideoA(data.video_a);
      setVideoB(data.video_b);
      setIngested(true);
      const fmtEng = (v) => v.engagement_note || (v.views > 0 ? `${v.engagement_rate}%` : `${v.likes?.toLocaleString() || 0} likes`);
      setMessages([{
        role: "assistant",
        content: `✅ **Both videos loaded and indexed!**\n\n**Video A:** ${data.video_a.title} (@${data.video_a.creator})\n- ${data.video_a.views?.toLocaleString() || 0} views · ${fmtEng(data.video_a)}\n\n**Video B:** ${data.video_b.title} (@${data.video_b.creator})\n- ${data.video_b.likes?.toLocaleString() || 0} likes · ${data.video_b.comments?.toLocaleString() || 0} comments · ${fmtEng(data.video_b)}\n\n🎯 Ask me anything — engagement comparison, hooks, improvements, and more!`,
        sources: [],
      }]);
    } catch (e) {
      setError(`❌ Network Error: ${e.message}\n\n💡 Make sure the backend is running:\n\`uvicorn main:app --reload --host 127.0.0.1 --port 8001\``);
      console.error("Ingest error:", e);
    } finally {
      setLoadingVideos(false);
    }
  };

  const handleChat = async () => {
    if (!input.trim() || streaming || !ingested) return;

    const question = input.trim();
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: question }]);
    setStreaming(true);

    // Get sources
    let sources = [];
    try {
      const srcRes = await fetch(`${API}/chat/sources`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, session_id: sessionId }),
      });
      const srcData = await srcRes.json();
      sources = srcData.sources || [];
    } catch (_) { }

    // Stream response
    setMessages((prev) => [...prev, { role: "assistant", content: "", sources, streaming: true }]);

    try {
      const res = await fetch(`${API}/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, session_id: sessionId }),
      });

      if (!res.ok) {
        throw new Error("Failed to get response");
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let fullText = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        fullText += decoder.decode(value, { stream: true });
        setMessages((prev) => {
          const updated = [...prev];
          updated[updated.length - 1] = {
            role: "assistant",
            content: fullText,
            sources,
            streaming: true,
          };
          return updated;
        });
      }

      setMessages((prev) => {
        const updated = [...prev];
        updated[updated.length - 1] = { role: "assistant", content: fullText, sources, streaming: false };
        return updated;
      });
    } catch (e) {
      setMessages((prev) => {
        const updated = [...prev];
        updated[updated.length - 1] = {
          role: "assistant",
          content: `⚠️ Error: ${e.message}`,
          sources: [],
          streaming: false
        };
        return updated;
      });
    } finally {
      setStreaming(false);
    }
  };

  const handleResetSession = async () => {
    try {
      await fetch(`${API}/session/${sessionId}`, { method: "DELETE" });
    } catch (_) {}
    
    // Generate new session ID
    fetch(`${API}/session/new`)
      .then((r) => r.json())
      .then((d) => setSessionId(d.session_id))
      .catch(() => setSessionId("session-" + Date.now()));
      
    setMessages([]);
    setError("");
  };

  const openEditModal = (label) => {
    const video = label === "A" ? videoA : videoB;
    if (!video) return;
    setEditingLabel(label);
    setEditTitle(video.title || "");
    setEditCreator(video.creator || "");
    setEditViews(video.views || 0);
    setEditLikes(video.likes || 0);
    setEditComments(video.comments || 0);
    setEditFollowers(video.followers || 0);
    setEditDuration(video.duration || 0);
    setEditTranscript(video.transcript || "");
    setIsEditModalOpen(true);
  };

  const saveEditData = () => {
    const originalVideo = editingLabel === "A" ? videoA : videoB;
    
    const viewsNum = parseInt(editViews) || 0;
    const likesNum = parseInt(editLikes) || 0;
    const commentsNum = parseInt(editComments) || 0;
    const engagementRate = viewsNum > 0
      ? parseFloat(((likesNum + commentsNum) / viewsNum * 100).toFixed(4))
      : 0;
    const engagementNote = viewsNum > 0
      ? null
      : `${likesNum.toLocaleString()} likes, ${commentsNum.toLocaleString()} comments (views not provided)`;

    const updatedVideo = {
      ...originalVideo,
      title: editTitle,
      creator: editCreator.replace(/^@/, ""),
      views: viewsNum,
      likes: likesNum,
      comments: commentsNum,
      followers: parseInt(editFollowers) || 0,
      duration: parseInt(editDuration) || 0,
      transcript: editTranscript,
      description: editTranscript,
      hook_first_5s: editTranscript.substring(0, 200),
      engagement_rate: engagementRate,
      engagement_note: engagementNote,
      isCustom: true,
    };

    if (editingLabel === "A") {
      setVideoA(updatedVideo);
    } else {
      setVideoB(updatedVideo);
    }
    
    setIsEditModalOpen(false);
    setMessages((prev) => [
      ...prev,
      {
        role: "assistant",
        content: `✏️ **Video ${editingLabel} details updated locally.**\n\nClick **"Analyze Videos"** to re-analyze and save changes.`,
        sources: [],
      },
    ]);
  };

  const suggestedQuestions = [
    "Why did Video A get more engagement than Video B?",
    "What's the engagement rate of each video?",
    "Compare the hooks in the first 5 seconds.",
    "Who's the creator of Video B and their follower count?",
    "Suggest improvements for B based on A.",
  ];

  return (
    <>
      <div className="app">
        <header className="app-header">
          <div className="header-content">
            <h1>🎬 Video RAG Analyst</h1>
            <p>AI-powered video comparison & insights</p>
            {backendReady ? (
              <div className="backend-status online">✅ Backend Ready</div>
            ) : (
              <div className="backend-status offline">❌ Backend Offline</div>
            )}
          </div>
        </header>

        <div className="url-section">
          <div className="apikey-row">
            <label className="url-label">🔑 Gemini API Key</label>
            <input
              className="url-input"
              type="password"
              placeholder="Get free key at https://aistudio.google.com"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              disabled={loadingVideos}
            />
          </div>

          <div className="url-row">
            <div className="url-input-group">
              <label className="url-label label-a">▶️ Video A (YouTube)</label>
              <input
                className="url-input"
                placeholder="https://youtube.com/watch?v=... or https://youtu.be/..."
                value={urlA}
                onChange={(e) => setUrlA(e.target.value)}
                disabled={loadingVideos}
              />
            </div>
            <div className="url-input-group">
              <label className="url-label label-b">📷 Video B (Instagram Reel)</label>
              <input
                className="url-input"
                placeholder="https://www.instagram.com/reel/..."
                value={urlB}
                onChange={(e) => setUrlB(e.target.value)}
                disabled={loadingVideos}
              />
            </div>
          </div>
        </div>

        <button
          className={`ingest-btn ${loadingVideos ? "loading" : ""}`}
          onClick={handleIngest}
          disabled={loadingVideos || !backendReady}
        >
          {loadingVideos ? "⏳ Analyzing..." : "🚀 Analyze Videos"}
        </button>

        {error && (
          <div className="error-msg">
            <div className="error-content">
              {error}
            </div>
          </div>
        )}
      </div>

      <div className="main-layout">
        <div className="videos-panel">
          <VideoCard label="A" data={videoA} loading={loadingVideos} onEdit={openEditModal} />
          <VideoCard label="B" data={videoB} loading={loadingVideos} onEdit={openEditModal} />
        </div>

        <div className="chat-panel">
          <div className="chat-header">
            <div className="chat-header-flex">
              <h2>💬 Video Analysis Chat</h2>
              {messages.length > 0 && (
                <button className="reset-btn" onClick={handleResetSession} title="Clear conversation history">
                  🧹 Reset Chat
                </button>
              )}
            </div>
          </div>

          <div className="chat-messages">
            {messages.length === 0 && (
              <div className="chat-empty">
                <p className="empty-title">🤖 Ready to Analyze</p>
                <p className="empty-subtitle">Load two videos to start chatting</p>
                <div className="suggested-questions">
                  {suggestedQuestions.map((q, i) => (
                    <button
                      key={i}
                      className="suggested-q"
                      onClick={() => { setInput(q); }}
                      disabled={!ingested}
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {messages.map((msg, i) => (
              <ChatMessage key={i} msg={msg} />
            ))}
            <div ref={chatEndRef} />
          </div>

          {ingested && messages.length > 0 && (
            <div className="suggested-row">
              {suggestedQuestions.slice(0, 2).map((q, i) => (
                <button key={i} className="suggested-chip" onClick={() => setInput(q)}>
                  {q.substring(0, 50)}...
                </button>
              ))}
            </div>
          )}

          <div className="chat-input-row">
            <input
              className="chat-input"
              placeholder={ingested ? "Ask about the videos..." : "Load videos first..."}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleChat()}
              disabled={!ingested || streaming}
            />
            <button
              className="send-btn"
              onClick={handleChat}
              disabled={!ingested || streaming || !input.trim()}
              title="Send message (or press Enter)"
            >
              {streaming ? "⏳" : "➤"}
            </button>
          </div>
        </div>
      </div>

      {/* Manual Data Override Modal */}
      {isEditModalOpen && (
        <div className="modal-backdrop">
          <div className="modal-content">
            <div className="modal-header">
              <h3>✏️ Edit Video {editingLabel} Details</h3>
              <button className="close-modal-btn" onClick={() => setIsEditModalOpen(false)}>✕</button>
            </div>
            <div className="modal-body">
              <div className="form-group">
                <label className="form-label">Video Title</label>
                <input className="form-input" value={editTitle} onChange={(e) => setEditTitle(e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">Creator Username</label>
                <input className="form-input" value={editCreator} onChange={(e) => setEditCreator(e.target.value)} />
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">Views</label>
                  <input className="form-input" type="number" value={editViews} onChange={(e) => setEditViews(e.target.value)} />
                </div>
                <div className="form-group">
                  <label className="form-label">Likes</label>
                  <input className="form-input" type="number" value={editLikes} onChange={(e) => setEditLikes(e.target.value)} />
                </div>
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">Comments</label>
                  <input className="form-input" type="number" value={editComments} onChange={(e) => setEditComments(e.target.value)} />
                </div>
                <div className="form-group">
                  <label className="form-label">Followers</label>
                  <input className="form-input" type="number" value={editFollowers} onChange={(e) => setEditFollowers(e.target.value)} />
                </div>
              </div>
              <div className="form-group">
                <label className="form-label">Duration (seconds)</label>
                <input className="form-input" type="number" value={editDuration} onChange={(e) => setEditDuration(e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">Video Script / Transcript / Description</label>
                <textarea
                  className="form-textarea"
                  rows="4"
                  placeholder="Paste description or auto-generated transcript..."
                  value={editTranscript}
                  onChange={(e) => setEditTranscript(e.target.value)}
                />
              </div>
            </div>
            <div className="modal-footer">
              <button className="cancel-btn" onClick={() => setIsEditModalOpen(false)}>Cancel</button>
              <button className="save-btn" onClick={saveEditData}>Save & Re-Ingest</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
