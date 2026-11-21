# VeriFlow — Autonomous Meeting-to-Execution Agent
> **Product Space Agentic AI Hackathon — Problem Statement 03 (PS 03)**  
> *Transforming messy spoken meetings into verified, conflict-free, tracked execution boards.*

---

## 1. Project Overview & Core Thesis

Most "meeting AI" tools are passive summarizers—they generate bulleted notes that get lost in Slack channels, leaving teams with ambiguous action items, forgotten deadlines, and contradictory decisions.

**VeriFlow is an Autonomous Execution Governor.** Rather than summarizing what was said, VeriFlow governs what gets committed to execution:
1. **Diarizes & Attributes:** Links every decision and task directly to an immutable verbatim speaker quote.
2. **Audits Organizational Memory:** Compares newly proposed decisions against historical meetings to catch contradictions (e.g., tech stack reversals, stealth date shifts) before code gets written.
3. **Simulates Blast Radius:** Measures the downstream delay days and blocked tasks caused by scope shifts.
4. **Enforces Human-in-the-Loop (HITL) Gatekeeping:** Prevents any task from polluting Jira, GitHub Issues, or Slack until explicitly reviewed and approved.

---

## 2. PS 03 Requirement Coverage

VeriFlow delivers 100% end-to-end backend and frontend implementation for every requirement of Problem Statement 03:

| PS 03 Requirement | VeriFlow Implementation | Backend Route & Code |
| :--- | :--- | :--- |
| **Speaker-Attributed Ingestion** | Normalizes raw transcripts into indexed speaker segments with verbatim quote anchors. | `POST /api/meetings/ingest` (Stage 1 `parse_transcript`) |
| **Deterministic Extraction** | Structured JSON schema extracts decisions, tasks, owners, and ISO-8601 deadlines. | `POST /api/meetings/ingest` (Stage 2 `extract_commitments`) |
| **Zero-Hallucination Guardrail** | Explicit `null` enforcement and `NEEDS_CLARIFICATION` state for missing owners/dates. | Pydantic v2 strict schema + `missing_fields` prompt |
| **Cross-Meeting Memory** | Persistent `ACTIVE` vs. `SUPERSEDED` decision memory with semantic conflict detection. | `POST /api/meetings/ingest` (Stage 3 `detect_conflicts`) |
| **HITL Staging Queue** | Isolated quarantine queue requiring manual or bulk human approval before execution. | `GET /api/staging`, `POST /api/staging/{id}/approve` |
| **External Task Tracker** | Interactive Kanban board with webhook dispatcher & GitHub Issues sync with local receipts. | `GET /api/tasks`, `PATCH /api/tasks/{id}/status` |
| **Pre-Deadline Reminders** | Proactive scanner for tasks due `<48h`, automated notification dispatcher, and delivery log. | `GET /api/reminders/upcoming`, `POST /api/reminders/dispatch-all` |
| **Per-Person Weekly Digest** | Grouped workload digest by owner showing active tasks, priorities, deadlines, and decisions. | `GET /api/digest/weekly` |

---

## 3. Standout Agentic USPs & Innovations

### 1. Counterfactual Blast-Radius Analyzer (`analyze_blast_radius`)
When a cross-meeting conflict occurs (e.g., changing from PostgreSQL to MongoDB or moving launch from Nov 29 to Nov 22), VeriFlow runs an impact simulation against all active database tasks:
- **Risk Level:** `LOW`, `MEDIUM`, `HIGH`, or `CRITICAL`
- **Impacted Downstream Tasks:** Specific tasks blocked or delayed
- **Estimated Delay:** Calculated slip in days
- **Mitigation Suggestion:** AI-synthesized actionable recommendation (e.g., *"Freeze secondary scope and apply mocked JSON contracts so downstream teams can proceed without waiting on schema refactoring."*)
- **Endpoint:** `GET /api/staging/{id}/blast-radius`

### 2. Zero-Hallucination "Strict Unknowns" Guardrail
If a speaker says *"someone from DevOps should set up CI/CD"*, traditional LLMs invent a random name or today's date. VeriFlow strictly outputs `owner: null`, `deadline_iso: null`, places the item in `NEEDS_CLARIFICATION`, identifies `missing_fields: ["owner", "deadline"]`, and generates a human clarification prompt.

### 3. Visual Decision & Dependency Lineage Graph API
Transforms all historical meetings, decisions, staged conflicts, and execution tasks into a directed DAG:
- **Node Types:** `MEETING`, `DECISION`, `TASK`, `CONFLICT`
- **Edges:** `PRODUCED`, `SUPERSEDES`, `CONFLICTS_WITH`, `BLOCKS`
- **Endpoint:** `GET /api/graph/lineage`

### 4. Meeting Execution Readiness Score (0–100) & Stale Watchdog
- **Readiness Score:** Starts at 100 and applies deterministic deductions for conflicts (-15), missing owners/dates (-12), and dependency risks (-10). Meeting 2 automatically receives a **68/100 (High Risk)** alert.
- **Stale Commitment Watchdog:** Cross-references previous meetings to detect tasks untouched in `TODO` status that are overdue.
- **Endpoint:** `GET /api/analytics/health`

### 5. One-Click Auto-Nudge & Escalation Drafter
Generates polite, quote-backed nudges for blockers or stale commitments and dispatches via Webhook/Slack with logged receipts.
- **Endpoint:** `POST /api/actions/send-nudge`

### 6. Conversational Memory Copilot (`POST /api/memory/ask`)
Allows stakeholders to ask questions across meetings in natural language (e.g. *"What database did we decide to use?"* or *"When is the product launch?"*). VeriFlow strictly cites exact sources (`meeting_title`, `meeting_date`, `speaker`, `verbatim_quote`). If unrecorded, it deterministically responds *"Not found in recorded meeting memory"* with zero hallucinations.

---

## 4. Live Voice Dictation & Browser Compatibility

VeriFlow features a **Live Dictate Meeting** mic directly inside Tab 1 with a quick speaker selector pill (`Sarah (PM)`, `Rohan (Backend)`, `Ananya (Design)`), automatically prefixing lines as `[Speaker]: ...` in real time so judges can dictate conflicting decisions out loud and immediately hit *"Run Agent Pipeline"*.

> ### ⚠️ Browser Compatibility Note
> The **Live Dictate Meeting** microphone feature relies on the browser's Web Speech API (`SpeechRecognition`) and **works in Google Chrome and other supporting Chromium browsers only**.  
> In unsupported browsers (such as Firefox, Brave, or environments with restricted microphone permissions), VeriFlow automatically falls back to simulated live dictation via the **"⚡ Insert Conflict Quote"** button, or you can use the **1-click demo loaders** and standard drag-and-drop / paste input.

---

## 5. Quick 60-Second Judge Demo Guide

Test the full multi-meeting conflict, blast-radius, and reminder engine in under 60 seconds:

```
Step 1: Click "1. Load Sprint Kickoff (Nov 14)" in the top demo bar.
        → Stages 3 decisions and 5 action items (with 2 items in Needs Clarification).
        → Readiness score: 76/100.

Step 2: Click "Approve All Ready (3)" in the queue.
        → Promotes PostgreSQL decision and tasks to active Execution Memory.
        → Tasks populate the Execution Board (Tab 2) and Decision Memory (Tab 3).

Step 3: Click "2. Load Tech Sync (Nov 21 — Conflicts)".
        → Triggers Cross-Meeting Conflict Audit against Meeting 1:
          🔥 Conflict 1: Database switched from PostgreSQL to MongoDB (CTO).
          🔥 Conflict 2: Launch date moved from Nov 29 to Nov 22 (PM) without scope cut.
        → Meeting Readiness drops to 68/100 (⚠️ High Delivery Slippage Risk).
        → Watchdog alerts: 1 stale task from Sprint 14 untouched in TODO.

Step 4: Inspect Counterfactual Blast Radius.
        → Expand "⚡ Blast Radius: HIGH (+3 Days Slip)" to see impacted tasks & mitigation.

Step 5: Test Conversational Memory & Reminders.
        → Click any chip in the floating "Ask Meeting Memory" bar at the bottom:
          "Why did our DB choice change?" → See grounded answer with dual meeting citations.
        → Switch to "Execution Board" (Tab 2):
          See upcoming deadline reminders (<48h) with 1-click "Dispatch All Reminders".
        → Switch to "Lineage Graph" (Tab 5):
          Inspect the live directed graph showing conflicts and supersedes relationships.
```

---

## 6. Architecture & Tech Stack

```
   ┌───────────────────────────────────────────────────────────────┐
   │                  Vite + React 18 Frontend                     │
   │      Warm Cream (#FBF6EF) & Ink (#0D0D0C) Design System       │
   │  SpeechRecognition Mic  •  Ask Memory Pill  •  Lineage Graph  │
   └───────────────────────────────┬───────────────────────────────┘
                                   │ HTTP / JSON REST API
   ┌───────────────────────────────▼───────────────────────────────┐
   │                      FastAPI Backend                          │
   │                                                               │
   │   Stage 1: Speaker Diarization & Verbatim Quote Indexer       │
   │   Stage 2: Gemini 2.5 Flash Strict JSON Schema Extraction     │
   │            (Resilient Auto-Fallback on Rate Limits / 429)     │
   │   Stage 3: Cross-Meeting Conflict Sentinel & Memory Audit     │
   │   Stage 4: Counterfactual Blast-Radius Analyzer               │
   │   Stage 5: Human-in-the-Loop Quarantine Queue                 │
   │   Stage 6: Proactive Deadline Scanner & Webhook Dispatcher    │
   └───────────────────────────────┬───────────────────────────────┘
                                   │ Async ORM
   ┌───────────────────────────────▼───────────────────────────────┐
   │                   SQLite (aiosqlite) DB                       │
   │     meetings • decisions • staging_items • execution_tasks    │
   │               reminder_logs • auto-seed on startup            │
   └───────────────────────────────────────────────────────────────┘
```

- **Backend:** Python 3.11+, FastAPI, Uvicorn, SQLAlchemy (Async with `aiosqlite`), Pydantic v2.
- **AI Engine:** Google Gemini API (`google-genai` SDK using `gemini-2.5-flash` with Structured Outputs). Includes zero-downtime deterministic fallback parser.
- **Frontend:** React 18, Vite, CSS Modules / Custom Design Tokens (warm cream `#FBF6EF` palette).
- **Integrations:** GitHub Issues REST API, Slack/Discord Webhooks, Local Execution Receipts.

---

## 7. Local Setup Instructions

### Prerequisites
- Python 3.11+
- Node.js 18+ and `npm`

### 1. Clone & Configure Backend
```bash
# Clone the repository
git clone https://github.com/SouvikSaha2006/Meeting-To-Execution-Agent.git
cd Meeting-To-Execution-Agent

# Create python virtual environment
python -m venv venv
# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate

# Install dependencies
pip install -r backend/requirements.txt

# Configure environment
cp backend/.env.example .env
```

Edit `.env` (or pass as system environment variables):
```env
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash
DEMO_MODE=false
DATABASE_URL=sqlite+aiosqlite:///./veriflow.db
PORT=8000
```
*(Note: If no Gemini API key is provided or if `DEMO_MODE=true`, the backend automatically runs in deterministic mock mode with zero errors).*

Run the backend:
```bash
python run.py
# Server runs on http://localhost:8000
# OpenAPI Docs: http://localhost:8000/docs
```

### 2. Configure & Run Frontend
```bash
cd frontend
npm install

# Run Vite dev server
npm run dev
# Frontend runs on http://localhost:5173
```

---

## 8. Cloud Deployment Guide

### Deploy Backend to Render
1. Create a **New Web Service** pointing to this GitHub repository.
2. Select **Root Directory:** `.` (or `backend`).
3. Set **Build Command:** `pip install -r backend/requirements.txt`
4. Set **Start Command:** `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
5. Environment Variables:
   - `PYTHON_VERSION`: `3.11.9`
   - `DATABASE_URL`: `sqlite+aiosqlite:///./veriflow.db`
   - `DEMO_MODE`: `false`
   - `GEMINI_API_KEY`: *(Your Google AI Studio API key)*
   - `GEMINI_MODEL`: `gemini-2.5-flash`
*(Render's blueprint file `render.yaml` is pre-configured in the repository root for 1-click deployment).*

### Deploy Frontend to Vercel
1. Create a **New Project** on Vercel importing this GitHub repository.
2. Set **Root Directory:** `frontend`.
3. Framework Preset: **Vite**.
4. Environment Variables:
   - `VITE_API_URL`: `https://your-render-backend-url.onrender.com`
5. Click **Deploy**. *(The included `frontend/vercel.json` automatically configures SPA client-side routing).*

---

## 9. API Reference Summary

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/health` | System telemetry (DB status, Gemini readiness, Webhook status). |
| `POST` | `/api/meetings/ingest` | 4-stage pipeline: parse transcript, extract, audit conflicts, stage items. |
| `GET` | `/api/staging` | Query Human-in-the-Loop staging queue with filters (`conflicts`, `clarification`, `ready`). |
| `PATCH`| `/api/staging/{id}/resolve`| Resolve ambiguous fields or pick conflict strategy (`SUPERSEDE_OLD` / `KEEP_ORIGINAL`). |
| `POST` | `/api/staging/{id}/approve`| Promote staged item to active Decision or Execution Task (fires external dispatch). |
| `POST` | `/api/staging/approve-all-ready` | Bulk-approve all ready items in the queue. |
| `POST` | `/api/staging/{id}/reject` | Reject a staged item with recorded audit rationale. |
| `GET` | `/api/staging/{id}/blast-radius` | Detailed counterfactual delay and task impact simulation. |
| `GET` | `/api/tasks` | List all tasks on the Execution Board (`TODO`, `IN_PROGRESS`, `DONE`). |
| `PATCH`| `/api/tasks/{id}/status` | Update execution status with timestamp tracking. |
| `GET` | `/api/decisions` | Query active and superseded cross-meeting decision memory ledger. |
| `GET` | `/api/digest/weekly` | Per-person weekly execution digest grouped by owner. |
| `GET` | `/api/graph/lineage` | Node-and-edge dependency and decision lineage graph. |
| `GET` | `/api/analytics/health` | Execution velocity, meeting readiness score trend, and stale task count. |
| `POST` | `/api/actions/send-nudge` | Dispatch quote-backed follow-up notification via webhook. |
| `GET` | `/api/reminders/upcoming` | Scan for execution tasks with deadlines due within `<48h`. |
| `POST` | `/api/reminders/dispatch-all` | Trigger automated pre-deadline reminders across owners. |
| `POST` | `/api/memory/ask` | Natural language conversational query over cross-meeting decisions & transcripts. |
| `POST` | `/api/demo/seed` | 1-click database reset and demo scenario preloader. |

---

## 10. License

Built for the **Product Space Agentic AI Hackathon (2024)**. Open-source under the MIT License.
