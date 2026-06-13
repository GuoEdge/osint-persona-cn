"""系统一致性与注册表核验 / System consistency checks."""

from __future__ import annotations

import importlib
import inspect

import pytest

from osint_toolkit.collectors.base import BaseCollector
from osint_toolkit.collectors.registry import COLLECTORS, DEFAULT_SEARCH_SOURCES, PROBE_SOURCES, normalize_sources
from osint_toolkit.services import search as search_service
from osint_toolkit.web import schemas as web_schemas


def test_collector_registry_complete():
    assert set(COLLECTORS) == {"zhihu", "bilibili", "web", "v2ex", "rss", "weixin"}
    for name, cls in COLLECTORS.items():
        assert cls.name == name
        assert issubclass(cls, BaseCollector)
        assert inspect.iscoroutinefunction(cls.search)
        assert inspect.iscoroutinefunction(cls.fetch)


def test_default_sources_in_registry():
    for source in DEFAULT_SEARCH_SOURCES:
        assert source in COLLECTORS


def test_probe_sources_subset_of_collectors():
    for source in PROBE_SOURCES:
        assert source in COLLECTORS


def test_search_service_exports_registry():
    assert search_service.COLLECTORS is COLLECTORS


def test_web_schema_default_sources():
    req = web_schemas.SearchRequest(query="test")
    assert req.sources == DEFAULT_SEARCH_SOURCES


def test_normalize_sources_filters_unknown():
    valid, unknown = normalize_sources(["zhihu", "nope", "web"], profile="default")
    assert "zhihu" in valid
    assert "web" in valid
    assert "nope" in unknown
    assert "nope" not in valid


def test_normalize_sources_falls_back_to_default_when_empty():
    valid, unknown = normalize_sources(["missing"], profile="default")
    assert valid == DEFAULT_SEARCH_SOURCES
    assert unknown == ["missing"]


@pytest.mark.parametrize(
    "module_path",
    [
        "osint_toolkit.collectors.zhihu",
        "osint_toolkit.collectors.bilibili",
        "osint_toolkit.collectors.web",
        "osint_toolkit.collectors.weixin",
        "osint_toolkit.collectors.v2ex",
        "osint_toolkit.collectors.rss",
        "osint_toolkit.collectors.serp.engine",
        "osint_toolkit.services.search",
        "osint_toolkit.services.save",
        "osint_toolkit.services.ingest",
        "osint_toolkit.services.health",
    ],
)
def test_core_modules_importable(module_path: str):
    importlib.import_module(module_path)
