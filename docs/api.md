# API

Base path `/api/v1`. Interactive OpenAPI docs are at `/docs` outside production. Every route needs
`Authorization: Bearer <Supabase access token>` except `/auth/dev/login` (dev only), the Gmail OAuth
callback, the WhatsApp webhook and the `/internal/*` routes (service key).

## Conventions

* **Errors** always look like this:
  `{"error": {"code": "not_configured", "message": "...", "request_id": "...", "details": ...}}`.
  `503 not_configured` means a feature needs server credentials, and the UI shows it as a disabled
  state. `502 upstream_*` means an external provider failed or timed out.
* **Pagination**: `?limit=&offset=` returns `{items, has_more, next_offset}`.
* **Limits**: 120 requests/min per user, 20 assistant runs/min, 10 voice sessions/min, 10 vault
  reveals/min, and a 6 MB request body.
* **Tracing**: every response carries `X-Request-ID`. Send your own to correlate logs.

## Assistant (SSE)

`POST /assistant/runs` with `{message, conversation_id?, location?, language?, regenerate?}` responds
with `text/event-stream`. The run executes in a server task, so a dropped connection does not stop it.

| Event | Data |
| --- | --- |
| `run_started` | `run_id`, `conversation_id`, `user_message_id`, `created_conversation`, `channel` |
| `status` | `text` ("Working on it...") |
| `token` | `text`, an incremental piece of the reply |
| `tool_start` | `id`, `tool`, `category` |
| `tool_end` | `id`, `tool`, `ok`, `message`, `duration_ms`, `error_code?`, `card?` (rich UI data) |
| `approval_required` | `approval_id`, `tool`, `summary`, `expires_at` |
| `message_end` | `message_id`, `content`, `provider`, `model`, `offline`, `cards`, `approvals`, `usage` |
| `error` | `code`, `message`, `retryable` |
| `cancelled` | `reason` |
| `done` | `status`. Always the final event |

* Resume: `GET /assistant/runs/{id}/events?after=N`, or send the `Last-Event-ID` header. Only
  events after `N` are replayed. Buffers are kept for 10 minutes after the run ends.
* Stop: `POST /assistant/runs/{id}/cancel`. Partial text is saved with status `cancelled`.
* Retry: `POST /assistant/runs` with `{conversation_id, regenerate: true}` re-runs the last user
  message without duplicating it.

## Endpoints

| Area | Routes |
| --- | --- |
| System | `GET /health`, `GET /health/ready`, `GET /system/status` (capabilities for honest UI states) |
| Auth (dev only) | `POST /auth/dev/login` |
| Me | `GET /me`, `PATCH /me/profile`, `PATCH /me/preferences`, `POST /me/onboarding`, `GET /me/usage`, `GET /me/export`, `DELETE /me` (`{"confirm":"DELETE"}`) |
| Conversations | `GET/POST /conversations`, `GET/PATCH/DELETE /conversations/{id}` |
| Voice | `POST /voice/sessions` (`activation`, `hold_to_talk`, `conversation_id`, `language`), `POST /voice/sessions/{id}/end`, `GET /voice/sessions` |
| Integrations | `GET /integrations`, `POST /integrations/gmail/connect`, `GET /integrations/gmail/callback`, `PUT /integrations/whatsapp`, `POST /integrations/{provider}/disconnect`, `GET/POST /integrations/whatsapp/webhook` |
| Gmail | `GET /gmail/messages?q=&unread=`, `GET /gmail/messages/{id}`, `POST /gmail/drafts`, `POST /gmail/drafts/{id}/send` |
| WhatsApp | `POST /whatsapp/messages` (text or template) |
| Location | `GET /location/categories`, `/location/geocode?q=`, `/location/reverse?lat=&lon=`, `/location/nearby?category=&lat=&lon=&radius_m=` |
| Weather | `GET /weather?lat=&lon=&days=` (defaults to the home location) |
| News | `GET /news?category=&q=&limit=`, `GET /news/categories` |
| YouTube | `GET /youtube/search?q=&kind=video\|channel\|playlist` |
| Music | `GET /music/search?q=`, `GET /music/provider` |
| Memories | `GET /memories?q=&kind=` (semantic when `q` is set), `POST`, `PATCH/DELETE /memories/{id}`, `DELETE /memories?confirm=true`, `GET /memories/export`, `POST /memories/reindex` |
| Vault | `GET /vault/status`, `GET/POST /vault`, `POST /vault/{id}/reveal`, `PATCH/DELETE /vault/{id}`, `GET /vault/audit` |
| Automations | `GET/POST /automations`, `POST /automations/preview`, `GET/PATCH/DELETE /automations/{id}`, `POST /automations/{id}/run`, `GET /automations/{id}/runs` |
| Tasks | `GET /tasks?status=&kind=`, `GET /tasks/{id}` |
| Approvals | `GET /approvals?status=`, `POST /approvals/{id}/approve`, `POST /approvals/{id}/reject` |
| Notifications | `GET /notifications?unread=`, `GET /notifications/unread-count`, `POST /notifications/read` |
| Permissions | `GET /permissions/tools`, `PUT /permissions/tools/{tool}` |
| Dashboard | `GET /dashboard` (one round-trip summary) |

### Internal (voice agent only)

Header `X-Nexora-Internal-Key: <INTERNAL_SERVICE_KEY>`. Never expose this to browsers.

* `POST /internal/voice/turns` with `{session_id, room_name, participant_identity, text, language?}`
  returns the same SSE stream as text runs. The API checks that the session is active, that the room
  matches, and that the identity is the session owner. Dropping the connection cancels the run
  (barge-in).
* `POST /internal/voice/events` with `{session_id, room_name, event: agent_joined | session_started |
  session_ended | metrics, reason?, metrics?}`.

## Schedules

```json
{"type": "once", "at": "2026-11-15T09:00"}
{"type": "daily", "time": "07:30"}
{"type": "weekly", "time": "07:30", "days": [0, 1, 2, 3, 4]}
{"type": "interval", "minutes": 60}
```

Times are local to the rule's IANA `timezone`, which defaults to the profile's timezone.
