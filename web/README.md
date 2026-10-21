# Neo Chat Web Frontend

Next.js frontend for the document RAG app.

## Current Routes

| Route | Who | What |
| --- | --- | --- |
| `/chat` | everyone | document-grounded Q&A |
| `/documents` | everyone | document library |
| `/upload` | write access | document upload and ingest jobs |
| `/feedback` | write access | report a wrong or incomplete answer |
| `/machines` | write access | machine registry |
| `/admin` | admin | users, job positions, permissions, feedback |
| `/admin/factories` | admin | factory configuration |
| `/system-admin` | admin | operational health — traffic, latency, ingest, dependency status |
| `/account`, `/login`, `/signup`, `/privacy` | everyone | account and auth |

## Quick Start

```bash
cd web
npm install
cp .env.mac-thin.example .env.local
npm run dev
```

The backend defaults to `http://127.0.0.1:8000`.

## Scripts

| Script | Purpose |
| --- | --- |
| `npm run dev` | Development server |
| `npm run build` | Production build and type check |
| `npm run start` | Serve production build |
| `npm run lint` | Lint |
| `npm run test` | Unit tests |
| `npm run test:e2e` | Playwright tests |

## Structure

```text
app/          App Router routes
components/   Chat, documents, upload, admin, auth, and UI components
hooks/        React Query and URL-state hooks
lib/          API client, chat streaming, auth, document helpers
stores/       Zustand stores
contexts/     Chat session context
docs/         Frontend architecture and design docs
```

## Related Docs

| Document | Purpose |
| --- | --- |
| [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md) | Frontend architecture |
| [docs/DESIGN_SYSTEM.md](./docs/DESIGN_SYSTEM.md) | UI conventions |
| [../docs/HANDOVER.md](../docs/HANDOVER.md) | Full project handover |
| [../README.md](../README.md) | Project overview |
