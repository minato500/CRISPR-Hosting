# Vercel deployment

This repository is configured as one **Vercel Services** project containing
only the main application:

| Public path | Vercel service | Source |
|---|---|---|
| `/` | `dashboard` | `frontend/` |
| `/api/*` | `api` | `backend.app.main:app` |

The dashboard is built with Vite and FastAPI runs in Vercel's native Python
runtime. They are released atomically by the root `vercel.json`. API requests
stay on the same origin, so the browser does not need a public backend URL or
cross-origin credentials. No Docker image is built on Vercel.

The `bug-bounty/` and `crispr_products/` applications are intentionally not
part of this Vercel deployment. They remain available for local or independent
deployment without affecting the main application.

## Important Compose differences

Vercel does not execute `docker-compose.yml` and has no `docker compose up`
equivalent. FastAPI runs as a stateless, autoscaling Function rather than a
permanent server. See Vercel's current guides for
[FastAPI](https://vercel.com/docs/frameworks/backend/fastapi) and
[Docker Compose migrations](https://vercel.com/kb/guide/docker-compose-concepts-on-vercel).

Consequently:

- PostgreSQL cannot run from the Compose `db` service or its local volume. Use
  managed PostgreSQL (for example Neon or Supabase from Vercel Marketplace).
- Neo4j cannot run from the Compose `neo4j` service or its local volume. Set
  `NEO4J_ENABLED=false`, or supply the TLS URI and credentials of a managed
  Neo4j instance such as Aura.
- `backend.workers.main` is a permanent polling process and cannot be a Vercel
  Function. Run that one process on an always-on container platform,
  or migrate the database queue to Vercel Queues before relying on connector
  sync, analysis, report-generation, or model-governance jobs. The dashboard
  and synchronous API routes still live in the one Vercel deployment.
- Local `./data` is bundled into the API Function as read-only application
  data; it is not persistent storage.

## 1. Create the project and database

Import the repository root in Vercel and select **Services** as the framework.
Do not select `frontend/` as the project root; the root `vercel.json` owns all
service builds and routing.

Attach a PostgreSQL provider from the Vercel Marketplace. For Neon, the CLI
flow is:

```bash
vercel link
vercel install neon
```

The backend already accepts a standard `DATABASE_URL`. If the provider injects
a differently named URL, copy its pooled PostgreSQL connection string into a
project environment variable named `DATABASE_URL`.

## 2. Configure environment variables

Set these for Production and, with separate data and secrets, Preview:

```dotenv
DATABASE_URL=postgresql://USER:PASSWORD@HOST/DATABASE?sslmode=require
DB_CONNECT_TIMEOUT_SECONDS=5
VERCEL_SUPPORT_LARGE_FUNCTIONS=1

AUTH_SECRET=GENERATE_A_LONG_RANDOM_VALUE
ACCESS_TOKEN_LIFETIME_MINUTES=30
INTEGRATION_ENCRYPTION_KEY=GENERATE_A_STABLE_FERNET_KEY
SECURITY_ADMIN_EMAIL=security@example.com
SECURITY_ADMIN_PASSWORD=GENERATE_A_STRONG_PASSWORD
ALLOW_PUBLIC_REPORTER_REGISTRATION=false

CRISPR_DATA_MODE=live
DEMO_AUTO_SEED=false
API_DOCS_ENABLED=false

NEO4J_ENABLED=false
OMP_NUM_THREADS=1
OPENBLAS_NUM_THREADS=1
MKL_NUM_THREADS=1
```

For an isolated demo, use `CRISPR_DATA_MODE=demo` and
`DEMO_AUTO_SEED=true`. If Neo4j is enabled, also set `NEO4J_URI` (normally a
`neo4j+s://` managed endpoint), `NEO4J_USER`, `NEO4J_PASSWORD`, and optionally
`NEO4J_DATABASE`.

Add `LLM_ENABLED`, `LLM_BASE_URL`, `LLM_API_KEY`, and the NVD variables from
`.env.example` only when those integrations are required. Do **not** define
`VITE_SIH_*_PASSWORD` in Vercel: every `VITE_*` value is public browser code.

Because all public traffic uses one origin, `CORS_ORIGINS` is not required for
the Vercel web applications. Add an exact HTTPS origin only if another website
must call the API directly.

## 3. Apply database migrations

The FastAPI service deliberately does not migrate on cold start. Apply the
migration once against Neon from a trusted workstation or CI environment before
the first deployment and whenever a migration is added:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
DATABASE_URL='postgresql://...' .venv/bin/alembic upgrade head
```

Avoid putting a real production URL in shared shell history. CI should inject
`DATABASE_URL` from its secret store.

## 4. Deploy and verify

Deploy from the repository root:

```bash
vercel deploy
vercel deploy --prod
```

Then verify the shared domain:

```bash
curl -fsS https://YOUR_DOMAIN/api/health/ready
curl -I https://YOUR_DOMAIN/
```

The readiness response must say `database: connected` and report schema
revision `0008_remediation_delivery_risk`.

For local Vercel routing tests, install the Vercel CLI and run `vercel dev -L`
from the repository root. Continue using
`docker compose up --build` when testing the original stateful local stack.

## Background worker production choices

Choose one before enabling queued features:

1. **Minimal migration:** deploy the existing `python -m backend.workers.main`
   command to an always-on container host. Give it the same `DATABASE_URL`,
   `INTEGRATION_ENCRYPTION_KEY`, connector settings, and model-thread limits as
   the Vercel API.
2. **Vercel-native:** publish each queued database job to
   [Vercel Queues](https://vercel.com/docs/queues) and convert the worker into
   queue-triggered, idempotent functions. This is a code migration, not a
   deployment setting; do not remove the PostgreSQL job records until retries
   and audit evidence have equivalent durable behavior.
