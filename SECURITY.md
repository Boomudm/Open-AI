# Security Policy

Neo Chat is deployed in factory environments where incorrect answers or data leaks carry real operational and safety risk. We take security reports seriously.

## Supported versions

| Version | Supported |
|---------|-----------|
| Latest release on `main` | ✅ |
| `develop` integration branch | ✅ (pre-release fixes land here first) |
| Older tagged releases | ⚠️ Critical fixes by agreement only |

## Reporting a vulnerability

**Please do not open a public GitHub issue for security vulnerabilities.**

### Preferred: GitHub Private Security Advisories

1. Go to the [Security tab](https://github.com/CPF-Chula-CEDT-2026/spark/security) on this repository.
2. Click **Report a vulnerability**.
3. Describe impact, affected components, and reproduction steps.

### Alternative contact

If you cannot use GitHub Advisories, contact the maintainers through your organization's established security channel for the CPF-Chula-CEDT-2026 project.

Include:

- Summary of the issue and potential impact
- Steps to reproduce (or proof-of-concept)
- Affected version / branch / commit
- Suggested remediation (if known)

## Response expectations

| Stage | Target |
|-------|--------|
| Acknowledgement | Within 3 business days |
| Initial triage | Within 7 business days |
| Fix or mitigation plan | Depends on severity; critical factory-safety issues prioritized |

We will coordinate disclosure timing with you before any public announcement.

## Scope

**In scope**

- Authentication / authorization bypass (JWT, factory RBAC, IAM ACL)
- SQL injection or unsafe Text-to-SQL paths
- Cross-factory data leakage in RAG retrieval or API filters
- Remote code execution in ingest parsers or file upload paths
- Secrets committed to the repository or logged in production

**Out of scope**

- Social engineering against plant operators
- Issues in optional sidecar repos cloned locally (`ragflow/`, etc.) — report upstream
- Denial-of-service without demonstrated impact on factory safety
- Findings in `.env` files that were never committed

## Secure deployment reminders

- Rotate `JWT_SECRET` before production; treat token invalidation as expected on rotation.
- Set `APP_ENV=production` and `AUTH_REQUIRED=true` on factory hosts.
- Never expose Ollama, Qdrant, or Postgres ports beyond the factory LAN.
- Plant documents under `/data/` must remain gitignored — see [`.gitignore`](./.gitignore).

## Automated scanning

This repository runs [CodeQL](https://github.com/CPF-Chula-CEDT-2026/spark/actions/workflows/codeql-analysis.yml) on `develop` and `main`, and [Dependabot](https://github.com/CPF-Chula-CEDT-2026/spark/security/dependabot) for dependency updates.

CodeQL analysis executes in CI on every PR. Upload to the GitHub **Security** tab requires **GitHub Advanced Security** on private repositories — enable it in repository settings to activate SARIF upload (set `upload: true` in the workflow).

---

See also: [CONTRIBUTING.md](./CONTRIBUTING.md) · [GOVERNANCE.md](./GOVERNANCE.md) · [CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md)
