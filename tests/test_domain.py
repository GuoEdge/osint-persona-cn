"""域名采集模块测试 / Domain collector tests."""

from osint_toolkit.collectors.domain import collect_domain_info


def test_collect_domain_info_structure():
    result = collect_domain_info("example.com")
    assert result["domain"] == "example.com"
    assert "dns_records" in result
    assert isinstance(result["dns_records"], list)
