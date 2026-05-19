const API_BASE =
  import.meta.env.VITE_SYMPOSA_API_URL?.replace(/\/$/, "") || "/api";

const TOKEN_KEY = "symposa_access_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

function authHeaders(): HeadersInit {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  return headers;
}

export async function login(email: string, password: string): Promise<void> {
  const resp = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || "Login failed");
  }
  const data = (await resp.json()) as { access_token: string };
  setToken(data.access_token);
}

export type Conversation = {
  id: string;
  title: string;
};

export async function listConversations(): Promise<Conversation[]> {
  const resp = await fetch(`${API_BASE}/conversations`, {
    headers: authHeaders(),
  });
  if (!resp.ok) throw new Error("Failed to load conversations");
  return resp.json();
}

export async function createConversation(title = "New conversation"): Promise<Conversation> {
  const resp = await fetch(`${API_BASE}/conversations`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ title }),
  });
  if (!resp.ok) throw new Error("Failed to create conversation");
  return resp.json();
}

export type ChatEvent = {
  id: string;
  role: string;
  content_text?: string | null;
  created_at: string;
};

export async function listEvents(conversationId: string): Promise<ChatEvent[]> {
  const resp = await fetch(`${API_BASE}/conversations/${conversationId}/events`, {
    headers: authHeaders(),
  });
  if (!resp.ok) throw new Error("Failed to load events");
  return resp.json();
}

export async function submitClarify(
  conversationId: string,
  clarifyId: string,
  response: string,
): Promise<void> {
  const resp = await fetch(`${API_BASE}/conversations/${conversationId}/clarify`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ clarify_id: clarifyId, response }),
  });
  if (!resp.ok) throw new Error("Failed to submit clarify response");
}

export async function submitRunApproval(
  conversationId: string,
  runId: string,
  choice: "once" | "session" | "always" | "deny" = "once",
): Promise<void> {
  const resp = await fetch(`${API_BASE}/conversations/${conversationId}/approval`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ run_id: runId, choice }),
  });
  if (!resp.ok) throw new Error("Failed to submit approval");
}

export type StreamHandlers = {
  onDelta: (text: string) => void;
  onToolProgress?: (payload: Record<string, unknown>) => void;
  onClarify?: (payload: { clarify_id: string; question: string; choices?: string[] }) => void;
  onApproval?: (payload: { run_id: string; command: string; choices?: string[] }) => void;
  onDone: (payload: {
    hermes_session_id?: string;
    reply?: string;
    run_id?: string;
    raw_model_hint?: boolean;
  }) => void;
  onError: (message: string) => void;
};

export async function streamChat(
  conversationId: string,
  message: string,
  hermesSessionId: string | undefined,
  handlers: StreamHandlers,
): Promise<void> {
  const resp = await fetch(`${API_BASE}/conversations/${conversationId}/chat/stream`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ message, hermes_session_id: hermesSessionId }),
  });
  if (!resp.ok || !resp.body) {
    handlers.onError("Chat request failed");
    return;
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const processBlock = (block: string) => {
    const lines = block.split("\n");
    let data = "";
    let eventName = "";
    for (const line of lines) {
      if (line.startsWith("event:")) {
        eventName = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        data += line.slice(5).trim();
      }
    }
    if (!data) return;
    if (data === "[DONE]") return;
    if (eventName === "hermes.tool.progress") {
      try {
        handlers.onToolProgress?.(JSON.parse(data));
      } catch {
        /* ignore */
      }
      return;
    }
    if (eventName === "symposa.clarify") {
      try {
        handlers.onClarify?.(JSON.parse(data));
      } catch {
        /* ignore */
      }
      return;
    }
    if (eventName === "symposa.approval") {
      try {
        handlers.onApproval?.(JSON.parse(data));
      } catch {
        /* ignore */
      }
      return;
    }
    if (eventName === "symposa.done") {
      try {
        handlers.onDone(JSON.parse(data));
      } catch {
        handlers.onDone({});
      }
      return;
    }
    if (eventName === "symposa.error") {
      try {
        const err = JSON.parse(data) as { message?: string };
        handlers.onError(err.message || "Stream error");
      } catch {
        handlers.onError("Stream error");
      }
      return;
    }
    try {
      const parsed = JSON.parse(data) as {
        choices?: Array<{ delta?: { content?: string } }>;
      };
      const delta = parsed.choices?.[0]?.delta?.content;
      if (delta) handlers.onDelta(delta);
    } catch {
      /* ignore non-json */
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";
    for (const part of parts) {
      if (part.trim()) processBlock(part);
    }
  }
  if (buffer.trim()) processBlock(buffer);
}

export type Profile = {
  display_name: string;
  soul_md?: string | null;
};

export async function getProfile(): Promise<Profile> {
  const resp = await fetch(`${API_BASE}/v2/profile`, { headers: authHeaders() });
  if (!resp.ok) throw new Error("Failed to load profile");
  return resp.json();
}

export async function updateProfile(body: Profile): Promise<Profile> {
  const resp = await fetch(`${API_BASE}/v2/profile`, {
    method: "PUT",
    headers: authHeaders(),
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error("Failed to save profile");
  return resp.json();
}

export type UserSkill = {
  skill_name: string;
  description?: string | null;
  is_custom: boolean;
  has_override: boolean;
};

export async function listUserSkills(): Promise<UserSkill[]> {
  const resp = await fetch(`${API_BASE}/v2/skills`, { headers: authHeaders() });
  if (!resp.ok) throw new Error("Failed to load skills");
  return resp.json();
}

export async function getUserSkill(name: string): Promise<{ skill_name: string; body_md: string }> {
  const resp = await fetch(`${API_BASE}/v2/skills/${encodeURIComponent(name)}`, {
    headers: authHeaders(),
  });
  if (!resp.ok) throw new Error("Skill not found");
  return resp.json();
}

export async function saveUserSkill(
  name: string,
  body_md: string,
  description?: string,
): Promise<void> {
  const resp = await fetch(`${API_BASE}/v2/skills/${encodeURIComponent(name)}`, {
    method: "PUT",
    headers: authHeaders(),
    body: JSON.stringify({ body_md, description }),
  });
  if (!resp.ok) throw new Error("Failed to save skill");
}

export async function createUserSkill(
  skill_name: string,
  body_md: string,
  description?: string,
): Promise<void> {
  const resp = await fetch(`${API_BASE}/v2/skills`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ skill_name, body_md, description }),
  });
  if (!resp.ok) throw new Error("Failed to create skill");
}

export async function deleteUserSkill(name: string): Promise<void> {
  const resp = await fetch(`${API_BASE}/v2/skills/${encodeURIComponent(name)}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!resp.ok) throw new Error("Failed to delete skill");
}

export type IntegrationStatus = {
  provider: string;
  label: string;
  description: string;
  scope: string;
  connect_type: string;
  connected: boolean;
};

export async function listIntegrations(): Promise<IntegrationStatus[]> {
  const resp = await fetch(`${API_BASE}/v2/integrations`, { headers: authHeaders() });
  if (!resp.ok) throw new Error("Failed to load integrations");
  return resp.json();
}

export async function connectIntegrationApiKey(provider: string, api_key: string): Promise<void> {
  const resp = await fetch(`${API_BASE}/v2/integrations/${encodeURIComponent(provider)}`, {
    method: "PUT",
    headers: authHeaders(),
    body: JSON.stringify({ api_key }),
  });
  if (!resp.ok) throw new Error("Failed to connect integration");
}

export async function disconnectIntegration(provider: string): Promise<void> {
  const resp = await fetch(`${API_BASE}/v2/integrations/${encodeURIComponent(provider)}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!resp.ok) throw new Error("Failed to disconnect");
}

export async function getGoogleConnectUrl(): Promise<string> {
  const resp = await fetch(`${API_BASE}/v2/integrations/google/connect`, {
    headers: authHeaders(),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || "Google connect unavailable");
  }
  const data = (await resp.json()) as { url: string };
  return data.url;
}

export type UserFile = {
  id: string;
  name: string;
  source: string;
  content_type?: string | null;
  size_bytes?: number | null;
  created_at: string;
  view_url: string;
  download_url: string;
  share_url?: string | null;
};

export async function listUserFiles(): Promise<UserFile[]> {
  const resp = await fetch(`${API_BASE}/user/files`, { headers: authHeaders() });
  if (!resp.ok) throw new Error("Failed to load files");
  const data = (await resp.json()) as { files: UserFile[] };
  return data.files;
}

export function userFileContentUrl(fileId: string, disposition?: "attachment"): string {
  const base = `${API_BASE}/user/files/${encodeURIComponent(fileId)}/content`;
  return disposition === "attachment" ? `${base}?disposition=attachment` : base;
}

export async function fetchUserFileBlob(fileId: string): Promise<Blob> {
  const resp = await fetch(userFileContentUrl(fileId), { headers: authHeaders() });
  if (!resp.ok) throw new Error("Failed to load file");
  return resp.blob();
}

export async function deleteUserFile(fileId: string): Promise<void> {
  const resp = await fetch(`${API_BASE}/user/files/${encodeURIComponent(fileId)}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!resp.ok) throw new Error("Failed to delete file");
}

export async function uploadUserFile(
  file: File,
): Promise<UserFile> {
  const params = new URLSearchParams({
    name: file.name,
    content_type: file.type || "application/octet-stream",
  });
  const token = getToken();
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  const resp = await fetch(`${API_BASE}/user/files?${params}`, {
    method: "POST",
    headers,
    body: await file.arrayBuffer(),
  });
  if (!resp.ok) throw new Error("Failed to upload file");
  return resp.json();
}

export async function register(
  company_name: string,
  email: string,
  password: string,
): Promise<void> {
  const resp = await fetch(`${API_BASE}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ company_name, email, password }),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || "Registration failed");
  }
  const data = (await resp.json()) as { access_token: string };
  setToken(data.access_token);
}
