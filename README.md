# YtFlow

A modern, self-hosted web video downloader powered by [yt-dlp](https://github.com/yt-dlp/yt-dlp).

YtFlow combines a clean IDM-inspired web interface with a Python/FastAPI backend and the yt-dlp media extraction engine.

> **Responsible use:** Download only content you own or are explicitly authorized to download. Follow the source website's terms and applicable copyright law. YtFlow does not bypass DRM or access controls.

## Features

- Paste a media URL and inspect title, thumbnail, uploader, duration, and available resolutions.
- Download video at best available quality or cap quality at 4K, 1440p, 1080p, 720p, 480p, or 360p.
- Extract audio to MP3, M4A, WAV, or Opus (FFmpeg required).
- Download playlists when explicitly selected.
- Track queued, downloading, processing, completed, failed, and cancelled jobs.
- See live percentage, transfer speed, and estimated time remaining.
- Cancel active jobs and retry failed/cancelled jobs.
- Dark/light interface themes.
- Docker Compose deployment with a persistent downloads folder.
- GitHub Actions CI for Python 3.11 and 3.12.

## Quick start with Docker

Requirements: Docker Engine and the Docker Compose plugin.

```bash
git clone https://github.com/sxsbsxs/YtFlow.git
cd YtFlow
docker compose up --build
```

Open **http://localhost:8080**.

Downloaded media is stored in the local `./downloads` folder. The Compose port is intentionally bound to `127.0.0.1` so the web UI is not exposed to your network by default.

Stop the service with:

```bash
docker compose down
```

## Run without Docker

Requirements: Python 3.11 or later and FFmpeg available on your system PATH.

```bash
git clone https://github.com/sxsbsxs/YtFlow.git
cd YtFlow
python -m venv .venv
```

Activate the environment:

```bash
# Linux / macOS
source .venv/bin/activate

# Windows PowerShell
.venv\\Scripts\\Activate.ps1
```

Install and start:

```bash
python -m pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8080
```

Open **http://127.0.0.1:8080**.

## Configuration

| Environment variable | Default | Description |
| --- | --- | --- |
| `YTFLOW_DOWNLOAD_DIR` | `downloads` | Directory used to store downloaded files |
| `YTFLOW_WORKERS` | `2` | Maximum concurrent download workers |

Example:

```bash
YTFLOW_WORKERS=3 YTFLOW_DOWNLOAD_DIR=/data/media uvicorn app.main:app --host 127.0.0.1 --port 8080
```

## API

- `GET /api/health` — health check
- `POST /api/inspect` — inspect a media URL
- `GET /api/downloads` — list jobs
- `POST /api/downloads` — create a job
- `GET /api/downloads/{id}` — get a job
- `DELETE /api/downloads/{id}` — cancel a job
- `POST /api/downloads/{id}/retry` — retry a failed/cancelled job
- `GET /api/files` — list downloaded files
- `GET /api/files/{filename}` — retrieve a downloaded file

Interactive API documentation is available at **/docs**.

## Development and tests

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

GitHub Actions runs the test suite on Python 3.11 and 3.12 for pushes and pull requests to `main`.

## Security notes

YtFlow is designed for trusted, local use. It does not currently provide user authentication or multi-user access control. Do not expose it directly to the public internet. Before any remote deployment, put it behind authentication and HTTPS, restrict network access, and apply rate limits. The URL validator rejects non-HTTP(S) schemes and obvious localhost/private-IP targets, but it is not a substitute for network-level egress controls.

Job metadata is held in memory and is cleared when the server restarts. Downloaded files remain in the configured downloads directory.

## License

MIT. See [LICENSE](LICENSE).
