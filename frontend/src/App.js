import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { BookOpen, ChevronDown, ChevronRight } from "lucide-react";

import "./App.css";
import PromptLibrary from "./components/PromptLibrary";
import PromptPreview from "./components/PromptPreview";
import { resolveHttp, resolveWs } from "./api";

const USER_ID = "user-123";

function formatTimestamp(value) {
  if (!value) {
    return "";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatPreview(text) {
  if (!text) {
    return "New Conversation";
  }
  const trimmed = text.trim();
  if (trimmed.length <= 52) {
    return trimmed;
  }
  return `${trimmed.slice(0, 52)}…`;
}

export default function App() {
  const llmSessionId = useMemo(() => {
    const random =
      typeof crypto !== "undefined" && crypto.randomUUID
        ? crypto.randomUUID().slice(0, 8)
        : Math.random().toString(36).slice(2, 10);
    return `llm-session-${random}`;
  }, []);

  const [sessions, setSessions] = useState([]);
  const [selectedSessionId, setSelectedSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [reasoningTrail, setReasoningTrail] = useState([]);
  const [liveReasoning, setLiveReasoning] = useState("");
  const [isReasoningOpen, setIsReasoningOpen] = useState(false);
  const [connectionState, setConnectionState] = useState("disconnected");
  const [inputValue, setInputValue] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [statusMessage, setStatusMessage] = useState("");
  const [showPromptLibrary, setShowPromptLibrary] = useState(false);
  const [showPromptPreview, setShowPromptPreview] = useState(false);
  const [previewPrompt, setPreviewPrompt] = useState(null);

  const wsRef = useRef(null);
  const pendingAssistantIdRef = useRef(null);
  const messagesEndRef = useRef(null);

  const scrollToBottom = useCallback(() => {
    const node = messagesEndRef.current;
    if (node && typeof node.scrollIntoView === "function") {
      node.scrollIntoView({ behavior: "smooth" });
    }
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, liveReasoning, scrollToBottom]);

  const loadSessions = useCallback(async () => {
    try {
      const response = await fetch(resolveHttp(`/sessions?user_id=${USER_ID}`));
      if (!response.ok) {
        throw new Error(`Failed to load sessions (${response.status})`);
      }
      const data = await response.json();
      setSessions(data.sessions || []);
      if (!selectedSessionId && data.sessions?.length) {
        setSelectedSessionId(data.sessions[0].id);
      }
    } catch (error) {
      console.error("Failed to load sessions", error);
      setStatusMessage("Unable to load sessions from the server.");
    }
  }, [selectedSessionId]);

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  const loadMessages = useCallback(async (chatSessionId) => {
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
      setMessages(
        (data.messages || []).map((msg) => ({
          id: msg.id,
          role: msg.role,
          content: msg.content,
          created_at: msg.created_at,
          isStreaming: false,
          isError: false,
        }))
      );
      pendingAssistantIdRef.current = null;
    } catch (error) {
      console.error("Failed to load messages", error);
      setMessages([]);
      setStatusMessage("Unable to load chat history for this session.");
    }
  }, []);

  useEffect(() => {
    if (!selectedSessionId) {
      return;
    }
    loadMessages(selectedSessionId);
    setReasoningTrail([]);
    setLiveReasoning("");
    setIsReasoningOpen(false);
    pendingAssistantIdRef.current = null;
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

    const updateAssistantMessage = (content, { final = false, isError = false } = {}) => {
      const messageId = pendingAssistantIdRef.current;
      const timestamp = new Date().toISOString();

      if (!messageId) {
        const fallbackId = `assistant-${Date.now()}`;
        setMessages((prev) => [
          ...prev,
          {
            id: fallbackId,
            role: "assistant",
            content,
            created_at: timestamp,
            isStreaming: !final,
            isError,
          },
        ]);
        pendingAssistantIdRef.current = final ? null : fallbackId;
        if (final) {
          setIsSending(false);
        }
        return;
      }

      setMessages((prev) => {
        let found = false;
        const updated = prev.map((message) => {
          if (message.id === messageId) {
            found = true;
            return {
              ...message,
              content,
              isStreaming: !final,
              isError,
            };
          }
          return message;
        });
        if (!found) {
          updated.push({
            id: messageId,
            role: "assistant",
            content,
            created_at: timestamp,
            isStreaming: !final,
            isError,
          });
        }
        return updated;
      });

      if (final) {
        pendingAssistantIdRef.current = null;
        setIsSending(false);
      }
    };

    socket.onopen = () => {
      setConnectionState("connected");
      setReasoningTrail([]);
      setLiveReasoning("");
      setStatusMessage("");
      pendingAssistantIdRef.current = null;
    };

    socket.onclose = () => {
      setConnectionState("disconnected");
      setIsSending(false);
      pendingAssistantIdRef.current = null;
      wsRef.current = null;
    };

    socket.onerror = () => {
      setConnectionState("error");
      setIsSending(false);
      setStatusMessage("WebSocket connection encountered an error.");
      pendingAssistantIdRef.current = null;
    };

    socket.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        switch (payload.type) {
          case "reasoning":
            if (payload.partial) {
              setLiveReasoning(payload.content || "");
              setIsReasoningOpen(true);
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
            break;
          case "assistant_partial":
            updateAssistantMessage(payload.content || "", { final: false });
            break;
          case "assistant": {
            const text = payload.content || "";
            updateAssistantMessage(text, { final: true, isError: false });
            setSessions((prev) =>
              prev.map((session) =>
                session.id === selectedSessionId
                  ? {
                      ...session,
                      message_count: (session.message_count || 0) + 1,
                      updated_at: new Date().toISOString(),
                    }
                  : session
              )
            );
            setStatusMessage("");
            break;
          }
          case "error": {
            const message = payload.content || "The assistant reported an error.";
            updateAssistantMessage(message, { final: true, isError: true });
            setLiveReasoning(`Error: ${message}`);
            setStatusMessage(message);
            break;
          }
          default:
            break;
        }
      } catch (error) {
        console.error("Failed to parse websocket payload", error);
      }
    };

    return () => {
      socket.close(1000, "switching sessions");
    };
  }, [selectedSessionId, llmSessionId, setSessions]);

  const sendMessage = useCallback(
    (rawContent, { clearInput = false } = {}) => {
      const content = (rawContent || "").trim();
      if (!content || !selectedSessionId) {
        return false;
      }
      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
        setStatusMessage("Message not sent — connection is not ready.");
        return false;
      }

      const timestamp = new Date().toISOString();
      const userMessage = {
        id: `user-${Date.now()}`,
        role: "user",
        content,
        created_at: timestamp,
        isStreaming: false,
        isError: false,
      };

      const assistantId = `assistant-${Date.now()}-stream`;
      pendingAssistantIdRef.current = assistantId;

      setMessages((prev) => [
        ...prev,
        userMessage,
        {
          id: assistantId,
          role: "assistant",
          content: "",
          created_at: timestamp,
          isStreaming: true,
          isError: false,
        },
      ]);

      setReasoningTrail([]);
      setLiveReasoning("");
      setIsReasoningOpen(false);
      setIsSending(true);
      setStatusMessage("");
      if (clearInput) {
        setInputValue("");
      }

      setSessions((prev) =>
        prev.map((session) =>
          session.id === selectedSessionId
            ? {
                ...session,
                message_count: (session.message_count || 0) + 1,
                first_message_preview: session.first_message_preview || content,
                updated_at: timestamp,
              }
            : session
        )
      );

      const payload = { type: "user_message", content };
      wsRef.current.send(JSON.stringify(payload));
      return true;
    },
    [selectedSessionId]
  );

  const handleSend = useCallback(() => {
    sendMessage(inputValue, { clearInput: true });
  }, [inputValue, sendMessage]);

  useEffect(() => {
    if (liveReasoning) {
      setIsReasoningOpen(true);
    }
  }, [liveReasoning]);

  useEffect(() => {
    const handler = (event) => {
      if (event.key === "Enter" && !event.shiftKey && !showPromptLibrary && !showPromptPreview) {
        event.preventDefault();
        handleSend();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [handleSend, showPromptLibrary, showPromptPreview]);

  const handlePromptSelect = useCallback((prompt) => {
    setPreviewPrompt(prompt);
    setShowPromptPreview(true);
  }, []);

  const handlePromptSend = useCallback(
    (preparedPrompt) => {
      const wasQueued = sendMessage(preparedPrompt);
      if (wasQueued) {
        setShowPromptPreview(false);
        setPreviewPrompt(null);
        setShowPromptLibrary(false);
      }
    },
    [sendMessage]
  );

  const handleCreateSession = useCallback(async () => {
    try {
      const response = await fetch(resolveHttp("/sessions"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: USER_ID,
          llm_session_id: llmSessionId,
          title: "Untitled conversation",
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
      setStatusMessage("");
    } catch (error) {
      console.error("Failed to create session", error);
      setStatusMessage("Could not create a new chat session.");
    }
  }, [llmSessionId, loadSessions]);

  const activeSession = sessions.find((session) => session.id === selectedSessionId);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="border-b-2 border-black px-4 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-lg font-bold text-gray-900">Codex Sessions</h1>
              <p className="text-xs uppercase tracking-wide text-gray-600">User: {USER_ID}</p>
            </div>
            <button
              type="button"
              onClick={handleCreateSession}
              className="border-2 border-black bg-primary px-3 py-2 text-sm font-semibold text-white transition-colors hover:bg-primary-dark"
            >
              New Chat
            </button>
          </div>
        </div>

        <nav className="flex-1 overflow-y-auto">
          {sessions.length === 0 ? (
            <p className="px-4 py-6 text-sm text-gray-600">No sessions yet. Start a new chat.</p>
          ) : (
            sessions.map((session) => {
              const isActive = session.id === selectedSessionId;
              return (
                <button
                  key={session.id}
                  type="button"
                  onClick={() => setSelectedSessionId(session.id)}
                  className={`flex w-full flex-col border-b border-gray-200 px-4 py-3 text-left transition ${
                    isActive ? "border-l-4 border-l-primary bg-red-50" : "hover:bg-gray-100"
                  }`}
                >
                  <span className="text-sm font-semibold text-gray-900">
                    {formatPreview(session.first_message_preview || session.title)}
                  </span>
                  <span className="text-xs text-gray-600">
                    Messages: {session.message_count || 0}
                  </span>
                  <span className="text-xs text-gray-500">
                    Updated {formatTimestamp(session.updated_at)}
                  </span>
                </button>
              );
            })
          )}
        </nav>
      </aside>

      <main className="chat-main">
        <header className="flex items-center justify-between border-b-2 border-black bg-white px-6 py-4">
          <div>
            <h2 className="text-xl font-bold text-gray-900">
              {activeSession?.title || "Conversation"}
            </h2>
            <p className="text-xs text-gray-600">
              Connection:&nbsp;
              <span className="font-semibold uppercase text-primary">{connectionState}</span>
            </p>
          </div>
          <button
            type="button"
            onClick={() => setShowPromptLibrary(true)}
            className="flex items-center gap-2 border-2 border-black bg-white px-4 py-2 text-sm font-semibold text-gray-900 transition-colors hover:bg-primary hover:text-white"
          >
            <BookOpen className="h-4 w-4" />
            Prompt Library
          </button>
        </header>

        <section className="flex-1 space-y-4 overflow-y-auto px-6 py-6">
          {messages.map((message) => (
            <MessageBubble key={message.id} message={message} />
          ))}
          <ReasoningPanel
            isOpen={isReasoningOpen}
            onToggle={() => setIsReasoningOpen((prev) => !prev)}
            liveText={liveReasoning}
            history={reasoningTrail}
          />
          <div ref={messagesEndRef} />
        </section>

        <footer className="border-t-2 border-black bg-gray-50 px-6 py-4">
          {statusMessage && (
            <div className="mb-3 border-2 border-primary bg-red-50 px-3 py-2 text-xs text-primary">
              {statusMessage}
            </div>
          )}
          <div className="flex items-end gap-3">
            <textarea
              value={inputValue}
              onChange={(event) => setInputValue(event.target.value)}
              placeholder="Ask Codex to explore your workspace..."
              className="flex-1 resize-none border-2 border-black px-4 py-3 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-primary-light"
              rows={3}
              disabled={!selectedSessionId || connectionState !== "connected" || isSending}
            />
            <button
              type="button"
              onClick={handleSend}
              disabled={!selectedSessionId || isSending || !inputValue.trim()}
              className="border-2 border-black bg-primary px-5 py-3 text-sm font-semibold text-white transition-colors hover:bg-primary-dark disabled:cursor-not-allowed"
            >
              Send
            </button>
          </div>
        </footer>
      </main>

      {showPromptLibrary && (
        <div className="fixed inset-0 z-40 flex items-start justify-center bg-black/40 px-4 py-8">
          <div className="h-[85vh] w-full max-w-6xl overflow-hidden border-2 border-black bg-white shadow-xl">
            <PromptLibrary
              user={USER_ID}
              onSelectPrompt={handlePromptSelect}
              onClose={() => setShowPromptLibrary(false)}
            />
          </div>
        </div>
      )}

      {showPromptPreview && previewPrompt && (
        <PromptPreview
          prompt={previewPrompt}
          onSend={handlePromptSend}
          onCancel={() => {
            setShowPromptPreview(false);
            setPreviewPrompt(null);
          }}
        />
      )}
    </div>
  );
}

function MessageBubble({ message }) {
  const isAssistant = message.role === "assistant";
  const bubbleClasses = isAssistant
    ? "border-black bg-gray-50 text-gray-900"
    : "border-black bg-primary text-white";
  const streamingSubtitle =
    message.isStreaming && !message.isError ? (
      <span className="ml-2 text-xs uppercase tracking-wide text-gray-500">Streaming…</span>
    ) : null;
  const errorSubtitle = message.isError ? (
    <span className="ml-2 text-xs uppercase tracking-wide text-primary">Error</span>
  ) : null;

  return (
    <div className={`flex ${isAssistant ? "justify-start" : "justify-end"}`}>
      <div className={`max-w-xl border-2 px-4 py-3 text-sm leading-relaxed ${bubbleClasses}`}>
        <p className="whitespace-pre-line">{message.content}</p>
        {(streamingSubtitle || errorSubtitle) && (
          <div className="mt-1 flex items-center text-xs text-gray-500">
            {streamingSubtitle}
            {errorSubtitle}
          </div>
        )}
      </div>
    </div>
  );
}

function ReasoningPanel({ isOpen, onToggle, liveText, history }) {
  const hasHistory = history.length > 0;
  const hasLive = Boolean(liveText);
  if (!hasHistory && !hasLive) {
    return null;
  }

  const Icon = isOpen ? ChevronDown : ChevronRight;

  return (
    <div className="border-2 border-black bg-white">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center justify-between bg-gray-100 px-4 py-2 text-sm font-semibold text-gray-900 transition-colors hover:bg-gray-200"
      >
        <span>Thinking</span>
        <Icon className="h-4 w-4" />
      </button>
      {isOpen && (
        <div className="space-y-3 border-t border-gray-200 px-4 py-3 text-sm text-gray-800">
          {liveText && (
            <div className="border border-primary bg-red-50 px-3 py-2 text-xs text-gray-800">
              {liveText}
            </div>
          )}
          {hasHistory && (
            <ul className="space-y-2">
              {history.map((entry) => (
                <li key={entry.id} className="border border-gray-200 bg-gray-50 px-3 py-2">
                  {entry.text}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
