"""Canonical prompt renderer for the prospect-initiated inbound demo."""
from scripts.render_retell_inbound_prompt import render_prompt


def test_capture_mode_is_consent_first_and_fail_closed():
    package = render_prompt()
    begin = package["begin_message"].lower()
    prompt = package["general_prompt"].lower()
    assert "ai assistant" in begin
    assert "recorded" in begin and "okay to continue" in begin
    assert "permission" in prompt and "before asking any other question" in prompt
    assert "simulation" in prompt
    assert "too few leads" in prompt and "chasing and screening" in prompt
    assert "15-minute" in prompt
    assert "no price, no trial, no pilot" in prompt
    assert "do not call either cal tool" in prompt
    assert package["booking_mode"] == "capture"


def test_verified_mode_requires_availability_then_explicit_booking():
    prompt = render_prompt(booking_mode="verified")["general_prompt"].lower()
    availability = prompt.index("check_availability_cal")
    booking = prompt.index("book_appointment_cal")
    assert availability < booking
    assert "only after the caller chooses that slot" in prompt
    assert "only after the booking tool succeeds" in prompt


def test_renderer_does_not_use_inbound_template_variables():
    package = render_prompt()
    combined = package["begin_message"] + package["general_prompt"]
    assert "{{" not in combined and "}}" not in combined
