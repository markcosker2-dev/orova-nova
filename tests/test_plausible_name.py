"""Owner-name quality gate (_is_plausible_name in lead_gen_v3).

Live hunt 2026-07-12 surfaced junk "owner" names — "Maintenance Manual",
"Member Circles" — scraped from page titles / WHOIS org fields. The validator
only checked shape (2-4 capitalized words), so business phrases passed. These
tests pin the strengthened check: real people accepted, business/page phrases
rejected, and real surnames that collide with business words NOT over-rejected.
"""
from app.skills.lead_gen_v3 import _is_plausible_name


def test_real_names_accepted():
    for name in ["Todd Rowsell", "Kim Malek", "Maria Lopez", "Jean-Luc Picard",
                 "Mary Anne Smith", "O'Brien Kelly"]:
        assert _is_plausible_name(name), f"should accept real name: {name}"


def test_business_and_page_phrases_rejected():
    for junk in ["Maintenance Manual", "Member Circles", "Auto Repair",
                 "California Auto", "Premium Detailing", "Acme LLC",
                 "Contact Us", "About Team", "Search Results", "Motor Group"]:
        assert not _is_plausible_name(junk), f"should reject junk: {junk}"


def test_surnames_that_look_like_words_still_accepted():
    # These collide with common nouns but ARE real surnames — must NOT be
    # over-rejected (the denylist deliberately excludes them).
    for name in ["John Baker", "Sarah Page", "David Mason", "Emily Wood",
                 "James Taylor", "Anna Berry"]:
        assert _is_plausible_name(name), f"real surname wrongly rejected: {name}"


def test_sentence_fragments_rejected():
    # Live prod 2026-07-13: the owner-name extractor stored sentence fragments
    # scraped from page copy. Each carries a lowercase function word, so the
    # Title-Case check must reject them.
    for junk in ["When you are an", "Now under the", "Christine Lally Department of",
                 "Keith Mayou While others", "Slider with alias", "When you",
                 "Call us today", "Serving the community"]:
        assert not _is_plausible_name(junk), f"fragment wrongly accepted: {junk}"


def test_lowercase_name_particles_allowed():
    # Real names with lowercase particles must still pass.
    for name in ["Ludwig van Beethoven", "Vincent van Gogh", "Robert de Niro",
                 "Oscar de la Renta"]:
        assert _is_plausible_name(name), f"particle name wrongly rejected: {name}"


def test_shape_rejects_still_hold():
    assert not _is_plausible_name("")            # empty
    assert not _is_plausible_name("Bob")         # single token
    assert not _is_plausible_name("A B C D E")   # too many tokens
    assert not _is_plausible_name("john123 smith")  # non-alpha
