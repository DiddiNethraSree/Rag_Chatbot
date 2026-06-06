import React, { useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import "./App.css";

const API = "http://localhost:8000";

function StatBadge({ label, value }) {
  return (
    <div className="stat-badge">
      <span className="stat-label">{label}</span>
      <span className="stat-value">{value}</span>
    </div>
  );
}

function VideoCard({ label, data, loading }) {
  if (loading) return (
    <div className="video-card loading">
      <div className="spinner" />
      <p>Fetching Video {label}...</p>
    </div>
  );

  if (!data) return (
    <div className="video-card empty">
      <div className="card-label">Video {label}</div>
      <p className="empty-text">Enter URL above to load</p>
    </div>
  );

  const formatNum = (n) => n >= 1000000
    ? (n / 1000000).toFixed(1) + "M"
    : n >= 1000 ? (n / 1000).toFixed(1) + "K" : String(n);

  return (
    <div className={`video-card loaded ${label === "A" ? "card-a" : "card-b"}`}>
      <div className="card-header">
        <span className="card-label-badge">{label}</span>
        <span className="platform-badge">{data.platform}</span>
      </div>
      <h3 className="video-title">{data.title || "Unknown Title"}</h3>
      <p className="creator-name">@{data.creator}</p>

      <div className="stats-grid">
        <StatBadge label="Views" value={formatNum(data.views)} />
        <StatBadge label="Likes" value={formatNum(data.likes)} />
        <StatBadge label="Comments" value={formatNum(data.comments)} />
        <StatBadge label="Followers" value={formatNum(data.followers)} />
        <StatBadge label="Engagement" value={`${data.engagement_rate}%`} />
        <StatBadge label="Duration" value={`${data.duration}s`} />
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
    </div>
  );
}

function ChatMessage({ msg }) {
  return (
    <div className={`chat-message ${msg.role}`}>
      <div className="message-role">{msg.role === "user" ? "You" : "AI Analyst"}</div>
      <div className="message-content">
        <ReactMarkdown>{msg.content}</ReactMarkdown>
      </div>
      {msg.sources?.length > 0 && (
        <div className="sources">
          <span className="sources-label">📎 Sources:</span>
          {msg.sources.map((s, i) => (
            <span key={i} className="source-chip">{s.source}</span>
          ))}
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

  useEffect(() => {
    fetch(`${API}/session/new`)
      .then((r) => r.json())
      .then((d) => setSessionId(d.session_id))
      .catch(() => setSessionId("session-" + Date.now()));
  }, []);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleIngest = async () => {
    if (!urlA.trim() || !urlB.trim()) {
      setError("Please enter both video URLs.");
      return;
    }
    if (!apiKey.trim()) {
      setError("Please enter your Gemini API key.");
      return;
    }
    setError("");
    setLoadingVideos(true);
    setIngested(false);
    setVideoA(null);
    setVideoB(null);
    setMessages([]);

    try {
      const res = await fetch(`${API}/ingest`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url_a: urlA, url_b: urlB, api_key: apiKey }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to ingest videos");
      }
      const data = await res.json();
      setVideoA(data.video_a);
      setVideoB(data.video_b);
      setIngested(true);
      setMessages([{
        role: "assistant",
        content: `✅ Both videos loaded and indexed!\n\n**Video A:** ${data.video_a.title}\n**Video B:** ${data.video_b.title}\n\nAsk me anything — engagement rates, hook comparison, improvement suggestions, or creator details!`,
        sources: [],
      }]);
    } catch (e) {
      setError(e.message);
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

    // Get sources first
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

    // Stream answer
    setMessages((prev) => [...prev, { role: "assistant", content: "", sources, streaming: true }]);

    try {
      const res = await fetch(`${API}/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, session_id: sessionId }),
      });

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
        updated[updated.length - 1] = { role: "assistant", content: "Error: " + e.message, sources: [], streaming: false };
        return updated;
      });
    } finally {
      setStreaming(false);
    }
  };

  const suggestedQuestions = [
    "Why did Video A get more engagement than Video B?",
    "What's the engagement rate of each video?",
    "Compare the hooks in the first 5 seconds.",
    "Who's the creator of Video B and what's their follower count?",
    "Suggest improvements for B based on what worked in A.",
  ];

  return (
    <>
      <div className="app">
        <header className="app-header">
          <h1>🎬 Video RAG Analyst</h1>
          <p>Compare two videos with AI-powered insights</p>
        </header>

        <div className="url-section">
          <div className="apikey-row">
            <label className="url-label" style={{ color: "#a855f7" }}>Gemini API Key</label>
            <input
              className="url-input"
              type="password"
              placeholder="AIzaSy... (get free key at aistudio.google.com)"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              disabled={loadingVideos} />
          </div>
          <div className="apikey-row">
            <label className="url-label" style={{ color: "#a855f7" }}>Gemini API Key</label>
            <input
              className="url-input"
              type="password"
              placeholder="AIzaSy... (get free key at aistudio.google.com)"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              disabled={loadingVideos} />
          </div>
          <div className="url-row">
            <div className="url-input-group">
              <label className="url-label label-a">Video A (YouTube)</label>
              <input
                className="url-input"
                placeholder="https://youtube.com/watch?v=..."
                value={urlA}
                onChange={(e) => setUrlA(e.target.value)}
                disabled={loadingVideos} />
            </div>
            <div className="url-input-group">
              <label className="url-label label-b">Video B (Instagram Reel)</label>
              <input
                className="url-input"
                placeholder="https://www.instagram.com/reel/..."
                value={urlB}
                onChange={(e) => setUrlB(e.target.value)}
                disabled={loadingVideos} />
            </div>
          </div>
        </div>
        <button
          className={`ingest-btn ${loadingVideos ? "loading" : ""}`}
          onClick={handleIngest}
          disabled={loadingVideos}
        >
          {loadingVideos ? "⏳ Fetching & Indexing..." : "🚀 Analyze Videos"}
        </button>
        {error && <div className="error-msg">⚠️ {error}</div>}
      </div><div className="main-layout">
        <div className="videos-panel">
          <VideoCard label="A" data={videoA} loading={loadingVideos} />
          <VideoCard label="B" data={videoB} loading={loadingVideos} />
        </div>

        <div className="chat-panel">
          <div className="chat-messages">
            {messages.length === 0 && (
              <div className="chat-empty">
                <p>🤖 Load two videos to start chatting</p>
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
              {suggestedQuestions.slice(0, 3).map((q, i) => (
                <button key={i} className="suggested-chip" onClick={() => setInput(q)}>{q}</button>
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
              disabled={!ingested || streaming} />
            <button
              className="send-btn"
              onClick={handleChat}
              disabled={!ingested || streaming || !input.trim()}
            >
              {streaming ? "⏳" : "➤"}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}