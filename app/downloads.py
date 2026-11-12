from __future__ import annotations

import ipaddress
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError


DOWNLOAD_DIR = Path(os.getenv("YTFLOW_DOWNLOAD_DIR", "downloads")).expanduser().resolve()
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

QUALITY_FORMATS = {
    "best": "bv*+ba/b",
    "2160p": "bestvideo[height<=2160]+bestaudio/best[height<=2160]",
    "1440p": "bestvideo[height<=1440]+bestaudio/best[height<=1440]",
    "1080p": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
    "720p": "bestvideo[height<=720]+bestaudio/best[height<=720]",
    "480p": "bestvideo[height<=480]+bestaudio/best[height<=480]",
    "360p": "bestvideo[height<=360]+bestaudio/best[height<=360]",
}
AUDIO_FORMATS = {"mp3", "m4a", "wav", "opus"}


def validate_media_url(value: str) -> str:
    """Accept web URLs only; reject credentials and obvious local/private targets."""
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("请输入有效的 http:// 或 https:// 视频链接。")
    if parsed.username or parsed.password:
        raise ValueError("链接中不能包含用户名或密码。")
    host = parsed.hostname.rstrip(".").lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".localhost"):
        raise ValueError("出于安全考虑，不允许访问本机地址。")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address and (address.is_private or address.is_loopback or address.is_link_local or address.is_reserved):
        raise ValueError("出于安全考虑，不允许访问内网或保留 IP 地址。")
    return value.strip()


def build_ydl_options(
    *,
    quality: str = "best",
    mode: str = "video",
    audio_format: str = "mp3",
    playlist: bool = False,
    progress_hook=None,
) -> dict[str, Any]:
    if mode not in {"video", "audio"}:
        raise ValueError("不支持的下载类型。")
    if mode == "video" and quality not in QUALITY_FORMATS:
        raise ValueError("不支持的画质选项。")
    if mode == "audio" and audio_format not in AUDIO_FORMATS:
        raise ValueError("不支持的音频格式。")

    options: dict[str, Any] = {
        "format": QUALITY_FORMATS[quality] if mode == "video" else "bestaudio/best",
        "paths": {"home": str(DOWNLOAD_DIR)},
        "outtmpl": "%(title).180B [%(id)s].%(ext)s",
        "windowsfilenames": True,
        "trim_file_name": 180,
        "noplaylist": not playlist,
        "continuedl": True,
        "retries": 3,
        "fragment_retries": 3,
        "file_access_retries": 3,
        "overwrites": False,
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": False,
        "restrictfilenames": False,
    }
    if mode == "video":
        options["merge_output_format"] = "mp4"
    else:
        options["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": audio_format,
            "preferredquality": "192",
        }]
    if progress_hook:
        options["progress_hooks"] = [progress_hook]
    return options


class DownloadManager:
    def __init__(self, workers: int = 2) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max(1, workers), thread_name_prefix="ytflow")
        self._lock = threading.RLock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._cancel: dict[str, threading.Event] = {}

    def create(
        self,
        url: str,
        quality: str = "best",
        mode: str = "video",
        audio_format: str = "mp3",
        playlist: bool = False,
    ) -> dict[str, Any]:
        safe_url = validate_media_url(url)
        # Validate options before accepting a job.
        build_ydl_options(quality=quality, mode=mode, audio_format=audio_format, playlist=playlist)

        with self._lock:
            if len(self._jobs) >= 100:
                raise ValueError("任务数量已达到上限，请先清理任务。")
            job_id = uuid.uuid4().hex[:12]
            job = {
                "id": job_id,
                "url": safe_url,
                "title": safe_url,
                "thumbnail": None,
                "status": "queued",
                "progress": 0.0,
                "speed": None,
                "eta": None,
                "downloaded": None,
                "total": None,
                "message": "等待下载",
                "quality": quality,
                "mode": mode,
                "audio_format": audio_format,
                "playlist": playlist,
                "created_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
            }
            self._jobs[job_id] = job
            self._cancel[job_id] = threading.Event()

        self._executor.submit(self._run, job_id)
        return self._public(job)

    def _update(self, job_id: str, **changes: Any) -> None:
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id].update(changes)

    def _run(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            cancel_event = self._cancel.get(job_id)
            if not job or not cancel_event:
                return
            if cancel_event.is_set():
                job.update(status="cancelled", message="已取消")
                return
            url = job["url"]
            quality = job["quality"]
            mode = job["mode"]
            audio_format = job["audio_format"]
            playlist = job["playlist"]

        self._update(job_id, status="downloading", message="正在连接媒体源")

        def progress_hook(data: dict[str, Any]) -> None:
            if cancel_event.is_set():
                raise DownloadError("Download cancelled by user")
            state = data.get("status")
            if state == "downloading":
                total = data.get("total_bytes") or data.get("total_bytes_estimate")
                current = data.get("downloaded_bytes", 0)
                percent = (current / total * 100) if total else 0
                self._update(
                    job_id,
                    status="downloading",
                    progress=round(min(percent, 99.9), 1),
                    speed=data.get("speed"),
                    eta=data.get("eta"),
                    downloaded=current,
                    total=total,
                    message="正在下载",
                )
            elif state == "finished":
                self._update(job_id, status="processing", progress=99.9, speed=None, eta=None, message="下载完成，正在处理文件")

        options = build_ydl_options(
            quality=quality,
            mode=mode,
            audio_format=audio_format,
            playlist=playlist,
            progress_hook=progress_hook,
        )
        try:
            with YoutubeDL(options) as ydl:
                info = ydl.extract_info(url, download=False)
                if isinstance(info, dict):
                    title = info.get("title") or info.get("playlist_title") or url
                    thumbnail = info.get("thumbnail")
                    self._update(job_id, title=str(title)[:240], thumbnail=thumbnail)
                if cancel_event.is_set():
                    raise DownloadError("Download cancelled by user")
                ydl.download([url])
            if cancel_event.is_set():
                self._update(job_id, status="cancelled", message="已取消", speed=None, eta=None)
            else:
                self._update(job_id, status="completed", progress=100.0, message="下载完成", speed=None, eta=None)
        except Exception as exc:  # yt-dlp surfaces site-specific errors through several exception types
            if cancel_event.is_set() or "cancelled by user" in str(exc).lower():
                self._update(job_id, status="cancelled", message="已取消", speed=None, eta=None)
            else:
                self._update(job_id, status="failed", message=(str(exc).strip() or "下载失败")[:320], speed=None, eta=None)

    def cancel(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            event = self._cancel.get(job_id)
            if not job or not event:
                return None
            if job["status"] in {"completed", "failed", "cancelled"}:
                return self._public(job)
            event.set()
            if job["status"] == "queued":
                job.update(status="cancelled", message="已取消")
            else:
                job.update(message="正在停止下载…")
            return self._public(job)

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return self._public(job) if job else None

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            jobs = sorted(self._jobs.values(), key=lambda item: item["created_at"], reverse=True)
            return [self._public(job) for job in jobs]

    @staticmethod
    def _public(job: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in job.items() if key not in {"url"}}


manager = DownloadManager(workers=int(os.getenv("YTFLOW_WORKERS", "2")))
