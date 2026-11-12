from app.downloads import DownloadManager


def test_job_history_survives_restart_and_can_be_retried(tmp_path):
    db_path = tmp_path / "ytflow.sqlite3"

    first = DownloadManager(workers=1, db_path=db_path)
    first._executor.submit = lambda *args, **kwargs: None
    created = first.create(
        "https://example.com/watch?v=sample",
        title="Persistent sample",
        quality="1080p",
    )
    first._executor.shutdown(wait=True)

    second = DownloadManager(workers=1, db_path=db_path)
    restored = second.get(created["id"])

    assert restored is not None
    assert restored["title"] == "Persistent sample"
    assert restored["status"] == "failed"
    assert "服务重启" in restored["message"]
    assert "url" not in restored

    second._executor.submit = lambda *args, **kwargs: None
    retried = second.retry(created["id"])
    assert retried["status"] == "queued"
    assert retried["id"] != created["id"]
    second._executor.shutdown(wait=True)
