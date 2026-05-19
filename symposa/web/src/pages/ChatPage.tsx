import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ChatEvent,
  Conversation,
  clearToken,
  createConversation,
  listConversations,
  listEvents,
  streamChat,
  submitClarify,
} from "../api/client";
import Composer from "../components/Composer";
import MessageList, { Message } from "../components/MessageList";

function eventsToMessages(events: ChatEvent[]): Message[] {
  return events
    .filter((e) => e.role === "user" || e.role === "assistant")
    .map((e) => ({
      id: e.id,
      role: e.role as "user" | "assistant",
      content: e.content_text || "",
    }));
}

export default function ChatPage() {
  const navigate = useNavigate();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [toolStatus, setToolStatus] = useState("");
  const [hermesSessionId, setHermesSessionId] = useState<string | undefined>();
  const [clarify, setClarify] = useState<{
    clarify_id: string;
    question: string;
    choices?: string[];
  } | null>(null);
  const [clarifyAnswer, setClarifyAnswer] = useState("");
  const [providerWarning, setProviderWarning] = useState("");

  const loadConversations = useCallback(async () => {
    const rows = await listConversations();
    setConversations(rows);
    if (!activeId && rows.length > 0) {
      setActiveId(rows[0].id);
    }
  }, [activeId]);

  useEffect(() => {
    loadConversations().catch(console.error);
  }, [loadConversations]);

  useEffect(() => {
    if (!activeId) return;
    listEvents(activeId)
      .then((events) => setMessages(eventsToMessages(events)))
      .catch(console.error);
  }, [activeId]);

  async function handleNewConversation() {
    const conv = await createConversation();
    setConversations((prev) => [conv, ...prev]);
    setActiveId(conv.id);
    setMessages([]);
    setHermesSessionId(undefined);
  }

  async function handleSend() {
    if (!activeId || !draft.trim()) return;
    const text = draft.trim();
    setDraft("");
    const userMsg: Message = {
      id: `local-${Date.now()}`,
      role: "user",
      content: text,
    };
    setMessages((prev) => [...prev, userMsg]);
    setStreaming(true);
    setToolStatus("");
    setProviderWarning("");

    const assistantId = `stream-${Date.now()}`;
    setMessages((prev) => [...prev, { id: assistantId, role: "assistant", content: "" }]);

    await streamChat(activeId, text, hermesSessionId, {
      onDelta: (chunk) => {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, content: m.content + chunk } : m,
          ),
        );
      },
      onToolProgress: (payload) => {
        const label = String(payload.label || payload.tool || "tool");
        setToolStatus(`Running: ${label}`);
      },
      onClarify: (payload) => {
        setClarify(payload);
        setClarifyAnswer("");
      },
      onDone: async (payload) => {
        if (payload.hermes_session_id) {
          setHermesSessionId(payload.hermes_session_id);
        }
        if (payload.reply) {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId ? { ...m, content: payload.reply! } : m,
            ),
          );
        }
        if (payload.raw_model_hint) {
          setProviderWarning(
            "Reply looks like a base model, not Hermes via the gateway. Check SYMPOSA_RUNTIME_WSL_ROOT.",
          );
        }
        setStreaming(false);
        setToolStatus("");
        setClarify(null);
        if (activeId) {
          try {
            const events = await listEvents(activeId);
            const fromDb = eventsToMessages(events);
            const hasAssistant = fromDb.some((m) => m.role === "assistant");
            if (hasAssistant) {
              setMessages(fromDb);
            }
          } catch {
            /* keep streamed text from payload.reply */
          }
        }
      },
      onError: (message) => {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, content: message } : m,
          ),
        );
        setStreaming(false);
        setToolStatus("");
      },
    });
  }

  async function handleClarifySubmit(answer: string) {
    if (!activeId || !clarify) return;
    await submitClarify(activeId, clarify.clarify_id, answer);
    setClarify(null);
    setClarifyAnswer("");
  }

  return (
    <div className="chat-layout">
      <aside className="sidebar">
        <div className="sidebar-header">
          <strong>Hermes</strong>
          <button type="button" className="link" onClick={() => handleNewConversation()}>
            New
          </button>
        </div>
        <ul className="conv-list">
          {conversations.map((c) => (
            <li key={c.id}>
              <button
                type="button"
                className={c.id === activeId ? "active" : ""}
                onClick={() => setActiveId(c.id)}
              >
                {c.title || "Conversation"}
              </button>
            </li>
          ))}
        </ul>
        <ul className="sidebar-nav">
          <li>
            <a href="/settings">Personality</a>
          </li>
          <li>
            <a href="/settings/integrations">Integrations</a>
          </li>
          <li>
            <a href="/settings/skills">Skills</a>
          </li>
        </ul>
        <button
          type="button"
          className="logout"
          onClick={() => {
            clearToken();
            navigate("/login");
          }}
        >
          Sign out
        </button>
      </aside>
      <main className="chat-main">
        {toolStatus ? <p className="tool-status">{toolStatus}</p> : null}
        {providerWarning ? <p className="provider-warning">{providerWarning}</p> : null}
        <MessageList messages={messages} />
        {clarify ? (
          <div className="clarify-panel">
            <p>{clarify.question}</p>
            {clarify.choices?.length ? (
              <div className="clarify-choices">
                {clarify.choices.map((choice) => (
                  <button
                    key={choice}
                    type="button"
                    onClick={() => handleClarifySubmit(choice)}
                  >
                    {choice}
                  </button>
                ))}
              </div>
            ) : null}
            <div className="clarify-free">
              <input
                type="text"
                value={clarifyAnswer}
                onChange={(e) => setClarifyAnswer(e.target.value)}
                placeholder="Your answer…"
              />
              <button
                type="button"
                onClick={() => handleClarifySubmit(clarifyAnswer)}
                disabled={!clarifyAnswer.trim()}
              >
                Submit
              </button>
            </div>
          </div>
        ) : null}
        <Composer
          value={draft}
          onChange={setDraft}
          onSubmit={handleSend}
          disabled={streaming || !activeId}
        />
      </main>
    </div>
  );
}
