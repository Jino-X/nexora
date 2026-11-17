# Security and privacy

## Threat model (summary)

| Threat | Control |
| --- | --- |
| Forged or expired tokens | Supabase JWT verification: JWKS (ES256/RS256) with issuer, audience `authenticated`, `exp` and role checks; HS256 only with the configured secret. `alg=none` and unknown algorithms are rejected. The dev issuer is accepted only when `AUTH_DEV_MODE=true`, which is refused in production |
| Cross-user data access | Every repository query is filtered by `user_id`; foreign rows return 404. RLS on all tables. Composite `(id, user_id)` FKs in Postgres. Isolation tests cover every resource |
| Prompt injection driving harmful actions | Tools are typed, allow-listed adapters only: no shell, HTTP, SQL or code execution. Arguments are validated. Sending email or WhatsApp **always** needs explicit approval in the UI. Automations can't auto-run write tools. Secret values never reach the model |
| Secret leakage | Vault and OAuth tokens use envelope encryption. Logs redact sensitive keys and token-like strings. The vault API never lists values. Reveals are rate limited and audited |
| Abuse and cost blow-ups | Per-user rate limits (global, assistant, voice, vault reveal, YouTube, WhatsApp), at most 3 concurrent runs per user, 6 MB body limit, 8k-character input cap, LLM step cap, and voice session caps |
| Voice hijacking | Short-lived (10 min) room-scoped tokens with microphone-only publish rights. The agent serves only the owner's identity. Every turn is re-authorized by the API (session, room and owner must match) |
| Double execution | Approvals transition `pending → approved` with a conditional UPDATE, and execution is keyed by a UNIQUE `task_runs.idempotency_key`. Automation occurrences work the same way |
| Browser attacks | Strict CSP, `X-Frame-Options: DENY`, `nosniff`, a permissions policy that limits the mic and location to self, no cookies sent to the API (bearer tokens only), and an exact CORS allow-list |

## Envelope encryption (vault and integration credentials)

```
payload ──AES-256-GCM(DEK, nonce, AAD)──► ciphertext       (stored in vault_items / integrations)
DEK (random per record) ──wrap(KEK)──►     wrapped_key      (stored next to the ciphertext)
KEK: local keyring (VAULT_MASTER_KEYS, from the secret manager) or AWS KMS (KEY_PROVIDER=aws_kms)
AAD = {"purpose", "user_id", "record_id"}
```

* Keys are separate from data. Database dumps alone can't decrypt anything.
* The associated data binds each ciphertext to its user, record and purpose. Moving or copying rows
  fails authentication (tested).
* The 96-bit random nonce comes from `os.urandom`. Each record has a fresh DEK.
* **KMS:** `AwsKmsKeyProvider` uses `Encrypt`/`Decrypt` with an EncryptionContext (also the AAD) and
  needs IAM `kms:Encrypt` and `kms:Decrypt` on the key.

### Key rotation

1. Generate a key: `python -c "import base64,os;print(base64.b64encode(os.urandom(32)).decode())"`
2. Prepend it: `VAULT_MASTER_KEYS=k2:<new>,k1:<old>` and set `VAULT_ACTIVE_KEY_ID=k2`. Deploy.
3. `python -m app.scripts.rotate_vault_keys` re-wraps DEKs. It is idempotent and the payloads are
   untouched.
4. When it reports `0 remaining`, remove `k1` and deploy. Old ciphertexts can't be opened once their
   key is gone.

For KMS, enable automatic key rotation on the CMK. Old wrapped keys stay decryptable through KMS.

### Using secrets

The assistant has only `vault_list_items`, which returns names and kinds. It cannot read values and
nothing is injected into prompts. Users reveal values in the Vault UI. Reveals auto-hide after 30
seconds, are audited, and can require a recent sign-in (`VAULT_REAUTH_MAX_AGE_MINUTES`, checked
against the Supabase `amr` claim). Memory refuses text that looks like a credential and points to the
vault.

## Approvals

Tools declare `approval: never | configurable | always`. `always` covers email sends and WhatsApp.
`configurable` covers drafts and defaults to on; users can change it in Settings → Permissions. A
pending approval stores validated arguments and a human summary, expires after 24 h, and is executed
by the API through the same permission check with channel `approval`. Every decision is audited.

## Logging

JSON logs carry `request_id` and `user_id`. Keys matching
`password|secret|token|authorization|api_key|cookie|credential|refresh|private|ciphertext` are
replaced with `[redacted]`. Bearer tokens, JWTs, `sk-`, `AKIA…`, `ya29.` and `EAA…` patterns are
scrubbed from messages and stack traces. Tool calls log full arguments only for read-only tools.

## Data rights

* **Export:** `GET /me/export` returns all user data as JSON, excluding secret values and tokens.
* **Delete:** `DELETE /me` revokes Gmail, deletes every row and, with `SUPABASE_SERVICE_ROLE_KEY`
  set, deletes the auth user.
* **Retention:** per-user memory and conversation retention, plus housekeeping in the worker.
* **Voice:** no raw audio is stored. The wake word runs fully on-device.

## Production checklist

* `APP_ENV=production` (refuses dev auth, SQLite, wildcard CORS, and a missing key provider)
* Secrets in AWS Secrets Manager or SSM; KMS for the vault; TLS everywhere
* `SUPABASE_SERVICE_ROLE_KEY`, `INTERNAL_SERVICE_KEY` and `SPEECH_API_KEY` only on servers
* The speech server and Ollama on a private network, never public
* Rotate `INTERNAL_SERVICE_KEY` by deploying the new value to the API and the agent together
