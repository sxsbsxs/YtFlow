from __future__ import annotations

import secrets
import threading
import time
from collections import defaultdict, deque
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from yt_dlp import YoutubeDL

from app.downloads import DOWNLOAD_DIR, manager, validate_media_url
from app.security import COOKIE_NAME, SessionAuth


app = FastAPI(
    title="YtFlow",
    version="0.2.0",
    description="A self-hosted web video downloader powered by yt-dlp.",
)
auth = SessionAuth.from_env()

LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_MAX_FAILURES = 5
_login_failures: dict[str, deque[float]] = defaultdict(deque)
_login_lock = threading.Lock()


class InspectRequest(BaseModel):
    url: str = Field(min_length=8, max_length=4096)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)


class DownloadRequest(BaseModel):
    url: str = Field(min_length=8, max_length=4096)
    quality: Literal["best", "2160p", "1440p", "1080p", "720p", "480p", "360p"] = "best"
    mode: Literal["video", "audio"] = "video"
    audio_format: Literal["mp3", "m4a", "wav", "opus"] = "mp3"
    playlist: bool = False
    title: str | None = Field(default=None, max_length=240)
    thumbnail: str | None = Field(default=None, max_length=4096)


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _login_is_limited(client_key: str) -> bool:
    now = time.monotonic()
    with _login_lock:
        attempts = _login_failures[client_key]
        while attempts and now - attempts[0] > LOGIN_WINDOW_SECONDS:
            attempts.popleft()
        return len(attempts) >= LOGIN_MAX_FAILURES


def _record_login_failure(client_key: str) -> None:
    now = time.monotonic()
    with _login_lock:
        attempts = _login_failures[client_key]
        while attempts and now - attempts[0] > LOGIN_WINDOW_SECONDS:
            attempts.popleft()
        attempts.append(now)


def _clear_login_failures(client_key: str) -> None:
    with _login_lock:
        _login_failures.pop(client_key, None)


@app.middleware("http")
async def security_and_auth_middleware(request: Request, call_next):
    path = request.url.path
    public_api_paths = {"/api/health", "/api/auth/status", "/api/auth/login"}
    if path.startswith("/api/") and path not in public_api_paths:
        session = auth.read(request.cookies.get(COOKIE_NAME))
        if session is None:
            response = JSONResponse({"detail": "请先登录 YtFlow。"}, status_code=401)
            response.headers["Cache-Control"] = "no-store"
            return response
        request.state.ytflow_session = session
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            supplied_csrf = request.headers.get("x-csrf-token", "")
            if not secrets.compare_digest(supplied_csrf, session["csrf"]):
                response = JSONResponse({"detail": "安全令牌无效，请刷新页面后重试。"}, status_code=403)
                response.headers["Cache-Control"] = "no-store"
                return response

    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; "
        "form-action 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; img-src 'self' data: https:; connect-src 'self'",
    )
    if path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/api/health")
async def health():
    return {"ok": True, "name": "YtFlow", "version": app.version}


@app.get("/api/auth/status")
async def auth_status(request: Request):
    session = auth.read(request.cookies.get(COOKIE_NAME))
    if not session:
        return {"authenticated": False}
    return {
        "authenticated": True,
        "username": session["sub"],
        "csrf_token": session["csrf"],
        "expires_at": session["exp"],
    }


@app.post("/api/auth/login")
async def login(payload: LoginRequest, request: Request):
    client_key = _client_key(request)
    if _login_is_limited(client_key):
        raise HTTPException(status_code=429, detail="登录尝试过多，请 15 分钟后再试。")
    if not auth.verify_credentials(payload.username, payload.password):
        _record_login_failure(client_key)
        raise HTTPException(status_code=401, detail="用户名或密码错误。")

    _clear_login_failures(client_key)
    token, csrf_token = auth.issue()
    response = JSONResponse({"ok": True, "csrf_token": csrf_token})
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=auth.config.session_ttl_seconds,
        httponly=True,
        secure=auth.config.cookie_secure,
        samesite="strict",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@app.post("/api/auth/logout")
async def logout():
    response = JSONResponse({"ok": True})
    response.delete_cookie(
        key=COOKIE_NAME,
        path="/",
        secure=auth.config.cookie_secure,
        httponly=True,
        samesite="strict",
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@app.post("/api/inspect")
async def inspect_media(request: InspectRequest):
    try:
        url = validate_media_url(request.url)

        def extract():
            with YoutubeDL({"quiet": True, "no_warnings": True, "noplaylist": True, "skip_download": True}) as ydl:
                return ydl.extract_info(url, download=False)

        info = await run_in_threadpool(extract)
        if not isinstance(info, dict):
            raise ValueError("无法读取该链接的媒体信息。")
        formats = info.get("formats") or []
        heights = sorted({int(item["height"]) for item in formats if item.get("height")}, reverse=True)
        return {
            "title": info.get("title") or "未知标题",
            "thumbnail": info.get("thumbnail"),
            "uploader": info.get("uploader") or info.get("channel"),
            "duration": info.get("duration"),
            "webpage_url": info.get("webpage_url") or url,
            "qualities": heights[:12],
            "is_live": bool(info.get("is_live")),
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=(str(exc).strip() or "解析失败")[:320]) from exc


@app.get("/api/downloads")
async def list_downloads():
    return {"items": manager.list()}


@app.post("/api/downloads", status_code=202)
async def create_download(request: DownloadRequest):
    try:
        return manager.create(
            request.url,
            quality=request.quality,
            mode=request.mode,
            audio_format=request.audio_format,
            playlist=request.playlist,
            title=request.title,
            thumbnail=request.thumbnail,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/downloads/{job_id}/retry", status_code=202)
async def retry_download(job_id: str):
    try:
        job = manager.retry(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not job:
        raise HTTPException(status_code=404, detail="找不到该下载任务。")
    return job


@app.get("/api/downloads/{job_id}")
async def get_download(job_id: str):
    job = manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="找不到该下载任务。")
    return job


@app.delete("/api/downloads/{job_id}")
async def cancel_download(job_id: str):
    job = manager.cancel(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="找不到该下载任务。")
    return job


@app.get("/api/files")
async def list_files():
    items = []
    for path in sorted(DOWNLOAD_DIR.iterdir(), key=lambda item: item.stat().st_mtime, reverse=True):
        if path.is_file() and not path.name.startswith("."):
            stat = path.stat()
            items.append({"name": path.name, "size": stat.st_size, "modified": stat.st_mtime})
    return {"items": items[:200]}


@app.get("/api/files/{filename}")
async def download_file(filename: str):
    target = (DOWNLOAD_DIR / filename).resolve()
    if target.parent != DOWNLOAD_DIR or not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在。")
    return FileResponse(target, filename=target.name)


app.mount("/", StaticFiles(directory="app/static", html=True), name="static")
