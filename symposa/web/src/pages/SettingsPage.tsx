import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Profile, getProfile, updateProfile } from "../api/client";

export default function SettingsPage() {
  const navigate = useNavigate();
  const [displayName, setDisplayName] = useState("Hermes");
  const [soulMd, setSoulMd] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    getProfile()
      .then((p) => {
        setDisplayName(p.display_name);
        setSoulMd(p.soul_md || "");
      })
      .catch((e) => setError(String(e)));
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setStatus("Saving…");
    try {
      await updateProfile({ display_name: displayName, soul_md: soulMd });
      setStatus("Saved. New chats will use this personality.");
    } catch (err) {
      setError(String(err));
      setStatus("");
    }
  }

  return (
    <div className="settings-page">
      <header className="settings-header">
        <Link to="/">← Chat</Link>
        <h1>Agent personality</h1>
        <p className="muted">
          Name your Hermes agent and describe how it should behave. Still Hermes under the hood —
          tools and skills work as usual.
        </p>
      </header>
      <form className="settings-form" onSubmit={onSubmit}>
        <label>
          Display name
          <input
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            placeholder="e.g. Aria"
            required
          />
        </label>
        <label>
          Soul / instructions
          <textarea
            rows={12}
            value={soulMd}
            onChange={(e) => setSoulMd(e.target.value)}
            placeholder="How should your agent communicate? What should it prioritize?"
          />
        </label>
        {error && <p className="error">{error}</p>}
        {status && <p className="muted">{status}</p>}
        <div className="settings-actions">
          <button type="submit">Save personality</button>
          <button type="button" className="secondary" onClick={() => navigate("/settings/integrations")}>
            Integrations →
          </button>
        </div>
      </form>
    </div>
  );
}
