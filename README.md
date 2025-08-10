# Job Interview Generator & Matching Engine

Generate, enrich, classify and browse interview questions starting from raw Job Descriptions (JDs). Combines:
- JD parsing (LLM powered) → structured role profile (title, skills, tools, responsibilities, experience)
- Skill graph construction & persistence
- Source crawling (StackExchange, GitHub lists, etc.)
- Question enrichment (classification: type, difficulty; metadata; rubric extraction)
- LLM question & Q/A generation for gaps
- Retrieval & filtering (by type, difficulty, source) via Gradio UI

---
## 1. Quick Start
```bash
# (Recommended) create & activate a virtual environment
python -m venv .venv && source .venv/bin/activate

# Install (editable)
pip install -e .

# Provide environment variables (see .env template below)
cp .env.example .env  # edit values

# Launch UI (installed console script)
jd2i-app
# or via python
python -m jd2interview
```

If you only want to test the mock standalone demo (older minimal version):
```bash
python app.py
```

---
## 2. Environment Variables (.env)
Create a `.env` file (loaded automatically by `python-dotenv`).
```
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini   # or any supported model; code default is gpt-5-mini placeholder
DB_URL=sqlite:///data/app.db
STACKEXCHANGE_KEY=your_stackapps_key_optional
# Optional tuning
OPENAI_TIMEOUT=90
OPENAI_MAX_RETRIES=2
CRAWL_SITES=stackoverflow,softwareengineering,dba,datascience,ai
CRAWL_PAGES=2
CRAWL_PAGE_SIZE=50
CRAWL_QUERY_HINT=interview
LLM_GEN_COUNTS={"Technical":10,"Coding":10,"Behavioral":10}
```
Note: A 401 AuthenticationError means the API key is missing, truncated, or invalid.

---
## 3. Project Layout
```
src/jd2interview/
  parsing/        # JD → structured fields (LLM)
  skills/         # Skill graph build, query, persistence, viz
  crawl/          # Role-aware crawling & pipelines
  enrich/         # Add metadata / classification to questions
  generation/     # LLM-driven Q & Q/A generation
  retrieval/      # Retrieval, availability filters, embeddings
  storage/        # Database (SQLAlchemy models / session helpers)
  ui/             # Gradio application
  utils/          # Config loading, shared helpers
scripts/          # Orchestration & batch utilities
```

---
## 4. Core Data Flow
1. Input JD text
2. `parsing.extract_structured` (LLM) → JSON (title, skills, tools, responsibilities, experience)
3. Build & persist skill graph (`skills.service`)
4. Crawl external sources (StackExchange, etc.) to collect real questions
5. Enrich each question (classification, difficulty, rubric)
6. Fill gaps with generated questions / answers (LLM)
7. Expose aggregated question set in UI with filtering & role context

---
## 5. Command Line Orchestrator
`python scripts/app.py -h` lists subcommands:
```
setup     # Initialize DB + skill index
crawl     # Crawl external sources for questions
generate  # LLM generate questions based on detected skills
index     # Build FAISS vector index for questions
ui        # Launch UI only
run       # End-to-end pipeline (setup + crawl + generate + index + UI)
```
Example end‑to‑end (no UI):
```bash
python scripts/app.py run --so-pages 2 --per-skill 2 --no-ui
```
Launch UI afterwards:
```bash
python scripts/app.py ui --port 7860
```

Installed console scripts (after `pip install -e .`):
```
jd2i      # same as python scripts/app.py (orchestrator) – if added
jd2i-app  # launches Gradio UI
```

---
## 6. Gradio UI Highlights
- Upload or paste JD → immediate parse + skill graph build
- View parsed role summary
- Dynamic counts of available question types & difficulty
- Filter by source: Web only / LLM only / both
- Per-question expandable metadata (rubric, answer, tags)
- Skill graph visualization (pyvis/networkx iframe)

---
## 7. LLM Integration
- Uses `langchain-openai` `ChatOpenAI(model=..., api_key=...)`
- Strict JSON coercion with fence stripping & fallback outer-object parse
- Low temperature (0.0) for deterministic schema extraction
- Replace `OPENAI_MODEL` with a model actually enabled for your account (the default `gpt-5-mini` is a placeholder)

Authentication troubleshooting:
- Ensure full key (starts with `sk-`) is exported or in `.env`
- Shell: `export OPENAI_API_KEY=sk-...` before launching
- 401 → invalid key; 404 / model_not_found → adjust OPENAI_MODEL

---
## 8. Database
Default: SQLite under `data/app.db` (configurable via `DB_URL`).
Stores: questions, metadata, answers, skill graph artifacts.
Initialize implicitly on first UI parse or via `setup` command.

---
## 9. Embeddings & Retrieval
Planned / partial components:
- FAISS index for question similarity (`scripts/build_embeddings.py` / retrieval module)
- Skill → question availability mapping
- Future: semantic reranking, answer scoring

---
## 10. Development
```bash
# Lint / format suggestions (add tooling as desired)
pip install ruff black
ruff check .
black .
```
Run smoke test:
```bash
python smoke_test.py
```
Run parsing quick test:
```bash
python -m jd2interview.parsing.extract
```

---
<!---

## 11. Testing JD Parsing Without an API Key
If no key is present the config prints a warning and LLM calls will fail fast. For offline dev you can stub or mock `extract_structured` or set a dummy implementation.

---
## 12. Roadmap (Short)
- Replace placeholder model name with stable defaults
- Expand crawler sources & rate limiting
- Advanced difficulty calibration using historical acceptance
- Semantic vector retrieval integration in UI
- Interview package export (PDF / JSON bundle)
- Automated evaluation rubric generation improvements

---
-->

## 11. Disclaimer
Do not use generated questions verbatim for high‑stakes interviews without human review.
