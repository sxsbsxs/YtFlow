# YtFlow

A modern, self-hosted web video downloader powered by [yt-dlp](https://github.com/yt-dlp/yt-dlp).

YtFlow combines an IDM-inspired web interface with a Python/FastAPI backend and the yt-dlp media extraction engine.

> **Responsible use:** Download only content you own or are explicitly authorized to download. Follow the source website's terms and applicable copyright law. YtFlow does not bypass DRM or access controls.

## Features

- Paste a media URL and inspect title, thumbnail, uploader, duration, and available resolutions.
- Download video at best available quality or cap quality at 4K, 1440p, 1080p, 720p, 480p, or 360p.
- Extract audio to MP3, M4A, WAV, or Opus (FFmpeg required).
- Download playlists when explicitly selected.
- Live queue status, percentage, transfer speed, and ETA.
- Persistent SQLite task history; tasks interrupted by a server restart are kept and can be retried.
- Cancel active jobs and retry failed/cancelled jobs.
- Downloaded-file browser with persistent storage.
- Dark/light interface themes.
- Administrator login with signed HttpOnly cookies, CSRF tokens, and failed-login throttling.
- Caddy reverse proxy with automatic HTTPS certificates.
- Docker Compose deployment; the app container is not directly published to the internet.
- GitHub Actions checks Python 3.11/3.12, browser JavaScript, and the Docker image.

## Public deployment (recommended)

You need:
- A Linux VPS/server with a public IPv4 address (2 GB RAM or more recommended).
- A domain or subdomain whose DNS A record points to that server.
- Inbound TCP ports **80** and **443** open in your VPS/cloud firewall.
- Docker Engine and the Docker Compose plugin installed.

### 1. Point your domain to the server

Create an A record such as `downloads.example.com` pointing to the server's public IPv4 address. If you have an AAAA record, it must point to the correct server IPv6 address; otherwise remove it. Caddy uses the domain to request and renew HTTPS certificates automatically.

### 2. Configure credentials

```bash
git clone https://github.com/sxsbsxs/YtFlow.git
cd YtFlow
cp .env.example .env
```

Edit `.env` and set your real domain, email, and a unique administrator password. Generate a strong signing key:

```bash
openssl rand -hex 32
```

Paste the output into `YTFLOW_SECRET_KEY`. Do not commit or share `.env`.

### 3. Start the public HTTPS service

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f caddy ytflow
```

Then visit **https://your-domain.example** and sign in with the administrator username/password from `.env`.

The public entry point is Caddy on ports 80/443. The FastAPI container is only reachable on the private Docker network; it has no host-published port. Caddy obtains and renews TLS certificates automatically. The downloads and Caddy certificate data are kept in named Docker volumes.

### 4. Update

```bash
git pull
docker compose up -d --build
```

### 5. Back up downloads and TLS state

Back up Docker volumes `ytflow-downloads`, `caddy-data`, and `caddy-config`. The hidden `.ytflow.sqlite3` database is stored inside `ytflow-downloads` alongside media. Keep a separate secure backup of `.env`; losing `YTFLOW_SECRET_KEY` invalidates existing sessions.

## Local development

For local development without Caddy, use the same credentials but set `YTFLOW_COOKIE_SECURE=false` (only for localhost/HTTP). Example:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
export YTFLOW_ADMIN_USERNAME=admin
export YTFLOW_ADMIN_PASSWORD='replace-with-a-long-local-password'
export YTFLOW_SECRET_KEY="$(openssl rand -hex 32)"
export YTFLOW_COOKIE_SECURE=false
uvicorn app.main:app --host 127.0.0.1 --port 8080
```

On Windows PowerShell, set the same variables with `$env:NAME="value"`. Do not use the insecure-cookie setting on a public deployment.

## Configuration

| Variable | Required | Description |
| --- | --- | --- |
| `YTFLOW_DOMAIN` | Public Docker deployment | Public hostname for Caddy |
| `YTFLOW_ACME_EMAIL` | Public Docker deployment | Email for TLS certificate registration |
| `YTFLOW_ADMIN_USERNAME` | Yes | Single administrator username |
| `YTFLOW_ADMIN_PASSWORD` | Yes | Administrator password (minimum 12 characters; use 16+ random characters) |
| `YTFLOW_SECRET_KEY` | Yes | Random signing secret (minimum 32 characters) |
| `YTFLOW_SESSION_TTL_SECONDS` | No | Session lifetime, 300 to 604800 seconds (default 86400) |
| `YTFLOW_COOKIE_SECURE` | No | Secure cookie flag (default true) |
| `YTFLOW_WORKERS` | No | Concurrent download workers (default 2) |
| `YTFLOW_DOWNLOAD_DIR` | No | Download directory (Docker sets this to `/data/downloads`) |

## API

- `GET /api/health` — public health check
- `GET /api/auth/status` — session status and CSRF token for the signed-in browser
- `POST /api/auth/login` — authenticate administrator
- `POST /api/auth/logout` — end the current browser session
- `POST /api/inspect` — inspect a media URL (authenticated)
- `GET /api/downloads` — list jobs
- `POST /api/downloads` — create a job
- `GET /api/downloads/{id}` — get a job
- `DELETE /api/downloads/{id}` — cancel a job
- `POST /api/downloads/{id}/retry` — retry a failed/cancelled job
- `GET /api/files` — list downloaded files
- `GET /api/files/{filename}` — retrieve a downloaded file

All API routes except health, auth status, and login require a valid session. Mutating API requests also require the session's `X-CSRF-Token` header. Interactive API documentation is available at `/docs`, but protected operations still require authentication.

## Development and tests

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

## Security notes

- Use a dedicated VPS and keep the host OS, Docker, and images updated.
- Keep SSH key-only where possible and enable your provider's firewall. Only expose TCP 80/443 publicly (and SSH from trusted IPs); do not publish port 8080.
- The app has one shared administrator account, not multi-user accounts or role-based access.
- Login failures are throttled per client address in the application process. For high-exposure deployments, also configure provider-level or reverse-proxy rate limiting.
- YtFlow accepts HTTP(S) URLs and rejects obvious local/private IP literals. This is not a complete SSRF defense against DNS rebinding or malicious redirects. Restrict outbound network access at the host/firewall layer if the service will be used by untrusted users.
- Download job metadata is stored in a hidden SQLite database inside the download directory. Task history therefore survives application restarts. Jobs that were queued or running when the process stopped are marked failed on next startup and can be retried; an interrupted media transfer may resume when the source server supports it.
- Do not expose the app directly to the internet or disable authentication.

## License

MIT. See [LICENSE](LICENSE).
