# Nexora web app

Next.js 16 (App Router, Cache Components) with Tailwind CSS 4, shadcn/ui, TanStack Query, Zustand,
the LiveKit React SDK, Leaflet maps and PWA support.

```bash
pnpm install                 # from the repo root
cp .env.example .env.local   # API URL; Supabase optional (dev login is used otherwise)
pnpm dev                     # http://localhost:3000
pnpm lint && pnpm typecheck && pnpm test && pnpm build
```

| Path                       | What                                                                                                                   |
| -------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| `src/proxy.ts`             | Route protection (Supabase session refresh, or the dev token)                                                          |
| `src/app/(auth)`           | Login, signup, password reset; `auth/callback` for Supabase links                                                      |
| `src/app/(app)`            | Dashboard, assistant, discover, memory, vault, automations, tasks, history, notifications, integrations, settings      |
| `src/components/assistant` | Chat view, streaming bubbles, tool chips, approval cards, result cards (weather, map, news, YouTube, music…)           |
| `src/components/voice`     | Voice orb and panel (LiveKit hooks, transcripts, tool events), wake word listener                                      |
| `src/lib/api`              | Typed fetch client, React Query hooks, resumable SSE client                                                            |
| `src/lib/auth`             | Supabase browser client, dev auth, `AuthProvider`                                                                      |
| `src/lib/voice`            | `VoiceProvider` (single LiveKit room), openWakeWord wake word (ONNX Runtime Web worker) + cooldown gate, Zustand store |

Read `AGENTS.md`: this Next.js version differs from older docs (`proxy.ts`, async params,
Cache Components).
