"""JSON util tests."""

from osint_toolkit.ai.json_util import parse_json_array


def test_parse_json_array_from_codeblock():
    text = '说明\n```json\n[{"item_id":"a","interest":"skip"}]\n```'
    out = parse_json_array(text)
    assert len(out) == 1
    assert out[0]["item_id"] == "a"
