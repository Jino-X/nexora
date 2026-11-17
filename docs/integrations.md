# Integrations

Each provider is an explicit adapter in `services/api/app/integrations/`. The assistant reaches
providers only through typed tools. Without credentials, a feature shows "Not configured" with setup
steps. It never pretends to work.

## Gmail (per user, OAuth)

* **Setup:** Google Cloud Console → enable the Gmail API → OAuth consent screen → OAuth client
  (Web). Add the redirect URI `{API_PUBLIC_URL}/api/v1/integrations/gmail/callback`. Set
  `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`.
* **Scopes (least privilege):** `gmail.readonly` to list, search and read, and `gmail.compose` to
  create drafts and send them. Nexora never deletes email or changes settings.
* **Flow:** authorization code with PKCE (S256) and single-use state (10 min). The refresh token is
  encrypted with envelope encryption. Access tokens refresh automatically. `invalid_grant` marks the
  integration "needs attention". Disconnecting or deleting the account revokes the token at Google.
* **Verification:** both scopes are Google **restricted** scopes. Until the app passes Google's OAuth
  verification and the annual third-party security assessment, keep it in *Testing* mode with up to
  100 named test users.
* **Approvals:** the assistant needs approval to create drafts (configurable per user) and always to
  send.

## WhatsApp (per user, Business Platform Cloud API)

* **Setup:** Meta for Developers app → WhatsApp product → business phone number. Paste the **phone
  number ID** and a **system-user access token** into Integrations → WhatsApp. The token is
  encrypted at rest.
* **Rules:** free-form text works only within 24 hours of the recipient's last message. Outside that
  window Meta requires approved **templates** (`POST /whatsapp/messages` with `template`). The
  assistant's sends always need approval. Personal WhatsApp accounts and WhatsApp Web automation are
  **not supported**.
* **Webhook (optional):** point Meta at `{API}/api/v1/integrations/whatsapp/webhook`, with
  `WHATSAPP_WEBHOOK_VERIFY_TOKEN` and `WHATSAPP_APP_SECRET`. Signatures (`X-Hub-Signature-256`) are
  verified, and inbound messages become notifications.

## Places and maps (server, OpenStreetMap)

* Geocoding uses **Nominatim** (`NOMINATIM_URL`). Nearby search uses **Overpass** (`OVERPASS_URL`,
  comma-separated mirrors, tried in order with one backoff retry). Maps use OSM tiles via Leaflet.
* Public instances have strict policies: Nominatim allows at most 1 request/s (enforced in code),
  needs a real User-Agent and expects caching (24 h geocode cache, 15 min nearby cache). The public
  Overpass server is **frequently at capacity** (40 s answers or 502s), so the default list tries the
  `maps.mail.ru` mirror first and `overpass-api.de` second. Keep the list to two entries: each try can
  take up to 25 s and the web app waits 60 s. For production, self-host Overpass with an India
  extract, or switch the provider. The adapter interface is `OSMPlacesProvider.nearby/geocode`.
* Directions are plain Google Maps / OSM links, so no Directions API key is needed.
* Attribution "© OpenStreetMap contributors" is shown on every map and list.

## Weather (server, Open-Meteo)

No key needed. Open-Meteo is free for **non-commercial** use. Commercial use requires an API
subscription: set `OPEN_METEO_URL` to the customer endpoint. Data is CC BY 4.0 and attribution is
shown. Responses are cached for 10 minutes per ~1 km cell.

## News (server, RSS)

`NEWS_FEEDS` (JSON) sets the sources. The defaults include BBC, The Hindu, Ars Technica, The Verge,
Hugging Face, Google AI and MIT Technology Review. Nexora shows headlines, publisher summaries, dates
and links back to the source, and de-duplicates by canonical URL and title similarity. Check each
publisher's terms before commercial use. The assistant is instructed never to invent news.

## YouTube (server, Data API v3)

Set `YOUTUBE_API_KEY`. Each `search.list` costs 100 quota units against the default 10,000/day
(about 100 searches), so results are cached for an hour. Playback uses the official privacy-enhanced
embed (`youtube-nocookie.com`). Nothing is downloaded.

## Music (server)

* **Default: Apple iTunes Search API.** No key needed. It returns Apple Music links and official
  30-second previews.
* **Spotify:** set `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET` (client credentials). Search
  results play in the official Spotify embed (previews, or full tracks for logged-in Premium users in
  the iframe). Nexora never downloads, records or re-hosts audio.

## Adding an integration

1. Write an adapter in `app/integrations/<name>/` that takes an `httpx.AsyncClient` (so tests can use
   `MockTransport`) and raises `NotConfiguredError` or `UpstreamError`.
2. Register tools in `app/agents/<name>_agent.py` with a Pydantic args model, a risk level, an
   approval policy and `integration=` if a per-user connection is required.
3. Add it to `CATALOG` in `api/v1/integrations.py` and to the web Integrations pages.
