# Codebase Analysis: AI Maintenance Concierge Foundation

**This project is a useful foundation for the knowledge and troubleshooting side of an AI Maintenance Concierge. It does not currently provide a complete maintenance-management workflow.**

The review covered the repository structure, application paths, models, migrations, AI pipelines, frontend, deployment configuration, and test setup. The analysis was read-only; this report is the only file created afterward. This is a static assessment: services and tests were not run, deployed configuration was not verified, and a dependency vulnerability scan was not performed.

## TECH STACK

| Area | Implementation |
|---|---|
| Frontend | Next.js **14.2.18**, React **18.3.1**, TypeScript, App Router |
| UI and state | Tailwind CSS, TanStack Query/Virtual, Zustand, Lucide, React PDF |
| Backend | Python **3.11–3.13**, FastAPI, Uvicorn, Pydantic |
| Relational database | PostgreSQL, SQLAlchemy, asyncpg, Alembic migrations |
| Vector database | Qdrant; dense vectors and optional sparse vectors |
| Background processing | Celery workers and Beat; Redis broker/cache |
| File storage | Local filesystem or S3-compatible storage, including MinIO |
| AI integration | LangChain clients; Ollama, vLLM, OpenAI-compatible gateways, ForgeNode |
| Embeddings/reranking | Sentence Transformers, BGE-M3, configurable cross-encoders, optional GPU sidecar |
| Document processing | Docling, pypdf, pdfplumber, Tesseract, Poppler, python-docx, openpyxl |
| Authentication | Password login, Google OAuth, custom HMAC-signed JWTs, HttpOnly cookies, API keys |
| Authorization | Roles, factory access, job-position document ACLs, document release controls |
| Operations/testing | Docker Compose, nginx, Prometheus/Grafana, pytest, Playwright, evaluation suites |

LangGraph is declared as a dependency, but no active graph implementation was found. The agentic canary entry point explicitly returns disabled.

## CURRENT ARCHITECTURE

The repository separates these areas:

- `web/`: user interface, API clients, streaming, document viewer, offline caching.
- `src/spark/api/`: REST endpoints and middleware.
- `src/spark/services/`: chat orchestration and application logic.
- `src/spark/ingestion/`: parsing, trust checks, chunking, embeddings, indexing.
- `src/spark/retrieval/`: search, fusion, reranking, filtering, evidence selection.
- `src/spark/generation/`: grounded answers, citation and safety checks.
- `src/spark/db/`, `alembic/`: models and database evolution.
- `configs/`: model profiles, ingestion rules, prompts, retrieval settings.
- `gpu-sidecar/`, `deploy/`, `ops/`: inference and deployment infrastructure.
- `tests/`: unit, integration, contract, security, chaos, and evaluation coverage.

The backend is a modular application with separate background workers, rather than a collection of independent business services.

```text
Browser → Next.js → FastAPI → Chat orchestrator
                                  ├─ PostgreSQL: users, machines, documents, chat, ACLs
                                  ├─ Qdrant + PostgreSQL: knowledge retrieval
                                  ├─ Model backend: answer generation
                                  └─ Optional external PostgreSQL: analytical questions

Document upload → Storage → Celery → Parse/chunk/embed → PostgreSQL + Qdrant
```

The API includes `/api/v1` endpoints for authentication, factories, machines, documents, ingestion/jobs, chat, RAG queries, feedback, administration, external data sources, API keys, streams, and audit export.

## CURRENT USER FLOW

1. **Sign in:** Password or Google authentication establishes a session. Factory access, privacy acceptance, and job position influence available content.
2. **Select context:** The user opens chat or selects a machine/document scope.
3. **Ask:** The frontend submits a question, optionally with PDF/image attachments.
4. **Authorize and contextualize:** The backend checks access, loads chat history, merges session filters, and resolves follow-up references.
5. **Retrieve:** The system searches authorized knowledge using vectors, lexical matching, and industrial identifiers.
6. **Generate:** Selected evidence goes to the configured LLM, followed by citation, grounding, and safety checks.
7. **Persist and respond:** Chat messages and retrieval information are saved; the frontend receives streaming events or JSON, sources, and trust/degradation metadata.

For analytical questions, a configured external PostgreSQL source can supply SQL results. Compound questions can combine SQL results with document evidence.

**The database is consulted before generation as well as after it**—retrieval supplies the evidence the AI uses.

Document uploads follow a separate asynchronous flow: validate → store → queue → parse/OCR → scan → chunk → embed/index → publish the new document generation.

## IMPORTANT FILES

Paths below are relative to the repository root.

| File | Purpose |
|---|---|
| [Dockerfile.api](Dockerfile.api) | Builds the FastAPI image; installs Python dependencies and runs as a non-root user. |
| `Dockerfile.worker` | Worker image with Tesseract and Poppler for OCR. |
| `web/package.json`, `pyproject.toml` | Frontend/backend dependencies and commands. |
| `src/spark/main.py` | Application startup, validation, migrations, health checks, middleware. |
| `src/spark/api/v1/router.py` | Authoritative map of mounted API features. |
| `src/spark/core/config.py` | Runtime settings and deployment defaults. |
| `src/spark/core/security.py` | Principals, role checks, factory authorization. |
| `src/spark/db/models/org.py` | Factories, machines, components, aliases, users. |
| `src/spark/db/models/docs.py` | Documents, chunks, retrieval metadata. |
| [chat_orchestrator.py](src/spark/services/chat_orchestrator.py) | Chat routing, context, caches, persistence, streaming, SQL/RAG coordination. |
| `src/spark/retrieval/service.py`, `engine.py` | Main RAG service and search orchestration. |
| `src/spark/generation/pipeline.py` | Evidence-grounded generation and verification. |
| `src/spark/ingestion/orchestrator.py` | Coordinates staged ingestion. |
| `src/spark/workers/celery_app.py` | Queues and scheduled maintenance jobs. |
| `configs/llm_profiles.yaml`, `configs/ingestion/` | Model backends and document-specific processing. |
| `web/components/chat/gemini/ChatInterface.tsx` | Main chat interface; directory naming does not determine the model provider. |
| `web/components/documents/DocumentUploadPanel.tsx` | Document upload interface. |

`services/rag_service.py` is primarily a compatibility facade; the substantive implementation lives under `retrieval/` and `generation/`.

## AI/RAG IMPLEMENTATION

**Implemented features relevant to the prototype:**

| Capability | Current status |
|---|---|
| Machine management | CRUD, aliases, images, factory ownership, machine-linked documents |
| Component hierarchy | Database models exist; current chat code explicitly removes component scope |
| Maintenance guidance | Document-based troubleshooting, procedures, specifications, safety-related answers |
| Manuals/SOPs | Dedicated ingestion profiles and structure-aware chunking |
| Other knowledge | Drawings, datasheets, I/O mappings, inspections, near misses, training and enterprise policies |
| File upload | PDF, Word, Excel, text/Markdown, images and JSON parser support; accepted combinations depend on profile |
| Chat attachments | PDF/image extraction for a chat turn, separate from normal library ingestion |
| Error/machine data | Industrial identifiers and PLC tags in retrieval; external SQL for configured structured data |
| Operational maintenance | No current complete work-order, scheduling, assignment, inventory, or repair-case lifecycle |

The retrieval implementation includes:

- **BGE-M3 dense embeddings**, generally **1,024 dimensions** in model profiles.
- Qdrant collections with factory/document filters and generation lineage.
- PostgreSQL lexical search with Thai and industrial-token handling.
- Rank fusion and configurable reranking.
- Parent/child context, revisions, source page/sheet references.
- Cache revalidation, retries, circuit breakers, degradation reporting.
- Ingestion trust scans, quarantine, staged replacement, and reconciliation.

One important distinction: the `bge_m3` **sparse encoder uses tokenizer IDs with log term-frequency weights**. It is not BGE-M3’s learned sparse output. SPLADE is a stub.

Answer safeguards include citations, numeric grounding, entailment checks, and structured safety handling. However, some verification failures permit **flagged unverified output**, and a retrieval rejection is softened in the generation pipeline. Documentation claims of universally verified answers are too strong.

## REUSABLE COMPONENTS

The strongest candidates are:

- **Document ingestion:** parser registry, chunking strategies, provenance, retries, revisions.
- **Knowledge retrieval:** dense/lexical search, reranking, industrial identifier matching.
- **Grounded response handling:** citations, source viewer, trust metadata.
- **Machine registry:** equipment metadata, aliases, images, document associations.
- **Chat infrastructure:** sessions, streaming, attachments, feedback.
- **Storage abstraction:** local/S3 implementations.
- **Validation assets:** retrieval, authorization, ingestion, and streaming tests.

These are reusable subsystems, but they depend on shared settings, factory identifiers, ORM models, and production profiles. They are not isolated drop-in packages.

## COMPONENTS TO REWRITE

For a new product, the likely replacement or substantial adaptation areas are:

- Neo/Spark branding, onboarding, navigation, and factory-specific language.
- Factory/job-position permission assumptions if the tenancy model differs.
- Thai-heavy prompts, routing heuristics, terminology, and fallback messages.
- Machine/component scoping where finer equipment context is needed.
- Deployment profiles tied to existing gateways, Jetson hardware, and domains.
- External SQL validation and stored-secret protection.
- Legacy RCA, handover, alerts, analytics, and inventory frontend remnants.

A concierge’s maintenance-case lifecycle, technician assignment, scheduling, escalation, and closure tracking would be **new functionality**, not merely re-enabled screens.

## RISKS / PROBLEMS

1. **Weak protection of database credentials.**
   [secret_box.py](src/spark/core/secret_box.py) uses repeating XOR plus Base64, without authenticated encryption. It can also derive its key from the JWT secret.

2. **SQL authorization checks are insufficient.**
   [validator.py](src/spark/services/external_sql/validator.py) extracts tables with regex and checks whether scope text appears anywhere in SQL. That does not prove a factory filter constrains returned rows. Read-only transactions prevent writes, not unauthorized reads.

3. **“On-prem only” is configuration-dependent.**
   Checked-in profiles route chat, vision, and reranking to external gateways. Document excerpts or query results can leave the host network through those paths.

4. **Offline data can outlive logout.**
   Documents are cached by document ID without a user namespace. The logout implementation does not clear that cache, creating a shared-device confidentiality concern.

5. **Documented features exceed the active implementation.**
   [Migration 0057](alembic/versions/0057_rag_only_cleanup.py) drops work orders, inventory, alerts, and question analytics. Repair history remains in migration history, but no current repair-management API is mounted. RCA/handover clients reference absent endpoints; redirects point to an absent `/dashboard` page.

6. **Deployment gaps and drift.**
   `Dockerfile.api` lacks OCR binaries despite API-side attachment OCR. The worker image includes them. Docker builds use `pip install .` rather than the checked-in `uv.lock`; some images use `latest`.

7. **Unsafe development defaults if exposed.**
   Base Compose publishes infrastructure ports and includes default database/MinIO credentials. Redis/Qdrant authentication is not configured there. Production behavior must be assessed separately.

8. **High coupling and configuration burden.**
   Chat orchestration is approximately 2,500 lines and the RAG service approximately 2,400. Multiple profiles, compatibility layers, obsolete defaults, and disabled features increase extraction and debugging effort.

9. **Quality is not established by test presence.**
   There is substantial automated coverage, but tests were not executed in this review. CI treats mypy failures as non-blocking. Model availability, cold starts, quotas, and fallback behavior also affect reliability.

10. **Reuse rights need checking.**
    The repository’s [LICENSE](LICENSE) is proprietary and explicitly restricts unauthorized reuse.

## RECOMMENDED STARTING POINT

Use the **machine-linked document Q&A workflow** as the initial technical foundation:

**Machine → manual/SOP → question → cited troubleshooting guidance → feedback.**

Preserve the ingestion, retrieval, citations, and relevant tests together before attempting extraction. First establish a reproducible baseline with representative maintenance documents and resolve the identified security issues. Treat operational maintenance workflows as a separate addition.

This offers substantial reuse for a **maintenance knowledge concierge**, with considerably more work required for a concierge that manages maintenance execution.
