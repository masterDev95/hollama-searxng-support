# Hollama + SearXNG Web Search Proxy

Add privacy-friendly web search to [Hollama](https://github.com/fmaclen/hollama) by routing your LLM
through an OpenAI-compatible proxy that forwards `search` requests to [SearXNG](https://searxng.org)
and `chat/completions` requests to [Ollama](https://ollama.com).

Everything runs locally in Docker. Your search queries and chat prompts never leave your machine — they
are sent to services you run yourself, and SearXNG exposes no results to the public index.

> This project was developed with AI assistance.

---

## Table of contents

- [Features](#features)
- [Architecture](#architecture)
- [Quick start](#quick-start)
- [Verify the stack](#verify-the-stack)
- [Configure Hollama](#configure-hollama)
- [Environment variables](#environment-variables)
- [Endpoints](#endpoints)
- [What the proxy does](#what-the-proxy-does)
- [Docker credential-helper workaround](#docker-credential-helper-workaround)
- [Maintenance](#maintenance)
- [Troubleshooting](#troubleshooting)
- [FAQ](#faq)

---

## Features

- **Web search in chat** — Hollama can answer questions using live search results from SearXNG.
- **Fully local** — SearXNG, the proxy, and Ollama all run on your own machine behind `127.0.0.1`.
- **OpenAI-compatible** — the proxy speaks the OpenAI API, so it drops straight into Hollama.
- **No secrets in git** — the only runtime variable (`SEARXNG_SECRET`) is kept out of version control.

---

## Architecture

```
┌─────────────┐        ┌──────────────────┐        ┌──────────────────────────┐
│  Hollama    │        │  proxy (Python)  │        │  upstream services       │
│  :4173      │──────▶│  :8081 /v1       │◀────▶│  Ollama :11434           │
└─────────────┘        └──────────────────┘        └──────────────────────────┘
        │ OpenAI client       │ OpenAI-compatible            │ /api/tags
        │  /v1/*              │  /v1/search  ──────────────▶│ (model list)
        │                     │  /v1/chat/completions        ▼
        │                     │                             SearXNG :8080
        │                     └───────────────────┬──────────┘
        └───────────────────────────────────────▶:8080  (search results)
```

- **Hollama** (`http://localhost:4173`) talks to the proxy as an OpenAI client.
- **The proxy** (`python:3.12-slim`) listens on the host network at `127.0.0.1:8081` and routes:
  - `/v1/search` → SearXNG (`http://127.0.0.1:8080`)
  - `/v1/chat/completions` → Ollama (`http://127.0.0.1:11434`)
  - `/v1/models` → Ollama (`http://127.0.0.1:11434/api/tags`)

---

## Quick start

Prerequisites: [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/) installed.

1. Clone the repository (if you have not already):

   ```bash
   git clone <your-repo-url>
   cd hollama-searxng-support
   ```

2. Create the environment file from the template and set a secret:

   ```bash
   cp .env.example .env
   # Edit .env and set SEARXNG_SECRET to a random string, e.g.:
   echo 'SEARXNG_SECRET=replace-me-with-a-long-random-string' > .env
   ```

   The `.env` file is excluded from Git (see `.gitignore`), so you can commit the project without
   leaking the secret.

3. Start the stack with Docker Compose:

   ```bash
   docker compose up -d
   ```

   This launches both services defined in [`compose.yaml`](compose.yaml):

   - `searxng` — the SearXNG instance, published on `127.0.0.1:8080`.
   - `proxy` — the Python proxy, running in host network mode bound to `127.0.0.1:8081`.

4. Make sure Ollama is running and has at least one model pulled:

   ```bash
   curl http://127.0.0.1:11434/api/tags
   # If the list is empty, pull a model first, e.g.:
   curl http://127.0.0.1:11434/api/tags?qwen3.5:9b
   ```

   `qwen3.5:9b` is only an example — replace it with any model you have pulled into Ollama.

5. Configure Hollama to use the proxy (see [Configure Hollama](#configure-hollama)).

---

## Verify the stack

Check that every service is responding before wiring up Hollama:

```bash
# SearXNG health
curl -s http://127.0.0.1:8080/healthz

# Proxy health and model list
curl -s http://127.0.0.1:8081/v1/healthz
curl -s http://127.0.0.1:8081/v1/models
```

A successful `/v1/models` response returns a JSON list of the models available in Ollama, for example:

```json
{
  "object": "list",
  "data": [
    {"id": "qwen3.5:9b", "object": "model", "created": 0, "owned_by": "ollama"}
  ]
}
```

---

## Configure Hollama

In the Hollama configuration, point the LLM provider at the proxy instead of Ollama directly. The
proxy is an OpenAI-compatible endpoint, so you only change the base URL and set the model name.

| Setting   | Value                     | Notes                                             |
| --------- | ------------------------- | ------------------------------------------------- |
| Base URL  | `http://127.0.0.1:8081/v1`| The proxy endpoint; **no trailing slash needed**. |
| API key   | *(empty / not required)*  | The proxy is bound to localhost and needs no key. |
| Model     | your Ollama model name    | e.g. `qwen3.5:9b` — any model listed by `/v1/models`. |

Enable the **web search** capability so Hollama sends `search` requests to the proxy's `/v1/search`
endpoint, which returns SearXNG results.

---

## Environment variables

The only variable required is `SEARXNG_SECRET`, used by SearXNG to sign its CSRF tokens.

| Variable         | Default                                   | Description                                              |
| ---------------- | ----------------------------------------- | -------------------------------------------------------- |
| `SEARXNG_SECRET` | — (required)                              | Secret used to generate SearXNG's anti-CSRF tokens.      |
| `PROXY_PORT`     | `8081`                                    | Port the proxy binds to on the host.                     |
| `OLLAMA_URL`     | `http://127.0.0.1:11434`                  | URL of the local Ollama instance.                        |
| `SEARXNG_URL`    | `http://127.0.0.1:8080`                   | URL of the local SearXNG instance.                       |

> The `.env` file is git-ignored — only `.env.example` is committed, and it contains just the
> `SEARXNG_SECRET` placeholder.

---

## Endpoints

| Endpoint                          | Port    | Purpose                                             |
| --------------------------------- | ------- | --------------------------------------------------- |
| `http://127.0.0.1:8080/`          | 8080    | SearXNG search API.                                 |
| `http://127.0.0.1:8081/v1/*`      | 8081    | OpenAI-compatible proxy (the endpoint Hollama uses).|
| `http://127.0.0.1:11434/`         | 11434   | Ollama (chat completions and model listing).        |
| `http://localhost:4173/`          | 4173    | Hollama (the LLM client).                           |

---

## What the proxy does

The proxy is a small OpenAI-compatible shim. It exposes the standard OpenAI routes and forwards them:

| Route                        | Upstream             | Notes                                            |
| ---------------------------- | -------------------- | ------------------------------------------------ |
| `POST /v1/search`            | SearXNG `:8080`      | Returns SearXNG results in an OpenAI `chat` shape.|
| `POST /v1/chat/completions`  | Ollama `:11434`      | Streams chat completions from Ollama.            |
| `GET /v1/models`             | Ollama `:11434/api/tags` | Returns the list of local models.            |
| `GET /v1/healthz`            | —                    | Lightweight liveness check.                       |

All upstream calls go to `127.0.0.1`, so nothing is exposed to the network.

---

## Docker credential-helper workaround

If `docker compose up` fails because Docker cannot resolve credentials, it is usually because the
configured credential helper (`docker-credential-desktop`) points to an executable that is not present
on this machine.

The proxy and SearXNG never authenticate against a registry, so they do not need any stored credential.
To let Compose start despite the broken helper, temporarily tell Docker to use the built-in
`desktop` helper with an empty credential store.

### Diagnose first

```bash
# Which helper does Docker use by default?
docker info 2>&1 | grep -i "security"

# Confirm the helper path resolves
docker-credential-desktop --version 2>&1 || echo "helper executable not found"
```

### Apply the workaround

```bash
# 1. Point Docker at a temporary config directory.
export DOCKER_CONFIG="$(mktemp -d)"

# 2. Satisfy the credential helper with an empty (but valid) credential store.
printf '{"Status":"Success","Credentials":{}}' > "$DOCKER_CONFIG/store"

# 3. Start the stack (the empty store satisfies the helper).
docker compose up -d
```

After the stack is up, you can leave `DOCKER_CONFIG` set for the rest of the session, or unset it
before the next real login flow. Remove the temporary directory when done:

```bash
rm -rf "$DOCKER_CONFIG"
```

> This only works as a local convenience. Do not commit `DOCKER_CONFIG` or any `docker config.json` —
> they may contain real registry credentials.

---

## Maintenance

### Restart services

```bash
docker compose restart
```

### Update the images

```bash
docker compose pull      # download the latest images
docker compose up -d     # bring the stack back up
```

### Logs

```bash
docker compose logs -f --tail=100
```

Filter a single service:

```bash
docker compose logs -f proxy
docker compose logs -f searxng
```

### Stop and remove everything

```bash
docker compose down
# Remove all containers, images, networks, and named volumes:
docker compose down --rmi all --remove-orphans --volumes
```

---

## Troubleshooting

| Symptom                                                   | Cause / Fix                                                                                   |
| --------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| `docker compose up` fails on the credential helper        | See [Docker credential-helper workaround](#docker-credential-helper-workaround).             |
| `/v1/models` returns an empty list                        | Ollama has no models pulled. Pull one with `curl http://127.0.0.1:11434/api/tags?qwen3.5:9b`. |
| Search returns nothing                                    | SearXNG needs at least one engine configured; check its settings UI at `http://127.0.0.1:8080`. |
| `Connection refused` on `:8081`                           | The proxy container is not running — `docker compose ps`.                                   |
| Hollama cannot reach the proxy                            | Use `http://127.0.0.1:8081/v1` (not `localhost`) and make sure Ollama is up.               |
| `401 Unauthorized` from the proxy                         | The proxy does not require an API key. Remove any key from the Hollama provider config.     |

---

## FAQ

**Q: Is anything sent to the internet?**

No. The proxy and SearXNG bind to `127.0.0.1`, and the proxy forwards only to `127.0.0.1:8080`
(SearXNG) and `127.0.0.1:11434` (Ollama). Nothing leaves your machine.

**Q: Do I need an API key?**

No. Because everything is bound to localhost, the proxy needs no authentication.

**Q: Why is `.env` not in the repository?**

The only secret here is `SEARXNG_SECRET`. `.gitignore` excludes `.env` (mode `600`), so your secret is
never committed.

**Q: Can I use this with other LLM clients?**

Yes. The proxy is OpenAI-compatible, so any client that speaks the OpenAI API can target
`http://127.0.0.1:8081/v1`.
