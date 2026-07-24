"""Unit tests for the ad-signal detector in app/skills/light_enrich.py.

The detector exists because Nova cannot query the Meta Ad Library (political
ads only via API, browser-only UI, and scraping Meta risks the ad account the
business runs on). The same signal is free in the prospect's own homepage HTML.

The tests that matter most here are the FALSE-POSITIVE ones: a signal that
fires on every site is worse than no signal, because it silently poisons the
ICP qualifier "already paying for leads" instead of leaving it blank.
"""
import json

from app.skills.light_enrich import detect_ad_signals, ad_signals_json


# ─── Meta Pixel ──────────────────────────────────────────────────

def test_meta_pixel_detected_from_fbevents():
    html = """<html><head><script>
      !function(f,b,e,v,n,t,s){...}(window,document,'script',
      'https://connect.facebook.net/en_US/fbevents.js');
      fbq('init', '123456789'); fbq('track', 'PageView');
    </script></head><body>Kitchens</body></html>"""
    assert detect_ad_signals(html)["meta_pixel"] is True


def test_meta_pixel_detected_from_noscript_beacon():
    html = '<noscript><img src="https://www.facebook.com/tr?id=99&ev=PageView"/></noscript>'
    assert detect_ad_signals(html)["meta_pixel"] is True


def test_own_facebook_page_link_is_not_a_pixel():
    # FALSE POSITIVE GUARD: bare "facebook.com/tr" is a substring of ordinary
    # page URLs like /treehouseremodeling and /tributes — and linking your own
    # Facebook page is the most common thing on a contractor site, so the loose
    # form fired almost everywhere. The beacon must keep its query separator.
    html = '<a href="https://www.facebook.com/treehouseremodeling">Follow us</a>'
    assert detect_ad_signals(html)["meta_pixel"] is False


def test_facebook_social_plugin_is_not_a_pixel():
    # FALSE POSITIVE GUARD: connect.facebook.net also serves sdk.js for like
    # buttons and social login. A like button is not an ad buyer.
    html = """<html><head>
      <script async src="https://connect.facebook.net/en_US/sdk.js#xfbml=1"></script>
      </head><body><div class="fb-like"></div></body></html>"""
    assert detect_ad_signals(html)["meta_pixel"] is False


# ─── Google Ads (not Google Analytics) ───────────────────────────

def test_google_ads_detected_from_conversion_id():
    html = """<script src="https://www.googletagmanager.com/gtag/js?id=AW-987654321"></script>
      <script>gtag('config', 'AW-987654321');</script>"""
    assert detect_ad_signals(html)["google_ads"] is True


def test_google_ads_detected_from_adservices_host():
    html = '<script src="https://www.googleadservices.com/pagead/conversion.js"></script>'
    assert detect_ad_signals(html)["google_ads"] is True


def test_plain_google_analytics_is_not_google_ads():
    # FALSE POSITIVE GUARD: a G- measurement ID is analytics, which sits on
    # roughly half the web. Flagging it as "runs ads" makes the field useless.
    html = """<script src="https://www.googletagmanager.com/gtag/js?id=G-ABC123"></script>
      <script>gtag('config', 'G-ABC123');</script>"""
    assert detect_ad_signals(html)["google_ads"] is False


def test_aw_prefixed_css_class_is_not_google_ads():
    # FALSE POSITIVE GUARD: "aw-" is a real CSS prefix in some themes.
    html = '<div class="aw-header aw-wrapper"><span class="aw-title">Remodels</span></div>'
    assert detect_ad_signals(html)["google_ads"] is False


# ─── Lead marketplaces (the competitor to displace) ──────────────

def test_angi_badge_names_the_competitor():
    html = '<a href="https://www.angi.com/companylist/us/ca/acme-remodeling.htm">Our reviews</a>'
    signals = detect_ad_signals(html)
    assert signals["paying_for_leads"] == ["angi"]


def test_multiple_marketplaces_all_recorded_sorted():
    html = """<footer>
      <a href="https://www.houzz.com/pro/acme">Houzz</a>
      <a href="https://www.homeadvisor.com/rated.Acme.12345.html">HomeAdvisor</a>
    </footer>"""
    assert detect_ad_signals(html)["paying_for_leads"] == ["homeadvisor", "houzz"]


def test_angieslist_legacy_domain_counts_as_angi():
    html = '<a href="https://www.angieslist.com/companylist/acme.htm">Reviews</a>'
    assert detect_ad_signals(html)["paying_for_leads"] == ["angi"]


def test_ordinary_copy_containing_angi_substring_is_not_a_marketplace():
    # FALSE POSITIVE GUARD — the single most important test in this file.
    # "angi" is a substring of changing/ranging/hanging/exchanging, all of
    # which are ordinary remodeler marketing copy. A bare substring match
    # would flag essentially every prospect as "already paying for leads".
    html = """<p>We specialize in changing tired kitchens into showpieces,
      hanging custom cabinetry, and remodels ranging from $80,000 upward.</p>"""
    assert detect_ad_signals(html)["paying_for_leads"] == []


def test_marketplace_subdomain_still_counts():
    html = '<a href="https://pro.angi.com/dashboard">Our Angi profile</a>'
    assert detect_ad_signals(html)["paying_for_leads"] == ["angi"]


def test_protocol_relative_link_still_counts():
    html = '<img src="//www.homeadvisor.com/badge/screened-approved.png"/>'
    assert detect_ad_signals(html)["paying_for_leads"] == ["homeadvisor"]


def test_longer_host_ending_in_a_marketplace_domain_does_not_fire():
    # FALSE POSITIVE GUARD: a plain "angi.com" substring check also matches the
    # unrelated host notangi.com. The host match must be left-anchored.
    html = '<a href="https://notangi.com/blog">Not a marketplace</a>'
    assert detect_ad_signals(html)["paying_for_leads"] == []


def test_prose_mention_of_a_marketplace_is_not_evidence_of_paying():
    # FALSE POSITIVE GUARD, and the one that would have been backwards: a
    # business writing "unlike angi.com, we don't sell your info" is saying it
    # does NOT pay for leads. A substring match would have recorded the exact
    # opposite of the truth and fed it to the ICP qualifier.
    html = "<p>Unlike angi.com and homeadvisor.com, we never sell your information.</p>"
    assert detect_ad_signals(html)["paying_for_leads"] == []


def test_marketplace_absent_when_no_links():
    html = "<html><body><h1>Acme Custom Homes</h1></body></html>"
    assert detect_ad_signals(html)["paying_for_leads"] == []


# ─── Lead-gen CTA / marketing maturity ───────────────────────────

def test_free_estimate_cta_marks_marketing_mature():
    html = '<a class="cta" href="/contact">Get Your Free Estimate</a>'
    assert detect_ad_signals(html)["marketing_mature"] is True


def test_brochure_site_without_cta_is_not_marketing_mature():
    html = "<html><body><h1>Acme Custom Homes</h1><p>Call us at 555-0100.</p></body></html>"
    assert detect_ad_signals(html)["marketing_mature"] is False


# ─── Contract / robustness ───────────────────────────────────────

def test_empty_and_non_string_input_never_raises():
    for bad in ("", None, 12345, b"<html>", []):
        signals = detect_ad_signals(bad)
        assert signals == {"meta_pixel": False, "google_ads": False,
                           "paying_for_leads": [], "marketing_mature": False}


def test_detector_never_fabricates_on_a_bare_page():
    signals = detect_ad_signals("<html><body>Hello</body></html>")
    assert signals["meta_pixel"] is False
    assert signals["google_ads"] is False
    assert signals["paying_for_leads"] == []
    assert signals["marketing_mature"] is False


def test_full_signal_page_reads_every_field():
    html = """<html><head>
      <script src="https://connect.facebook.net/en_US/fbevents.js"></script>
      <script src="https://www.googletagmanager.com/gtag/js?id=AW-111222333"></script>
      </head><body>
      <a href="/estimate">Request a Quote</a>
      <a href="https://www.thumbtack.com/ca/acme">Thumbtack</a>
      </body></html>"""
    assert detect_ad_signals(html) == {
        "meta_pixel": True,
        "google_ads": True,
        "paying_for_leads": ["thumbtack"],
        "marketing_mature": True,
    }


# ─── Storage serialization ───────────────────────────────────────

def test_ad_signals_json_roundtrips():
    html = '<script src="https://connect.facebook.net/en_US/fbevents.js"></script>'
    parsed = json.loads(ad_signals_json(html))
    assert parsed["meta_pixel"] is True


def test_unread_page_stays_empty_string_not_all_false_json():
    # "" means never checked; a JSON blob of all-false means checked and clean.
    # Conflating them would let the UI claim a prospect runs no ads when in
    # fact nobody ever looked at their site.
    assert ad_signals_json("") == ""
    assert ad_signals_json(None) == ""
    assert json.loads(ad_signals_json("<html>x</html>"))["meta_pixel"] is False
