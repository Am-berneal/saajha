from saajha_core.numparse import parse_bill


def test_hinglish_rate_marker():
    d = parse_bill("sharma ji ko 50 cotton kurta 400 wale")
    assert d["buyer"]["name"] == "Sharma Traders Pvt Ltd"
    assert (d["items"][0]["qty"], d["items"][0]["rate"]) == (50, 400)


def test_rate_before_quantity_with_fraction_words():
    d = parse_bill("sharma ji ko saadhe teen sau ke 12 dupatte")
    assert (d["items"][0]["qty"], d["items"][0]["rate"]) == (12, 350)


def test_devanagari_words():
    d = parse_bill("शर्मा जी को पचास कुर्ते चार सौ वाले")
    assert (d["items"][0]["qty"], d["items"][0]["rate"]) == (50, 400)


def test_missing_rate_asks_instead_of_guessing():
    d = parse_bill("gupta ji ko 10 saree")
    assert d["questions"] and not d["items"][0]["rate"]
