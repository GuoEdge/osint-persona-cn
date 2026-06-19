"""路径安全校验测试."""

from __future__ import annotations

import pytest

from osint_toolkit.utils.safe_path import (
    PathSecurityError,
    assert_domain,
    assert_prompt_name,
    assert_run_id,
    assert_safe_filename,
    resolve_under,
)


def test_assert_run_id_valid():
    assert assert_run_id("20260101-120000-aabbccdd") == "20260101-120000-aabbccdd"


def test_assert_run_id_rejects_traversal():
    with pytest.raises(PathSecurityError):
        assert_run_id("../etc/passwd")


def test_assert_safe_filename_rejects_path_segments():
    with pytest.raises(PathSecurityError):
        assert_safe_filename("../manifest.json")


def test_assert_domain_rejects_path():
    with pytest.raises(PathSecurityError):
        assert_domain("../../config")


def test_assert_prompt_name_rejects_invalid():
    with pytest.raises(PathSecurityError):
        assert_prompt_name("../evil")


def test_resolve_under_blocks_escape(tmp_path):
    root = tmp_path / "runs"
    root.mkdir()
    with pytest.raises(PathSecurityError):
        resolve_under(root, "..", "secret.txt")
