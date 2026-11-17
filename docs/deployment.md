# Deployment

## Topology

| Component | Recommended host | Notes |
| --- | --- | --- |
| Web (`apps/web`) | Vercel (root `apps/web`, pnpm) or any Node 20.9+ host / container (`web.Dockerfile`, standalone) | Set `NEXT_PUBLIC_*` at build time |
| API (`services/api`) | AWS ECS Fargate or App Runner behind an ALB (`api.Dockerfile`) | **One task**, or add Redis for run buffers and rate limits (below). Health: `/health`, readiness: `/health/ready` |
| Automation worker | ECS Fargate service, same image, `python -m app.automations.worker` | Set `RUN_SCHEDULER_IN_API=false` on the API. Several workers are safe (DB leases) |
| Voice agent | ECS on EC2 or Fargate with steady CPU (`voice-agent.Dockerfile`, `start`) | Long-lived WebSocket to LiveKit; scale on CPU. Each process runs VAD + turn detector |
| Speech server | EC2 GPU instance (g5/g6/g6e class) in a private subnet | Models are cached in a volume. Expose only to the agent's security group |
| Ollama (Qwen3 8B) | The same GPU instance, or a separate one | Q4 Qwen3 8B needs about 6–8 GB VRAM. CPU works but is slow for voice |
| Database / Auth | Supabase (Pro for production: backups, no pausing) | Apply `supabase/migrations`; enable email confirmations |
| Realtime voice | LiveKit Cloud | Agent dispatch by name `nexora-voice` |

Secrets go in AWS Secrets Manager or SSM Parameter Store, injected as environment variables. Use KMS
for the vault (`KEY_PROVIDER=aws_kms`, `AWS_KMS_KEY_ID`). The task role needs only `kms:Encrypt` and
`kms:Decrypt` on that key.

## Steps

1. **Supabase:** create the project → `supabase link` → `supabase db push`. Auth → URL configuration:
   site URL `https://app.example.com`, redirect `https://app.example.com/auth/callback`.
2. **API:** build and push `api.Dockerfile`. Environment: `APP_ENV=production`, `DATABASE_URL`
   (session pooler), `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `CORS_ORIGINS=https://app.example.com`,
   `API_PUBLIC_URL`, `WEB_APP_URL`, `INTERNAL_SERVICE_KEY`, `KEY_PROVIDER=aws_kms` + `AWS_KMS_KEY_ID`
   (or `VAULT_MASTER_KEYS`), `LIVEKIT_*`, `OLLAMA_BASE_URL` (private), and the optional integration
   keys. Set `DATABASE_AUTO_CREATE=false` and `RUN_SCHEDULER_IN_API=false`.
3. **Worker:** same image and environment, command `python -m app.automations.worker`.
4. **Speech + Ollama (GPU):** `docker run` the speech image with `SPEECH_API_KEY`, then
   `ollama pull qwen3:8b nomic-embed-text`.
5. **Voice agent:** environment `LIVEKIT_*`, `NEXORA_API_URL` (internal ALB),
   `NEXORA_INTERNAL_SERVICE_KEY`, `SPEECH_SERVER_URL`, `SPEECH_SERVER_KEY`.
6. **Web:** on Vercel, set `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_APP_URL`, `NEXT_PUBLIC_SUPABASE_URL`,
   `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` and `NEXT_PUBLIC_LIVEKIT_URL`. For the wake word, the model
   files in `apps/web/public/wake-word/` must be present at build time. They're git-ignored, so
   add them to the deployment, for example by running `pnpm wake-word:models` in the build and
   storing `hey_nexora.onnx` where the build can copy it.
7. Update the Gmail OAuth redirect and the WhatsApp webhook URLs to the production API.

## Scaling beyond one API task

In-process state that must move to shared infrastructure when you run more than one API task:

* **Assistant run buffers** (`assistant/runs.py`): use Redis Streams (`XADD` per event, `XREAD` from
  `Last-Event-ID`), or ALB sticky sessions.
* **Rate limits** (`core/rate_limit.py`): Redis `INCR` + `EXPIRE` per window.
* **Provider caches** (`integrations/base.py:TTLCache`): optional; Redis improves hit rates.

The scheduler is already multi-instance safe.

## Cost estimate

These are **assumptions**, not quotes: one person or a small household, about 50 text turns and
15 voice minutes a day, a 30-day month. Check current pricing before relying on any of it. Free tiers
often exclude commercial use.

| Item | Assumption | Approx. monthly |
| --- | --- | --- |
| Supabase | Pro plan | ~US$25 |
| Vercel | Hobby (personal, non-commercial) / Pro | $0 / ~US$20 per member |
| API + worker | 2 × Fargate 0.25 vCPU / 0.5 GB, always on | ~US$20 |
| Voice agent | 1 × 1 vCPU / 2 GB, always on | ~US$30–40 |
| LiveKit Cloud | ~450 agent/participant minutes | Often within the entry tier; check the current plan |
| GPU for Qwen3 + speech | g5.xlarge on-demand **24×7** | ~US$700+ (dominant cost) |
| GPU, only when used | Start/stop or spot, ~3 h/day | ~US$90–120 |
| Alternative | Local GPU workstation at home for Ollama + speech, reached over a VPN | electricity only |
| Cloud LLM fallback | Only when Ollama is down; usage logged in `execution_logs` | usage-based |

Ways to keep costs down, most already built in:

* Local inference comes first.
* Offline routing handles clear requests without a model call.
* Caches for weather, places, news and YouTube.
* Short prompts with a 16-message context window.
* Voice replies capped at 350 tokens.
* Per-user usage in `GET /me/usage` and `execution_logs`.
