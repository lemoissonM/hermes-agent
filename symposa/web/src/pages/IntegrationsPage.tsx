import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  IntegrationStatus,
  connectIntegrationApiKey,
  disconnectIntegration,
  getGoogleConnectUrl,
  listIntegrations,
} from "../api/client";

export default function IntegrationsPage() {
  const [items, setItems] = useState<IntegrationStatus[]>([]);
  const [error, setError] = useState("");
  const [apiKeyDraft, setApiKeyDraft] = useState<Record<string, string>>({});

  async function refresh() {
    setItems(await listIntegrations());
  }

  useEffect(() => {
    refresh().catch((e) => setError(String(e)));
  }, []);

  async function connectGoogle() {
    setError("");
    try {
      const url = await getGoogleConnectUrl();
      window.location.href = url;
    } catch (e) {
      setError(String(e));
    }
  }

  async function connectApiKey(provider: string) {
    const key = apiKeyDraft[provider]?.trim();
    if (!key) return;
    setError("");
    try {
      await connectIntegrationApiKey(provider, key);
      setApiKeyDraft((d) => ({ ...d, [provider]: "" }));
      await refresh();
    } catch (e) {
      setError(String(e));
    }
  }

  async function disconnect(provider: string) {
    setError("");
    try {
      await disconnectIntegration(provider);
      await refresh();
    } catch (e) {
      setError(String(e));
    }
  }

  return (
    <div className="settings-page">
      <header className="settings-header">
        <Link to="/settings">← Personality</Link>
        <h1>Integrations</h1>
        <p className="muted">One-click connect for email, GitHub, and more. Stored securely in your account.</p>
      </header>
      {error && <p className="error">{error}</p>}
      <ul className="integration-list">
        {items
          .filter((i) => i.scope === "user")
          .map((item) => (
            <li key={item.provider} className="integration-card">
              <div>
                <strong>{item.label}</strong>
                <p className="muted">{item.description}</p>
                <span className={item.connected ? "badge ok" : "badge"}>
                  {item.connected ? "Connected" : "Not connected"}
                </span>
              </div>
              <div className="integration-actions">
                {item.connect_type === "oauth" && item.provider === "google_workspace" && (
                  <>
                    {!item.connected && (
                      <button type="button" onClick={connectGoogle}>
                        Connect Google
                      </button>
                    )}
                    {item.connected && (
                      <button type="button" className="secondary" onClick={() => disconnect(item.provider)}>
                        Disconnect
                      </button>
                    )}
                  </>
                )}
                {item.connect_type === "api_key" && (
                  <>
                    {!item.connected && (
                      <form
                        onSubmit={(e: FormEvent) => {
                          e.preventDefault();
                          connectApiKey(item.provider);
                        }}
                        className="api-key-form"
                      >
                        <input
                          type="password"
                          placeholder="Paste API key / token"
                          value={apiKeyDraft[item.provider] || ""}
                          onChange={(e) =>
                            setApiKeyDraft((d) => ({ ...d, [item.provider]: e.target.value }))
                          }
                        />
                        <button type="submit">Connect</button>
                      </form>
                    )}
                    {item.connected && (
                      <button type="button" className="secondary" onClick={() => disconnect(item.provider)}>
                        Disconnect
                      </button>
                    )}
                  </>
                )}
              </div>
            </li>
          ))}
      </ul>
    </div>
  );
}
