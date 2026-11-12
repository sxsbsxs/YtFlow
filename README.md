# YtFlow

A modern, self-hosted web video downloader powered by [yt-dlp](https://github.com/yt-dlp/yt-dlp).

> Download only content you own or are authorized to download. Respect each website's terms and applicable copyright law.

## Status

Initial project scaffold is being built. The first release provides a local web UI, URL inspection, video/audio download jobs, live progress, and Docker deployment.

## Quick start

```bash
docker compose up --build
```

Open http://localhost:8080.

## Local development

Requires Python 3.11+ and FFmpeg on `PATH`.

```bash
python -m venv .venv
. .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8080
```

## Security

YtFlow is intended for trusted, local use. Do not expose it directly to the public internet. Add authentication, HTTPS, network restrictions, and appropriate rate limits before remote deployment. Downloads are stored in the configured `downloads/` directory.

## License

MIT. See [LICENSE](LICENSE).
