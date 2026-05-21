#  Agent & Symposa — Tooling Inventory

This document maps the **Tooling Inventory** product requirements to what exists in this repository: native  tools, toolsets, gateway messaging channels, bundled skills, and Symposa integrations. Use it when configuring agents, company defaults, and operator checklists.

**Sources:** [`toolsets.py`](../toolsets.py), [`tools/`](../tools/), [`skills/`](../skills/), [`optional-skills/`](../optional-skills/), [`gateway/platforms/`](../gateway/platforms/), Symposa [`symposa-web`](../toolsets.py) toolset, and [`symposa2/services/credential_registry.py`](../symposa2/services/credential_registry.py).

---

## Requirements coverage (PDF checklist)

| PDF section | Required capability | How it is covered here | Notes |
|-------------|---------------------|------------------------|-------|
| **1. Workspace — Google** | Drive read/write/list | Skill: `google-workspace` + tools `read_file`, `write_file`, `search_files` | Symposa integration: OAuth via Settings → Google Workspace |
| | Gmail read/draft/send | `google-workspace` skill (Gmail API / `gws`) | Preloaded by default for Symposa tenants |
| | Calendar CRUD/list | `google-workspace` skill | Same OAuth |
| **1. Workspace — Microsoft** | OneDrive files | **Partial** — no dedicated OneDrive skill in tree | Use Microsoft Graph via custom skill/MCP, or `terminal` + Graph CLI if you add one |
| | Outlook email | **Partial** — `himalaya` (IMAP/SMTP), `teams-meeting-pipeline` (Graph meetings) | No first-class Outlook REST skill; configure IMAP or extend Graph |
| | Microsoft Calendar | **Partial** — `teams-meeting-pipeline` (meetings/transcripts) | Full calendar parity not bundled |
| **2. File operations** | Read PDF, DOCX, XLSX, CSV, TXT, JSON | Tools: `read_file`, `search_files`; skills: `ocr-and-documents`, `powerpoint`, `nano-pdf` | `read_file` handles text-oriented formats; binaries use skill scripts |
| | Convert / extract | `web_extract` (remote PDFs), `ocr-and-documents`, `nano-pdf` | |
| | Metadata | `read_file`, `search_files`, terminal + skill scripts | |
| | Full-text / keyword search | `search_files` (`target=content` or `files`) | |
| | Semantic search | `session_search`, `memory`; optional vector skills (e.g. `qdrant` in optional-skills) | |
| | Write/update structured files | `write_file`, `patch` | |
| **3. Web intelligence** | Web search | Tool: `web_search` | Backends: Exa, Firecrawl, Parallel, Tavily |
| | Structured results | `web_search` JSON results | |
| | Extract / parse HTML | Tool: `web_extract` | Markdown-oriented extraction |
| | Multi-page crawl | **Partial** — `web_extract` multi-URL; deep crawl via Firecrawl in extract path | `web_crawl` exists in code but is **not** exposed as a registered agent tool; enable via skill/script or add to toolset if needed |
| **4. Communication** | **WhatsApp Business** | Gateway: `-whatsapp` + Symposa WhatsApp channel | Bridge supports Business API, `whatsapp-web.js`, and Baileys — see [gateway/platforms/whatsapp.py](../gateway/platforms/whatsapp.py) |
| | Send notifications | `send_message` (platform `whatsapp`) + gateway push | Symposa: plugin routes WhatsApp to tenant conversations |
| | Read messages | WhatsApp gateway adapter (inbound) | |
| | Workflow triggers | Gateway hooks, `cronjob`, Symposa `pre_gateway_dispatch` | |
| **5. Knowledge** | Summarize documents/threads | `session_search`; context **compression** in agent loop; skills/workflows | No single tool named “summarizer”; compression + auxiliary LLM tasks |

---

## Native  tools (agent-callable)

These are registered under [`tools/`](../tools/) and grouped into toolsets in [`toolsets.py`](../toolsets.py).

### Skills (discovery & authoring)

| Tool | Purpose |
|------|---------|
| `skills_list` | List available skills (name, description, category) |
| `skill_view` | Load full `SKILL.md` or linked files (`references/`, `scripts/`, `templates/`) |
| `skill_manage` | Create, patch, edit, or remove skills |

### File manipulation

| Tool | Purpose |
|------|---------|
| `read_file` | Read file contents (pagination, size limits) |
| `write_file` | Create/overwrite files |
| `patch` | Apply fuzzy patches to files |
| `search_files` | Search by path glob and/or file content |

### Web

| Tool | Purpose |
|------|---------|
| `web_search` | Internet search (structured results) |
| `web_extract` | Extract page/PDF content to markdown |

### Terminal & code

| Tool | Purpose |
|------|---------|
| `terminal` | Run shell commands (with approval on dangerous ops) |
| `process` | Manage background processes |
| `execute_code` | Run Python that calls other tools in-process |
| `delegate_task` | Spawn subagents for isolated work |

### Browser automation

| Tool | Purpose |
|------|---------|
| `browser_navigate` | Open URLs |
| `browser_snapshot` | Accessibility snapshot of page |
| `browser_click` | Click elements |
| `browser_type` | Type into fields |
| `browser_scroll` | Scroll viewport |
| `browser_back` | History back |
| `browser_press` | Key presses |
| `browser_get_images` | Image extraction |
| `browser_vision` | Vision on page |
| `browser_console` | Console logs |
| `browser_cdp` | Chrome DevTools Protocol |
| `browser_dialog` | Handle dialogs |

### Vision, media, speech

| Tool | Purpose |
|------|---------|
| `vision_analyze` | Analyze images |
| `image_generate` | Generate images |
| `video_analyze` | Video understanding (opt-in toolset `video`) |
| `video_generate` | Video generation (opt-in toolset `video_gen`) |
| `text_to_speech` | TTS (Edge, ElevenLabs, OpenAI, xAI) |

### Memory, planning, session

| Tool | Purpose |
|------|---------|
| `memory` | Persistent notes / user profile across sessions |
| `todo` | Task list for multi-step work |
| `session_search` | Search and summarize past conversation history |
| `clarify` | Ask user multiple-choice or open questions |

### Scheduling & messaging

| Tool | Purpose |
|------|---------|
| `cronjob` | Scheduled jobs (prompts, scripts, delivery) |
| `send_message` | Send to connected messaging platforms |