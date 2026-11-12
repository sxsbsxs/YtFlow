import pytest

from app.downloads import AUDIO_FORMATS, QUALITY_FORMATS, build_ydl_options, validate_media_url


def test_quality_options_cover_common_resolutions():
    assert {"best", "2160p", "1440p", "1080p", "720p", "480p", "360p"} == set(QUALITY_FORMATS)


def test_video_options_use_ffmpeg_merge_container():
    options = build_ydl_options(quality="1080p")
    assert options["merge_output_format"] == "mp4"
    assert "height<=1080" in options["format"]


def test_audio_options_add_extractor():
    options = build_ydl_options(mode="audio", audio_format="mp3")
    assert options["postprocessors"][0]["preferredcodec"] == "mp3"


def test_audio_formats_are_supported():
    assert {"mp3", "m4a", "wav", "opus"} == AUDIO_FORMATS


@pytest.mark.parametrize("url", ["ftp://example.com/video", "file:///etc/passwd", "http://localhost/a", "http://127.0.0.1/a"])
def test_rejects_unsupported_or_local_urls(url):
    with pytest.raises(ValueError):
        validate_media_url(url)


def test_accepts_https_url():
    assert validate_media_url("https://example.com/watch?v=123") == "https://example.com/watch?v=123"
