"""Fast checks for the Instagram Reel delivery guardrail."""

from scripts.ig_reel_preflight import check_public_url, validate_caption, validate_video


GOOD_CAPTION = (
    "A builder's ads can work while the enquiry handoff loses momentum.\n\n"
    "Check where the delay starts before buying more traffic.\n\n"
    "DM MAP if you want to inspect that path.\n\n"
    "#CustomHomeBuilder #MetaAds #LeadQualification"
)


def good_probe() -> dict:
    return {
        "format": {"duration": "25.0"},
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 720,
                "height": 1280,
                "r_frame_rate": "30/1",
            },
            {"codec_type": "audio", "codec_name": "aac", "sample_rate": "48000"},
        ],
    }


def test_caption_keeps_real_paragraphs_and_spaced_hashtags():
    assert validate_caption(GOOD_CAPTION) == []
    assert any("blank lines" in error for error in validate_caption(GOOD_CAPTION.replace("\n\n", " ")))
    assert any("space-separated" in error for error in validate_caption(GOOD_CAPTION.replace(" #MetaAds", "#MetaAds")))


def test_reel_rejects_96khz_and_missing_audio():
    probe = good_probe()
    assert validate_video(probe, 1_000_000) == []
    probe["streams"][1]["sample_rate"] = "96000"
    assert "audio sample rate must be 48 kHz" in validate_video(probe, 1_000_000)
    probe["streams"].pop()
    assert "informational OROVA Reels require an audio stream" in validate_video(probe, 1_000_000)


def test_reel_rejects_wrong_aspect_and_frame_rate():
    probe = good_probe()
    probe["streams"][0].update({"width": 1280, "height": 720, "r_frame_rate": "15/1"})
    errors = validate_video(probe, 1_000_000)
    assert any("9:16" in error for error in errors)
    assert any("frame rate" in error for error in errors)


def test_url_requires_public_https_without_credentials():
    assert check_public_url("http://example.com/video.mp4", 100)[0]
    assert check_public_url("https://user:secret@example.com/video.mp4", 100)[0]
