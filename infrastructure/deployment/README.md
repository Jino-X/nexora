# Deployment assets

* Container images: `infrastructure/docker/*.Dockerfile` (api, worker = api image, voice-agent, speech, web)
* Local stack: `docker-compose.yml` at the repo root (profiles `llm`, `postgres`, `voice`, `speech`)
* Plain-Postgres shim for the Supabase migrations: `infrastructure/docker/postgres-init/`
* Migration and RLS verifier: `infrastructure/scripts/verify-migrations.sh`
* Environment bootstrap: `infrastructure/scripts/bootstrap-env.py`

The AWS / Vercel / Supabase / LiveKit Cloud runbook and cost assumptions are in
[docs/deployment.md](../../docs/deployment.md). Infrastructure-as-code (Terraform/CDK) is not
included yet.
