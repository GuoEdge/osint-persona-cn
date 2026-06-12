"""WBI signing tests."""

from osint_toolkit.ingest.bilibili_wbi import sign_wbi_params


def test_sign_wbi_params_deterministic_with_fixed_time(monkeypatch):
    monkeypatch.setattr("osint_toolkit.ingest.bilibili_wbi.time.time", lambda: 1700000000)
    img = "7cd084941338484aae1ad9425b84077c"
    sub = "4932caff0ff746eab6f01bf08b70ac45"
    signed = sign_wbi_params({"foo": "114", "bar": "514"}, img, sub)
    assert signed["wts"] == "1700000000"
    assert "w_rid" in signed
    assert len(signed["w_rid"]) == 32
