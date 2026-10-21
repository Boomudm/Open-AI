# Web Architecture

The frontend is a Next.js App Router app for document RAG.

Current routes:

- `/chat`
- `/documents`
- `/upload`
- `/admin`
- `/account`
- `/login`
- `/signup`
- `/privacy`

The data layer uses the typed API client in `web/lib/api`, React Query for
server state, Zustand for chat state, and SSE for streaming chat answers.
