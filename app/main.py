from __future__ import annotations

from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from yt_dlp import YoutubeDL

from app.downloads import DOWNLOAD_DIR, manager, validate_media_url


app = FastAPI(
    title="YtFlow",
    version="0.1.0",
    description="A local web video downloader powered by yt-dlp.",
)


class InspectRequest(BaseModel):
    url: str = Field(min_length=8, max_length=4096)


class DownloadRequest(BaseModel):
    url: str = Field(min_length=8, max_length=4096)
    quality: Literal["best", "2160p", "1440p", "1080p", "720p", "480p", "360p"] = "best"
    mode: Literal["video", "audio"] = "video"
    audio_format: Literal["mp3", "m4a", "wav", "opus"] = "mp3"
    playlist: bool = False
    title: str | None = Field(default=None, max_length=240)
    thumbnail: str | None = Field(default=None, max_length=4096)


@app.get("/api/health")
async def health():
    return {"ok": True, "name": "YtFlow", "version": app.version}


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
