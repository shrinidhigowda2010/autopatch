# FixPilot

Autonomous bug detection and repair. Find it. Fix it. Prove it.

A developer uploads Python code. FixPilot scans it with real static tools and, when a key is set, Google Gemini. Each bug report says what triggers the bug and why. A minimal patch is proposed as a unified diff and a side-by-side before/after. Tests run in a sandbox before and after the patch. Nothing is written into the project until a person accepts it.

## Problem

Students and junior developers can see that a program is wrong and still not know which line is at fault, why that line fails, or whether a fix broke something else. The marks calculator in the brief is the running example: it accepts negative marks and marks over 100, and it crashes when the list is empty. FixPilot is built to catch that class of mistake, explain it in plain language, patch only the lines that need to change, and show the test that proves it.

## Solution

Five steps, in the sidebar:

1. **Upload** almost anything: a code file, a zip/tar archive, a PDF, a Word doc, a Jupyter notebook, a screenshot of code, pasted code, or a link. The app shows the file tree, languages, dependencies, important files, and an import graph. See [What you can upload](#what-you-can-upload).
2. **Scan** with two layers. Layer 1 is pylint, pyflakes, bandit, and a secret scanner. Layer 2 is Gemini (`GEMINI_API_KEY`), with a second model, retries, and a timeout. Findings are merged. If Gemini is missing, the AI engine stays on standby and static analysis plus project knowledge continue without a banner.
3. **Explain** the root cause: the input that triggers the bug, and why the code does the wrong thing. Student mode shortens that. Kannada and Hindi are available for the bundled rules, and via Gemini when a key is set.
4. **Fix** with a small patch. The screen shows a unified diff and the before (red) and after (green) code. Accept or reject is required. "Apply all safe fixes" only applies high-confidence patches whose tests passed.
5. **Test** existing tests, then generated edge cases (normal, minimum, maximum, invalid), before the patch and after it, then the full suite as a regression check. Progress streams over server-sent events. The code runs in a temp directory with CPU, memory, file-size, and wall-clock limits.

### AI Agent Assistant

**FixPilot Assistant** (`/p/{projectId}/assistant`) is a project-scoped chat. The left sidebar lists past conversations (stored per user / Coder ID). The right panel shows the file tree and live bug list — clicking a bug attaches it as context. Messages stream token-by-token over SSE; tool steps appear as small cards (scan, explain, propose fix, run tests, show diff, search). When the agent proposes a fix, a diff card offers Approve / Reject / Edit and plugs into the same permission and audit flow as the Fix page — nothing is written without Approve. Quick-prompt chips and English / Kannada / Hindi are supported. Secrets are redacted before anything is sent to Gemini; if Gemini is down, answers fall back silently to the static findings.

Every bug report has the same six sections: bug details, root cause, suggested patch, test results, severity and confidence, and change history. Low confidence is marked "needs human review".

## Where each requirement lives

| Requirement | Where it is implemented |
| --- | --- |
| Upload files, archives, PDFs, docs, notebooks, screenshots, pasted code, or links | `backend/app/ingest/` (`files.py`, `formats.py`, `links.py`, `github.py`), Upload page |
| File tree, languages, dependencies, important files, import graph | `backend/app/ingest/structure.py`, Scan page |
| Layer 1: pylint, pyflakes, bandit, secret scanning | `backend/app/analysis/static_runner.py`, `secrets.py` |
| Layer 2: Gemini for logic errors, edge cases, wrong outputs, crashes | `backend/app/llm/gemini.py` |
| Fallback model, retries, timeouts | `Gemini.analyze_with_gemini`, `GEMINI_FALLBACK_MODEL`, `GEMINI_TIMEOUT_S` |
| Merge and dedupe findings | `backend/app/analysis/merge.py` |
| Root cause in plain English, including the trigger | `backend/app/analysis/catalog.py`, Explain and bug pages |
| Student mode | Header toggle, `frontend/src/lib/format.ts` |
| Kannada and Hindi | Stored on each rule; `POST /api/bugs/{id}/translate` calls Gemini if a stored line is missing |
| Minimal patch, unified diff, side-by-side red/green | `backend/app/patching/`, Fix page, `DiffView.tsx` |
| Existing tests, generated normal/min/max/invalid tests, before and after, regression | `backend/app/testing/generate.py`, `testing/service.py` |
| Sandbox: temp dir, CPU, memory, time, truncated output | `backend/app/sandbox/runner.py` |
| Live test progress | `GET /api/test-runs/{id}/events` (SSE), Test page |
| Severity, impact, calibrated confidence, "needs human review" | `catalog.py` (`REVIEW_BELOW = 0.8`), bug report, dashboard |
| Dashboard charts | Dashboard page, recharts |
| Accept or reject every patch; nothing applied without approval | `services.decide_patch`, Fix page |
| Auto-Correct Mode (ask / auto-safe), rollback, decision log | Fix page, `approve`/`reject`/`edit`/`rollback-*`, `workspace_versions` |
| Login, Coder ID, JWT, guest mode, per-user history | `auth.py`, `auth_routes.py`, Login/Register/Profile |
| FixPilot Assistant chat, tools, SSE, secret redaction | `agent/`, `assistant_routes.py`, Assistant page |
| "Apply all safe fixes" only for high-confidence patches whose tests passed | `services.apply_safe` |
| SQLAlchemy, SQLite default, Postgres via `DATABASE_URL` | `backend/app/db.py`, `models.py` |
| History of scans, bugs, patches, tests, decisions | `history_events` table, History page |
| Export fixed project zip, report PDF, report JSON | `backend/app/exporting/report.py` |
| Bug report fields: details, root cause, patch, tests, severity and confidence, change history | `GET /api/bugs/{id}`, bug page headings |
| Marks calculator (negative and over-100 marks) | `samples/marks_calculator/` |
| 5–8 buggy projects with ground truth | `samples/` (8 projects, 12 bugs) |
| Measured detection, fix success, false positives | `benchmark/run_benchmark.py`, `benchmark/results/latest.json`, Benchmark page |
| One-click demo from the home page | Home page sample cards, `?auto=1` starts the scan |
| Silent AI standby when Gemini is missing or fails | `analysis/pipeline.py`, `samples/cache.json` |
| Upload size limits, rate limiting, validation, structured logs | `ingest/files.py`, `limiter.py`, `logging_config.py` |
| pytest, frontend tests, GitHub Actions | `backend/tests/`, `frontend/src/**/*.test.ts(x)`, `.github/workflows/ci.yml` |
| One Dockerfile, Render free tier | `Dockerfile`, `render.yaml` |

## What a strong solution shows

| What judges should be able to see | Where |
| --- | --- |
| The whole workflow, not a chat box | Sidebar steps Upload → Scan → Explain → Fix → Test |
| A real static layer plus a model layer, and a demo that still runs if the model is down | Scan page banner, tool notes, cached model chip |
| An explanation of the trigger, not only a line number | Root cause and "What triggers it" on the bug page |
| A small patch and a human decision | Fix page, Accept / Reject, history event |
| Proof the patch worked and did not break existing tests | Test page: existing before, generated before, generated after, regression |
| Severity and a confidence that can say "a person should check this" | The stock-total sample is medium confidence and flagged for review |
| Numbers from a run, with the method written down | Benchmark page and the method paragraph in `benchmark/results/latest.json` |
| The marks-calculator example from the problem | Home card "Marks calculator", `samples/marks_calculator` |

## Architecture

```mermaid
flowchart LR
  UI["React UI"] --> API["FastAPI"]
  API --> Ingest["Ingest"]
  API --> Scan["Scan pipeline"]
  Scan --> Static["pylint, pyflakes, bandit, secrets, AST rules"]
  Scan --> Gemini["Gemini, fallback model"]
  Scan --> Cache["Sample cache if Gemini is down"]
  API --> Patch["Patchers"]
  API --> Sandbox["Sandbox pytest"]
  API --> DB["SQLite or Postgres"]
```

More detail is in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). The three-minute demo is in [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md). Interactive API docs are at `/docs` when the server is running.

## Benchmark results

Measured by `python benchmark/run_benchmark.py` on 19 Nov 2026. Gemini was not called. Eight projects, twelve ground-truth bugs.

| Metric | Result |
| --- | --- |
| Detection rate | 100% (12 / 12) |
| Fix success rate | 100% (12 / 12) |
| False positives | 0 |

Projects: marks calculator, bank balance, login SQL injection, off-by-one, division by zero, hardcoded secret, mutable default argument, skipped first stock row. The raw rows are in `benchmark/results/latest.json`. Re-run the script or the Benchmark page to measure again. The pytest suite asserts these rates, so a regression fails CI.

Style notes from pylint (a long line, a suggestion to use `enumerate`) are shown in the UI and are not counted as false-positive bugs. That choice is written in the benchmark method string.

## Authentication & Coder ID

Accounts are optional. Judges can use **Continue without account** on the Login page; guest projects are not linked to a durable profile. Signed-in users get a unique **Coder ID** like `FP-CODER-7F3K2`. Accounts made before the rename keep their `AP-CODER-…` ID, and either prefix works at sign-in.

- Register / login: `POST /api/auth/register`, `POST /api/auth/login` (email **or** Coder ID + password). Passwords are bcrypt-hashed; JWT access tokens last 24h (`JWT_SECRET`).
- `GET /api/auth/me` returns profile stats (scans, bugs found, patches accepted/rejected, member since). `POST /api/auth/logout` tells the client to discard the token.
- Every project, scan, and patch decision stores `user_id` when you are logged in. History and project lists show only your data; admins see everything.
- Login attempts are rate-limited. Plain passwords are never stored or logged.

## Auto-Correct Mode (Human-in-the-Loop)

AI and rule-based patches are proposals until a person decides. That matters because a “safe-looking” rewrite can still break auth, money, or tests.

On the Fix page, choose **Manual**, **Ask Every Fix** (default), or **Auto for Safe Fixes** (confidence ≥ 90%, risk = safe, tests passing). Each fix shows a permission card: diff, why/what, risk badge, and Approve / Reject / Edit / Skip / Ask AI. Approved fixes write only the working copy; the original upload stays intact. After each approve, tests re-run — failure triggers auto-rollback. Undo last / Rollback all walk a version timeline (v0 → v1 → …). Rejections with a reason can ask Gemini for an alternative. The Decision Log and export PDF/JSON record every choice against your Coder ID.

## Tech stack

- Backend: Python 3.12, FastAPI, SQLAlchemy, pydantic, passlib/bcrypt, python-jose, pylint, pyflakes, bandit, httpx, fpdf2, pytest
- Model: Google Gemini (`gemini-2.5-flash`, fallback `gemini-2.0-flash`)
- Frontend: React, Vite, TypeScript, Tailwind, recharts
- Data: SQLite by default, Postgres when `DATABASE_URL` is set
- Deploy: one Docker image, Render web service

## Prove it: Break-It, the Debate Room, and the Repair Race

Every proposed patch on the Fix page has a **Prove it** strip with two tools.

- **🛡 Break-It attack** (`POST /api/patches/{id}/attack`) builds 10–15 hostile inputs for the patched function: empty, None, negative, huge, NaN, unicode, wrong types. Gemini suggests some and a rule-based generator fills the rest. Gemini's inputs must pass a literal-only whitelist first. The old and new code both run in the sandbox, and an animated scoreboard shows "Old code failed X/N · New code survived Y/N". A crash, a hang, or quietly accepting input the fix now refuses all count as a failure. A deliberate `raise`, or a `TypeError` on a wrong-type input, counts as a safe refusal.
- **⚖️ AI Debate Room** (`POST /api/patches/{id}/debate`, streamed) runs three rounds where Breaker attacks the fix with an edge case and Fixer answers. A Judge then rules **Safe** or **Needs changes** with a confidence %. Each turn is its own Gemini call, using the faster model first. If Gemini drops out, the remaining turns and the verdict are built from the test results and the Break-It scoreboard.
- **🏁 Live Repair Race** (`/race`, `POST /api/race`, streamed) is a full-screen page with a big stopwatch. Paste buggy code and the real pipeline runs: scan, then the patch, then edge-case tests run on the original and patched code (or Break-It attacks when there are no tests for that rule). The stages light up as **Bug found → Fixed → Verified**, with confetti at the end.

## What you can upload

The Upload page has three tabs, and Ctrl+V works anywhere on the page (an image uploads, a link opens the link tab, text opens the paste tab).

| Input | How FixPilot reads it |
| --- | --- |
| Code and text: `.py .js .ts .jsx .tsx .java .c .cpp .h .cs .go .rb .php .kt .swift .rs .sql .sh .html .css .json .yaml .xml .md .txt` and more | Used as is. The language comes from the extension, or from the content when there is none. |
| Archives: `.zip .tar .tar.gz .tgz` | Unpacked with path-traversal, file-count and expanded-size checks. Symlinks and devices in tar files are skipped. |
| PDF | Text is extracted with `pypdf`, and code blocks are split from the prose. Scanned PDFs are read from their page images. |
| Word `.docx` | Paragraph text is read, then split into code blocks like a PDF. |
| Jupyter `.ipynb` | Code cells are joined into one `.py` file. Shell commands and magics become comments. |
| Screenshots: `.png .jpg .webp .gif .bmp` | Gemini vision transcribes the code. Without a key, the page asks you to paste the code instead (Tesseract is used if it is installed). |
| Pasted code | Saved as a file. The name is guessed from the language if you leave it blank. |
| Links | A GitHub repo (zip download), a GitHub file page (turned into its raw link), a Gist, a Pastebin page, or any public `http(s)` file. |

PDFs, documents, notebooks and screenshots open in a preview first, so you can fix anything that was read wrong before clicking **Scan now**. Python gets the full pipeline (static tools and sandbox tests). Other languages get Gemini analysis only, and the UI labels them "AI analysis only, not verified by tests". Anything else gets a clear "can't read that yet" message (HTTP 415).

## Security and the sandbox

- Uploads are capped (8 MB by default). Zips are checked for path traversal and for a zip bomb (file count and uncompressed size).
- GitHub imports accept only `https://github.com/owner/repo`. The download is capped at 8 MB. No credentials are sent.
- Uploads are identified by their content, not just their extension: a `.png` that is not an image, or a binary file named `.py`, is rejected.
- Links must be `http` or `https`. The host is resolved and refused if any address is loopback, private, link-local or reserved, and the check runs again on every redirect. Downloads have timeouts and a byte cap.
- Secrets are redacted from source code before it is sent to Gemini. Screenshots are sent as images, so avoid screenshots that show real keys.
- Uploaded files are only parsed, never run. Code runs only inside the test sandbox.
- User code runs with `subprocess` in a temp copy. The child does not receive `GEMINI_API_KEY`, `DATABASE_URL`, or other secret environment variables. CPU, address-space, file-size, and wall-clock limits are set. Output is truncated.
- Network is not a separate namespace. Isolating the network with `unshare` needs privileges this service does not assume. The child still has no API keys.
- Patches are not written until Approve/Accept, or until "Apply all safe fixes" after tests have passed. Auto-Correct Mode asks before each change and rolls back if post-fix tests fail.
- Set a strong `JWT_SECRET` in production. Auth tokens are Bearer JWTs stored in the browser.
- Secrets found in a scan are stored as findings. Do not upload a real production secret.

## Limitations

- Python is the language the rules, fixers, and generated tests understand well. JavaScript and TypeScript are ingested, shown in the tree, and secret-scanned. They are not patched.
- The fixers cover the bug classes in the benchmark (range checks, empty division, zero division, deposits and withdrawals, SQL f-strings, hardcoded secrets, mutable defaults, two off-by-one shapes). A novel logic bug needs Gemini, and the patch may still need a person.
- The skipped-first-row rule is deliberately low confidence. Some loops start at 1 on purpose. It is flagged for human review and is not auto-applied.
- Confidence numbers are set by the rule, not learned from a large labelled set. They are calibrated against these samples: the rules that are structural (mutable default, SQL interpolation) sit higher than the heuristic ones.
- Gemini model names change. If both models fail, the scan continues on the static layer.
- The sandbox cannot stop every abuse. It is a limit around a student program, not a hardened multi-tenant jail.

## Run it locally

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pytest
cd ../frontend
npm ci
npm test
npm run build
cd ../backend
.venv/bin/uvicorn app.main:app --reload --port 8000
```

Open http://127.0.0.1:8000 . For frontend hot reload, run `npm run dev` in `frontend/` and open http://127.0.0.1:5173 . The dev server proxies `/api` to port 8000.

Copy `.env.example` to `.env` if you want Gemini. Leave `GEMINI_API_KEY` empty to run with static analysis and project knowledge (AI engine: standby).

```bash
python benchmark/run_benchmark.py
```

## Deploy on Render

The repo includes `render.yaml` and a Dockerfile that builds the frontend and serves it from FastAPI. Create a Render web service from this repo (free plan). Set `GEMINI_API_KEY` and `JWT_SECRET` in the dashboard. Set `DATABASE_URL` only if you attach Postgres; otherwise the service uses SQLite on local disk, which resets when the free instance sleeps. The health check is `/api/health`.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Liveness, whether Gemini is configured |
| POST | `/api/auth/register` | Create account; returns Coder ID + JWT |
| POST | `/api/auth/login` | Email or Coder ID + password |
| GET | `/api/auth/me` | Profile + stats (Bearer token) |
| POST | `/api/auth/logout` | Client discards token |
| GET | `/api/auth/history` | Projects owned by the signed-in user |
| GET | `/api/samples` | Bundled demos |
| POST | `/api/projects/upload` | Any supported file or archive; creates a project |
| POST | `/api/projects/extract` | Any supported file; returns editable files for the preview, no project |
| POST | `/api/projects/paste` | `{ "name": "", "origin": "paste", "files": [{ "path": "main.py", "content": "..." }] }` |
| POST | `/api/projects/link` | `{ "url": "https://github.com/owner/repo/blob/main/app.py" }` |
| POST | `/api/projects/github` | `{ "url": "https://github.com/owner/repo" }` |
| POST | `/api/projects/sample` | `{ "sample_id": "marks_calculator" }` |
| GET | `/api/projects/{id}` | Tree, languages, dependencies, graph |
| POST | `/api/projects/{id}/scans` | Run both layers |
| GET | `/api/bugs/{id}` | Full bug report |
| POST | `/api/bugs/{id}/translate` | `{ "language": "kn" }` or `"hi"` |
| POST | `/api/patches/{id}/decision` | `{ "action": "accept" }` or `"reject"` |
| POST | `/api/patches/{id}/approve` | Approve + re-test; auto-rollback on failure |
| POST | `/api/patches/{id}/reject` | Reject; optional reason + try-another |
| POST | `/api/patches/{id}/edit` | Apply edited after-code |
| POST | `/api/patches/{id}/skip` | Skip for now |
| POST | `/api/patches/{id}/ask-ai` | Chat about one fix |
| POST | `/api/scans/{id}/apply-safe` | High-confidence patches whose tests passed (`dry_run` supported) |
| POST | `/api/projects/{id}/rollback-last` | Undo last applied fix |
| POST | `/api/projects/{id}/rollback-all` | Restore original upload (v0) |
| GET | `/api/projects/{id}/versions` | Version timeline |
| GET | `/api/projects/{id}/decision-log` | Audit trail of patch decisions |
| POST | `/api/projects/{id}/tests` | Start a proof run |
| GET | `/api/test-runs/{id}/events` | Server-sent events |
| GET | `/api/projects/{id}/history` | Change history |
| GET | `/api/projects/{id}/dashboard` | Counts for the charts |
| GET | `/api/projects/{id}/export/json` | Report JSON (includes decision log) |
| GET | `/api/projects/{id}/export/pdf` | Report PDF |
| GET | `/api/projects/{id}/export/zip` | Workspace zip |
| POST | `/api/benchmark/run` | Re-measure the samples |
