# Neo Chat Documentation

Neo Chat is scoped to document RAG: upload documents, index them, ask
questions with citations, and manage access inside one app.

## Start Here

**[HANDOVER.md](./HANDOVER.md) — the authoritative, code-grounded project
handover / onboarding document (dev + ops).** Read this first. Other docs
below may be older; when they disagree with HANDOVER.md or the code, trust
the code and HANDOVER.md.

**[DELIVERY_ACCEPTANCE.md](./DELIVERY_ACCEPTANCE.md) — the delivery &
acceptance package** (scope, acceptance tests, warranty/support, liability,
credential hand-off, sign-off). Read this alongside HANDOVER.md when the
question is "what counts as delivered" rather than "how does it work."

## Core Docs

| Document | Purpose |
| --- | --- |
| [HANDOVER.md](./HANDOVER.md) | **Authoritative handover: architecture, config, RAG/ingest pipelines, deploy, ops, secrets** |
| [DELIVERY_ACCEPTANCE.md](./DELIVERY_ACCEPTANCE.md) | **Delivery scope, acceptance tests, warranty, liability, credential hand-off, sign-off** |
| [delivery-forms/](./delivery-forms/) | **A4 Thai HTML forms** — client checklist + formal acceptance agreement (print to PDF) |
| [../README.md](../README.md) | Project overview and quick start |
| [user-guide.md](./user-guide.md) | Operator user guide |
| [admin-guide.md](./admin-guide.md) | Admin guide |

## Engineering Reference

| Document | Purpose |
| --- | --- |
| [architecture.md](./architecture.md) | System architecture |
| [architecture/hybrid_retrieval_v2.md](./architecture/hybrid_retrieval_v2.md) | Retrieval architecture |
| [architecture/import_spine_v2.md](./architecture/import_spine_v2.md) | Ingestion architecture |
| [api-overview.md](./api-overview.md) | API map |
| [public-api-integration.md](./public-api-integration.md) | Integrating a third party against the API |
| [operations-guide.md](./operations-guide.md) | Install, config, backup, monitoring |
| [demo_playbook.md](./demo_playbook.md) | Scripted walkthrough for demos |
| [../web/README.md](../web/README.md) | Frontend guide |
| [../web/docs/ARCHITECTURE.md](../web/docs/ARCHITECTURE.md) | Frontend architecture |
| [../web/docs/DESIGN_SYSTEM.md](../web/docs/DESIGN_SYSTEM.md) | UI conventions |

## Current App Scope

- Chat answers are grounded in uploaded documents.
- Retrieval uses document chunks from Qdrant and PostgreSQL.
- Admin tools cover users, job positions, permissions, feedback, and document release.
- Upload supports generic knowledge and policy/manual-style documents.

Keep new work inside this document RAG scope unless the product direction is
explicitly changed.
