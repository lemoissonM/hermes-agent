import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  UserSkill,
  createUserSkill,
  deleteUserSkill,
  getUserSkill,
  listUserSkills,
  saveUserSkill,
} from "../api/client";

export default function SkillsPage() {
  const [skills, setSkills] = useState<UserSkill[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [body, setBody] = useState("");
  const [newName, setNewName] = useState("");
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");

  async function refresh() {
    setSkills(await listUserSkills());
  }

  useEffect(() => {
    refresh().catch((e) => setError(String(e)));
  }, []);

  async function loadSkill(name: string) {
    setSelected(name);
    setError("");
    try {
      const row = await getUserSkill(name);
      setBody(row.body_md);
    } catch {
      setBody("");
      setError("Could not load skill body");
    }
  }

  async function onSave(e: FormEvent) {
    e.preventDefault();
    if (!selected) return;
    setStatus("Saving…");
    try {
      await saveUserSkill(selected, body);
      setStatus("Saved");
      await refresh();
    } catch (err) {
      setError(String(err));
    }
  }

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    if (!newName.trim()) return;
    const template = `---\nname: ${newName.trim()}\ndescription: Custom skill.\n---\n\n# ${newName.trim()}\n\nDescribe what this skill does.\n`;
    try {
      await createUserSkill(newName.trim(), template);
      setNewName("");
      await refresh();
      await loadSkill(newName.trim());
    } catch (err) {
      setError(String(err));
    }
  }

  async function onDelete(name: string) {
    if (!confirm(`Remove custom skill "${name}"?`)) return;
    await deleteUserSkill(name);
    if (selected === name) {
      setSelected(null);
      setBody("");
    }
    await refresh();
  }

  return (
    <div className="settings-page skills-page">
      <header className="settings-header">
        <Link to="/">← Chat</Link>
        <h1>Your skills</h1>
        <p className="muted">Add or customize skills saved to your account. Otherwise Hermes uses built-in skills.</p>
      </header>
      {error && <p className="error">{error}</p>}
      <div className="skills-layout">
        <aside>
          <form className="new-skill-form" onSubmit={onCreate}>
            <input
              placeholder="new-skill-name"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
            />
            <button type="submit">Add skill</button>
          </form>
          <ul className="skill-list">
            {skills.map((s) => (
              <li key={s.skill_name}>
                <button
                  type="button"
                  className={selected === s.skill_name ? "active" : ""}
                  onClick={() => loadSkill(s.skill_name)}
                >
                  {s.skill_name}
                  {s.is_custom && " *"}
                </button>
                {s.is_custom && (
                  <button type="button" className="link danger" onClick={() => onDelete(s.skill_name)}>
                    delete
                  </button>
                )}
              </li>
            ))}
          </ul>
        </aside>
        <form className="skill-editor" onSubmit={onSave}>
          {selected ? (
            <>
              <h2>{selected}</h2>
              <textarea rows={20} value={body} onChange={(e) => setBody(e.target.value)} />
              {status && <p className="muted">{status}</p>}
              <button type="submit">Save skill</button>
            </>
          ) : (
            <p className="muted">Select a skill or add a new one.</p>
          )}
        </form>
      </div>
    </div>
  );
}
