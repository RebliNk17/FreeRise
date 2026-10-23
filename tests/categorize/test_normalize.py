from freerise.categorize.normalize import normalize_merchant as n


def test_normalize_strips_reference_codes():
    assert n("SPOTIFY P420ECF50D") == "spotify"
    assert n("SPOTIFY P47973AA10") == "spotify"
    assert n("GOOGLE*CLOUD QZ9RNW") == "google cloud"
    assert n("117-4126685/13054296/OnePlusJ - דמי מנוי") == n(
        "117-4784059/16845191/OnePlusJ - דמי מנוי"
    )
    assert n("מ. יוחננוף ובניו-  ר") == "מ יוחננוף ובניו ר"
    assert n("") == ""


def test_all_reference_tokens_fall_back():
    assert n("7eleven") == "7eleven"
    assert n("12345678") == "12345678"
