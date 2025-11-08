import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import "./App.css";

const USER_ID = "user-123";
const API_BASE = (process.env.REACT_APP_BACKEND_URL || "http://localhost:8000").replace(/\/$/, "");

function resolveHttp(path) {
  if (!API_BASE) {
    return path;
  }
  return `${API_BASE}${path}`;
}

function resolveWs(path) {
  const origin = API_BASE || window.location.origin;
  const url = new URL(path, origin);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  return url.toString();
}

function formatTimestamp(value) {
  try {
    const date = new Date(value);
    return date.toLocaleString();
  } catch (error) {
    return value;
  }
}

export default function App() {
  const llmSessionId = useMemo(() => {
    const random = typeof crypto !== "undefined" && crypto.randomUUID
      ? crypto.randomUUID().slice(0, 8)
      : Math.random().toString(36).slice(2, 10);
    return `llm-session-${random}`;
  }, []);

  const [sessions, setSessions] = useState([]);
  const [selectedSessionId, setSelectedSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [reasoningTrail, setReasoningTrail] = useState([]);
  const [liveReasoning, setLiveReasoning] = useState("");
  const [connectionState, setConnectionState] = useState("disconnected");
  const [inputValue, setInputValue] = useState("");
  const [isSending, setIsSending] = useState(false);
  const wsRef = useRef(null);

  const loadSessions = useCallback(async () => {
    try {
      const response = await fetch(resolveHttp(`/sessions?user_id=${USER_ID}`));
      if (!response.ok) {
        throw new Error(`Failed to load sessions (${response.status})`);
      }
      const data = await response.json();
      setSessions(data.sessions);
      if (!selectedSessionId && data.sessions.length > 0) {
        setSelectedSessionId(data.sessions[0].id);
      }
    } catch (error) {
      console.error("Failed to load sessions", error);
    }
  }, [selectedSessionId]);

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  const loadMessages = useCallback(
    async (chatSessionId) => {
      if (!chatSessionId) {
        setMessages([]);
        return;
      }
      try {
        const response = await fetch(
          resolveHttp(`/sessions/${chatSessionId}/messages?user_id=${USER_ID}`)
        );
        if (!response.ok) {
          throw new Error(`Failed to load messages (${response.status})`);
        }
        const data = await response.json();
        setMessages(data.messages.map((msg) => ({
          id: msg.id,
          role: msg.role,
          content: msg.content,
          created_at: msg.created_at,
        })));
      } catch (error) {
        console.error("Failed to load messages", error);
        setMessages([]);
      }
    },
    []
  );

  useEffect(() => {
    if (!selectedSessionId) {
      return;
    }
    loadMessages(selectedSessionId);
  }, [selectedSessionId, loadMessages]);

  useEffect(() => {
    if (!selectedSessionId) {
      return undefined;
    }

    const wsUrl = resolveWs(
      `/chat?chat_session_id=${selectedSessionId}&llm_session_id=${llmSessionId}&user_id=${USER_ID}`
    );
    const socket = new WebSocket(wsUrl);
    wsRef.current = socket;
    setConnectionState("connecting");

    socket.onopen = () => {
      setConnectionState("connected");
      setReasoningTrail([]);
      setLiveReasoning("");
    };

    socket.onclose = () => {
      setConnectionState("disconnected");
      wsRef.current = null;
    };

    socket.onerror = () => {
      setConnectionState("error");
    };

    socket.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        if (payload.type === "reasoning") {
          if (payload.partial) {
            setLiveReasoning(payload.content || "");
          } else {
            setLiveReasoning("");
            setReasoningTrail((prev) => [
              ...prev,
              {
                id: `${Date.now()}-${prev.length}`,
                text: payload.content || "",
              },
            ]);
          }
        } else if (payload.type === "assistant") {
          const text = payload.content || "";
          setLiveReasoning("");
          setMessages((prev) => [
            ...prev,
            { id: `assistant-${Date.now()}`, role: "assistant", content: text },
          ]);
          setIsSending(false);
        } else if (payload.type === "error") {
          setLiveReasoning(`Error: ${payload.content || "Unexpected error"}`);
          setIsSending(false);
        }
      } catch (error) {
        console.error("Failed to parse websocket payload", error);
      }
    };

    return () => {
      socket.close(1000, "switching sessions");
    };
  }, [selectedSessionId, llmSessionId]);

  const handleCreateSession = useCallback(async () => {
    try {
      const response = await fetch(resolveHttp("/sessions"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: USER_ID,
          llm_session_id: llmSessionId,
          title: "Untitled analysis",
        }),
      });
      if (!response.ok) {
        throw new Error(`Failed to create session (${response.status})`);
      }
      const session = await response.json();
      await loadSessions();
      setSelectedSessionId(session.chat_session_id);
      setMessages([]);
      setReasoningTrail([]);
    } catch (error) {
      console.error("Failed to create session", error);
    }
  }, [llmSessionId, loadSessions]);

  const handleSend = useCallback(async () => {
    const content = inputValue.trim();
    if (!content || !selectedSessionId) {
      return;
    }
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      console.warn("WebSocket not ready");
      return;
    }

    setMessages((prev) => [
      ...prev,
      { id: `user-${Date.now()}`, role: "user", content },
    ]);
    setInputValue("");
    setIsSending(true);
    setLiveReasoning("");

    const payload = { type: "user_message", content };
    wsRef.current.send(JSON.stringify(payload));
  }, [inputValue, selectedSessionId]);

  useEffect(() => {
    const handler = (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        handleSend();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [handleSend]);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-800">
          <div>
            <h1 className="text-lg font-semibold">Codex Sessions</h1>
            <p className="text-xs text-slate-400">User: {USER_ID}</p>
          </div>
          <button
            type="button"
            onClick={handleCreateSession}
            className="rounded-md bg-primary px-3 py-1 text-sm font-medium text-white shadow hover:bg-primary-light"
          >
            New
          </button>
        </div>
        <nav className="overflow-y-auto">
          {sessions.length === 0 ? (
            <p className="px-4 py-6 text-sm text-slate-500">No sessions yet.</p>
          ) : (
            sessions.map((session) => (
              <button
                key={session.id}
                type="button"
                onClick={() => setSelectedSessionId(session.id)}
                className={`w-full px-4 py-3 text-left transition hover:bg-slate-800 ${
                  session.id === selectedSessionId ? "bg-slate-800" : ""
                }`}
              >
                <p className="text-sm font-medium text-slate-100 truncate">
                  {session.title || "Untitled analysis"}
                </p>
                <p className="text-xs text-slate-500">
                  Updated {formatTimestamp(session.updated_at)}
                </p>
              </button>
            ))
          )}
        </nav>
      </aside>

      <main className="chat-main">
        <header className="flex items-center justify-between border-b border-slate-800 px-6 py-4">
          <div>
            <h2 className="text-lg font-semibold text-white">
              {sessions.find((session) => session.id === selectedSessionId)?.title || "Conversation"}
            </h2>
            <p className="text-xs text-slate-500">
              Connection: <span className="uppercase tracking-wide">{connectionState}</span>
            </p>
          </div>
        </header>

        <section className="flex-1 overflow-y-auto space-y-4 px-6 py-6">
          {messages.map((message) => (
            <MessageBubble key={message.id} message={message} />
          ))}

          {reasoningTrail.length > 0 && (
            <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-4 text-sm text-slate-300">
              <h3 className="mb-2 font-semibold text-slate-200">Reasoning</h3>
              <ul className="space-y-2">
                {reasoningTrail.map((entry) => (
                  <li key={entry.id} className="rounded-md bg-slate-900/60 p-2 text-slate-300">
                    {entry.text}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {liveReasoning && (
            <div className="rounded-lg border border-slate-900 bg-slate-900/80 p-3 text-xs text-slate-400">
              {liveReasoning}
            </div>
          )}
        </section>

        <footer className="border-t border-slate-800 bg-slate-900/60 p-4">
          <div className="flex items-end gap-3">
            <textarea
              value={inputValue}
              onChange={(event) => setInputValue(event.target.value)}
              placeholder="Ask Codex to explore your workspace..."
              className="flex-1 resize-none rounded-md border border-slate-800 bg-slate-950 px-4 py-3 text-sm text-white shadow-inner outline-none focus:border-primary focus:ring-2 focus:ring-primary/40"
              rows={3}
              disabled={!selectedSessionId || connectionState !== "connected" || isSending}
            />
            <button
              type="button"
              onClick={handleSend}
              disabled={!selectedSessionId || isSending || !inputValue.trim()}
              className="shrink-0 rounded-md bg-primary px-4 py-2 text-sm font-semibold text-white shadow transition hover:bg-primary-light disabled:cursor-not-allowed"
            >
              Send
            </button>
          </div>
        </footer>
      </main>
    </div>
  );
}

function MessageBubble({ message }) {
  const isAssistant = message.role === "assistant";
  return (
    <div className={`flex ${isAssistant ? "justify-start" : "justify-end"}`}>
      <div
        className={`max-w-xl rounded-2xl px-4 py-3 text-sm shadow ${
          isAssistant
            ? "bg-slate-900 text-slate-100 border border-slate-800"
            : "bg-primary text-white"
        }`}
      >
        <p className="whitespace-pre-line leading-relaxed">{message.content}</p>
      </div>
    </div>
  );
}
