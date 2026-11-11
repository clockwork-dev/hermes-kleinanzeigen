"""Comprehensive unit and CLI integration tests for the Kleinanzeigen skill."""

from __future__ import annotations

from datetime import datetime
import html as html_lib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tomllib
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import skills.kleinanzeigen.scripts as scripts  # noqa: E402
from skills.kleinanzeigen.scripts import kleinanzeigen_api as api  # noqa: E402
from skills.kleinanzeigen.scripts import monitor, search_cli  # noqa: E402


EXPECTED_KEYS = {
    "id",
    "title",
    "price",
    "location",
    "url",
    "image_url",
    "description",
}


BEM_HTML = """
<!DOCTYPE html>
<html lang="de">
<body>
  <ul id="srchrslt-adtable" class="itemlist">
    <li class="ad-listitem"></li>
    <li class="ad-listitem ad-banner">
      <div class="banner">Werbung</div>
    </li>
    <li class="ad-listitem is-topad">
      <article class="aditem is-topad" data-adid="900000001" data-href="/s-anzeige/top-bike/900000001-217-3352">
        <div class="aditem-image">
          <img src="https://img.kleinanzeigen.de/top.jpg" alt="Top Bike">
        </div>
        <div class="aditem-main">
          <div class="aditem-main--top">
            <div class="aditem-main--top--left">10115 Berlin</div>
            <div class="aditem-main--top--right"><span class="badge-topad">Top-Anzeige</span></div>
          </div>
          <h2 class="aditem-main--title-line"><a href="/s-anzeige/top-bike/900000001-217-3352">Gesponsertes Fahrrad</a></h2>
          <p class="aditem-main--middle--description">Top Anzeige Beschreibung</p>
          <p class="aditem-main--middle--price-shipping--price">999 €</p>
        </div>
      </article>
    </li>
    <li class="ad-listitem">
      <article class="aditem" data-adid="2987654321" data-href="/s-anzeige/gravel-bike-28-zoll/2987654321-217-3352">
        <div class="aditem-image">
          <img src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==" data-src="https://img.kleinanzeigen.de/api/v1/prod-ads/images/ab/abcd.jpg?rule=$_35.JPG" alt="Gravel Bike">
        </div>
        <div class="aditem-main">
          <div class="aditem-main--top">
            <div class="aditem-main--top--left">10115 Berlin-Mitte</div>
            <div class="aditem-main--top--right">Heute, 14:22</div>
          </div>
          <h2 class="aditem-main--title-line">
            <a class="ellipsis" href="/s-anzeige/gravel-bike-28-zoll/2987654321-217-3352">Gravel Bike 28 Zoll Top Zustand</a>
          </h2>
          <p class="aditem-main--middle--description">Kaum gefahrenes Gravel Bike, keine Top-Anzeige nötig.</p>
          <div class="aditem-main--middle--price-shipping">
            <p class="aditem-main--middle--price-shipping--price">420 € VB</p>
          </div>
        </div>
      </article>
    </li>
    <li class="ad-listitem">
      <article class="aditem" data-adid="2987654321">
        <h2 class="aditem-main--title-line"><a href="/s-anzeige/duplicate/2987654321-217-3352">Duplicate Listing</a></h2>
      </article>
    </li>
    <li class="ad-listitem">
      <article class="aditem" data-adid="2987654322">
        <div class="aditem-image">
          <img src="/static/img/citybike.jpg" alt="Citybike">
        </div>
        <div class="aditem-main">
          <div class="aditem-main--top">
            <div class="aditem-main--top--left">10117 Berlin</div>
          </div>
          <h2 class="aditem-main--title-line">
            <a href="https://www.kleinanzeigen.de/s-anzeige/citybike-damen/2987654322-217-3352">Citybike Damen</a>
          </h2>
          <p class="aditem-main--middle--description"></p>
          <p class="aditem-main--middle--price-shipping--price">Zu verschenken</p>
        </div>
      </article>
    </li>
  </ul>
</body>
</html>
"""


TAILWIND_HTML = """
<!DOCTYPE html>
<html lang="de">
<body>
  <ul class="space-y-4">
    <li class="ad-listitem">
      <article class="flex gap-4 p-4 border rounded" data-adid="300000001">
        <div class="imagebox">
          <img srcset="/images/thumb1.jpg 1x, /images/thumb1_2x.jpg 2x" alt="ThinkPad">
        </div>
        <div class="flex-1">
          <div class="flex justify-between">
            <span class="text-xs text-gray-500">80331 München</span>
            <span class="text-xs text-gray-500">Heute, 11:05</span>
          </div>
          <h2 class="text-lg font-semibold">
            <a href="/s-anzeige/thinkpad-t14-gen2/300000001-278-6411">ThinkPad T14 Gen 2</a>
          </h2>
          <p class="text-sm text-gray-700">16GB RAM, 512GB SSD, sehr gepflegt.</p>
          <p class="text-base font-bold">VB</p>
        </div>
      </article>
    </li>
    <li class="ad-listitem">
      <article class="flex gap-4 p-4 border rounded" data-adid="300000002">
        <div class="flex-1">
          <span class="text-xs">Top-Anzeige</span>
          <h2><a href="/s-anzeige/pro-highlight/300000002-278-6411">Highlight Ad</a></h2>
          <p class="font-bold">500 €</p>
        </div>
      </article>
    </li>
    <li class="ad-listitem">
      <article class="flex gap-4 p-4 border rounded" data-adid="300000003">
        <div class="flex-1">
          <div class="flex justify-between">
            <span class="text-xs text-gray-500">20095 Hamburg</span>
          </div>
          <h2><a href="/s-anzeige/thinkpad-x1-carbon/300000003-278-9420">ThinkPad X1 Carbon</a></h2>
          <p class="text-xs text-gray-500">Heute, 09:00</p>
          <div class="aditem-main--middle--price-shipping--shipping">Versand möglich</div>
          <span class="font-bold">650 EUR</span>
        </div>
      </article>
    </li>
  </ul>
</body>
</html>
"""


def _make_html_with_ads(ads: list[tuple[str, str, str, str, str]]) -> str:
    """Build deterministic Kleinanzeigen HTML from (id, title, price, loc, desc) tuples."""
    items = []
    for ad_id, title, price, loc, desc in ads:
        items.append(
            f"""
            <li class="ad-listitem">
              <article class="aditem" data-adid="{ad_id}" data-href="/s-anzeige/item/{ad_id}-217-3352">
                <div class="aditem-image">
                  <img data-src="https://img.kleinanzeigen.de/{ad_id}.jpg" alt="{title}">
                </div>
                <div class="aditem-main">
                  <div class="aditem-main--top">
                    <div class="aditem-main--top--left">{loc}</div>
                  </div>
                  <h2 class="aditem-main--title-line">
                    <a href="/s-anzeige/item/{ad_id}-217-3352">{title}</a>
                  </h2>
                  <p class="aditem-main--middle--description">{desc}</p>
                  <p class="aditem-main--middle--price-shipping--price">{price}</p>
                </div>
              </article>
            </li>
            """
        )
    return f"<!DOCTYPE html><html><body><ul>{''.join(items)}</ul></body></html>"


def _run_cli(
    script_rel: str,
    args: list[str],
    *,
    cwd: Path = REPO_ROOT,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a CLI script with the workspace venv Python and capture UTF-8 output."""
    script_path = REPO_ROOT / script_rel
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return subprocess.run(
        [sys.executable, str(script_path), *args],
        cwd=str(cwd),
        env=merged_env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def test_public_exports() -> None:
    """Package __init__ exposes all required public symbols."""
    assert scripts.ALLOWED_RADII == (0, 5, 10, 20, 30, 50, 100, 150, 200)
    assert scripts.BASE_URL == "https://www.kleinanzeigen.de"
    assert scripts.BLOCKED_RESOURCE_TYPES == frozenset({"image", "media", "font"})
    assert "/liberty/" in scripts.BLOCKED_URL_PATTERNS
    for name in (
        "KleinanzeigenError",
        "ValidationError",
        "KleinanzeigenBlockedError",
        "build_search_url",
        "parse_breadcrumb",
        "parse_listings_html",
        "resolve_location_id",
        "search_listings",
    ):
        assert hasattr(scripts, name)


class TestUrlBuilderAndLocationLookup:
    """Tests for build_search_url and resolve_location_id."""

    def test_build_search_url_query_only(self) -> None:
        url = api.build_search_url("fahrrad")
        assert url == "https://www.kleinanzeigen.de/s-seite:1?keywords=fahrrad"

    def test_build_search_url_full_params(self) -> None:
        url = api.build_search_url(
            query="gravel bike",
            postal_code="10115",
            radius=0,
            min_price=0,
            max_price=500,
            location_id="3352",
            page=2,
        )
        assert url == (
            "https://www.kleinanzeigen.de/s-preis:0:500/s-seite:2?"
            "keywords=gravel+bike&locationStr=10115&locationId=3352&radius=0"
        )

    def test_build_search_url_partial_prices_and_optional_location_id(self) -> None:
        assert (
            api.build_search_url("fahrrad", min_price=50)
            == "https://www.kleinanzeigen.de/s-preis:50:/s-seite:1?keywords=fahrrad"
        )
        assert (
            api.build_search_url("fahrrad", max_price=500)
            == "https://www.kleinanzeigen.de/s-preis::500/s-seite:1?keywords=fahrrad"
        )

        url = api.build_search_url("fahrrad", location_id="3352")
        assert url == "https://www.kleinanzeigen.de/s-seite:1?keywords=fahrrad&locationId=3352"
        assert "locationStr=" not in url
        assert "radius=" not in url

        plz_only = api.build_search_url("fahrrad", postal_code="10115", radius=0)
        assert (
            plz_only
            == "https://www.kleinanzeigen.de/s-seite:1?keywords=fahrrad&locationStr=10115&radius=0"
        )

    @pytest.mark.parametrize(
        "payload,expected",
        [
            ([{"id": "_3352", "name": "10115 Berlin - Mitte"}], "3352"),
            ({"_0": "Deutschland", "_3352": "10115 Berlin"}, "3352"),
            ({"locations": [{"locationId": "6411", "label": "80331 München"}]}, "6411"),
            ({"suggestions": [{"key": "999", "label": "Other"}]}, "999"),
        ],
    )
    def test_resolve_location_id_success(self, payload: Any, expected: str) -> None:
        session = MagicMock()
        response = MagicMock(status_code=200, text="{}", json=MagicMock(return_value=payload))
        session.get.return_value = response

        loc_id = api.resolve_location_id("10115", session=session, headers={"User-Agent": "UA"})
        assert loc_id == expected
        session.get.assert_called_once()

    @pytest.mark.parametrize(
        "resp_kwargs",
        [
            {"status_code": 403, "text": "Forbidden"},
            {"status_code": 200, "text": "cf-turnstile"},
            {"status_code": 200, "text": "not-json", "json": MagicMock(side_effect=ValueError("bad"))},
        ],
    )
    def test_resolve_location_id_fails_silently(self, resp_kwargs: dict[str, Any]) -> None:
        session = MagicMock()
        session.get.return_value = MagicMock(**resp_kwargs)
        assert api.resolve_location_id("10115", session=session, headers=None) is None

    def test_resolve_location_id_network_exception_returns_none(self) -> None:
        session = MagicMock()
        session.get.side_effect = requests.Timeout("timed out")
        assert api.resolve_location_id("10115", session=session, headers=None) is None
        assert api.resolve_location_id("", session=session, headers=None) is None


class TestValidation:
    """Tests for strict parameter validation across API functions."""

    @pytest.mark.parametrize("bad_query", ["", "   ", None, 123])
    def test_invalid_query(self, bad_query: Any) -> None:
        with pytest.raises(api.ValidationError):
            api.build_search_url(bad_query)

    @pytest.mark.parametrize("bad_plz", ["1234", "123456", "abcde", "1011a", 10115])
    def test_invalid_postal_code(self, bad_plz: Any) -> None:
        with pytest.raises(api.ValidationError):
            api.build_search_url("fahrrad", postal_code=bad_plz)

    def test_radius_without_postal_code(self) -> None:
        with pytest.raises(api.ValidationError):
            api.build_search_url("fahrrad", radius=10)

    @pytest.mark.parametrize("bad_radius", [-1, 15, 250, True, False, "10"])
    def test_invalid_radius(self, bad_radius: Any) -> None:
        with pytest.raises(api.ValidationError):
            api.build_search_url("fahrrad", postal_code="10115", radius=bad_radius)

    @pytest.mark.parametrize("bad_price", [-1, True, False, 10.5, "50"])
    def test_invalid_prices(self, bad_price: Any) -> None:
        with pytest.raises(api.ValidationError):
            api.build_search_url("fahrrad", min_price=bad_price)
        with pytest.raises(api.ValidationError):
            api.build_search_url("fahrrad", max_price=bad_price)

    def test_min_greater_than_max_price(self) -> None:
        with pytest.raises(api.ValidationError):
            api.build_search_url("fahrrad", min_price=500, max_price=100)

    def test_equal_and_zero_prices_allowed(self) -> None:
        url = api.build_search_url("fahrrad", min_price=0, max_price=0)
        assert url == "https://www.kleinanzeigen.de/s-preis:0:0/s-seite:1?keywords=fahrrad"

    @pytest.mark.parametrize("bad_limit", [0, -5, True, False, "10"])
    def test_invalid_limit(self, bad_limit: Any) -> None:
        with pytest.raises(api.ValidationError):
            api.parse_listings_html(BEM_HTML, limit=bad_limit)
        with pytest.raises(api.ValidationError):
            api.search_listings("fahrrad", limit=bad_limit, html_override=BEM_HTML)

    @pytest.mark.parametrize("bad_page", [0, -1, True, "1"])
    def test_invalid_page(self, bad_page: Any) -> None:
        with pytest.raises(api.ValidationError):
            api.build_search_url("fahrrad", page=bad_page)


class TestHtmlParsing:
    """Tests for classic BEM and Tailwind HTML listing parsing."""

    def test_parse_bem_cards_filters_top_banners_dups_and_resolves_urls(self) -> None:
        results = api.parse_listings_html(BEM_HTML, limit=10)
        assert len(results) == 2

        first, second = results
        assert set(first.keys()) == EXPECTED_KEYS
        assert first == {
            "id": "2987654321",
            "title": "Gravel Bike 28 Zoll Top Zustand",
            "price": "420 € VB",
            "location": "10115 Berlin-Mitte",
            "url": "https://www.kleinanzeigen.de/s-anzeige/gravel-bike-28-zoll/2987654321-217-3352",
            "image_url": "https://img.kleinanzeigen.de/api/v1/prod-ads/images/ab/abcd.jpg?rule=$_35.JPG",
            "description": "Kaum gefahrenes Gravel Bike, keine Top-Anzeige nötig.",
        }

        assert second == {
            "id": "2987654322",
            "title": "Citybike Damen",
            "price": "Zu verschenken",
            "location": "10117 Berlin",
            "url": "https://www.kleinanzeigen.de/s-anzeige/citybike-damen/2987654322-217-3352",
            "image_url": "https://www.kleinanzeigen.de/static/img/citybike.jpg",
            "description": "",
        }

    def test_parse_bem_include_top_ads(self) -> None:
        results = api.parse_listings_html(BEM_HTML, limit=10, include_top_ads=True)
        assert [item["id"] for item in results] == ["900000001", "2987654321", "2987654322"]

    def test_parse_tailwind_cards_and_shipping_guard(self) -> None:
        results = api.parse_listings_html(TAILWIND_HTML, limit=10)
        assert len(results) == 2

        first, second = results
        assert first == {
            "id": "300000001",
            "title": "ThinkPad T14 Gen 2",
            "price": "VB",
            "location": "80331 München",
            "url": "https://www.kleinanzeigen.de/s-anzeige/thinkpad-t14-gen2/300000001-278-6411",
            "image_url": "https://www.kleinanzeigen.de/images/thumb1.jpg",
            "description": "16GB RAM, 512GB SSD, sehr gepflegt.",
        }
        assert second["id"] == "300000003"
        assert second["price"] == "650 EUR"
        assert second["location"] == "20095 Hamburg"
        assert second["image_url"] is None
        assert second["description"] == ""

    def test_parse_shipping_only_class_never_becomes_price(self) -> None:
        html = """
        <article class="aditem" data-adid="444">
          <h2><a href="/s-anzeige/x/444">Monitor</a></h2>
          <div class="aditem-main--middle--price-shipping--shipping">Versand möglich</div>
        </article>
        """
        results = api.parse_listings_html(html)
        assert len(results) == 1
        assert results[0]["price"] == ""

    def test_parse_tailwind_price_div_with_sibling_shipping_span(self) -> None:
        html = """
        <article class="aditem" data-adid="445">
          <h2><a href="/s-anzeige/x/445">Monitor 27 Zoll</a></h2>
          <div class="flex gap-2">
            <span class="font-bold">150 € VB</span>
            <span class="text-xs">Versand möglich</span>
          </div>
        </article>
        """
        results = api.parse_listings_html(html)
        assert len(results) == 1
        assert results[0]["price"] == "150 € VB"

    def test_parse_limit_truncation_and_empty_inputs(self) -> None:
        html = _make_html_with_ads(
            [
                ("1", "Item 1", "10 €", "10115 Berlin", "Desc 1"),
                ("2", "Item 2", "20 €", "10115 Berlin", "Desc 2"),
                ("3", "Item 3", "30 €", "10115 Berlin", "Desc 3"),
            ]
        )
        results = api.parse_listings_html(html, limit=2)
        assert [item["id"] for item in results] == ["1", "2"]
        assert api.parse_listings_html("   ") == []
        with pytest.raises(api.ValidationError):
            api.parse_listings_html(None)  # type: ignore[arg-type]


class TestFetchBlockAndPlaywrightFallback:
    """Tests for HTTP session fetching, anti-bot block detection, and Playwright fallback."""

    def test_search_listings_http_success_and_headers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        recorded_calls: list[tuple[str, dict[str, Any]]] = []

        class FakeSession:
            def __enter__(self) -> FakeSession:
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def get(self, url: str, **kwargs: Any) -> Any:
                recorded_calls.append((url, kwargs))
                return SimpleNamespace(
                    status_code=200,
                    url=url,
                    text=BEM_HTML,
                    encoding="utf-8",
                    content=BEM_HTML.encode("utf-8"),
                    headers={"Content-Type": "text/html; charset=utf-8"},
                )

        monkeypatch.setattr(api.requests, "Session", FakeSession)
        results = api.search_listings("fahrrad", postal_code="10115", radius=10, limit=2)

        assert len(results) == 2
        assert len(recorded_calls) == 1
        search_url, search_kwargs = recorded_calls[0]
        assert (
            search_url
            == "https://www.kleinanzeigen.de/s-seite:1?keywords=fahrrad&locationStr=10115&radius=10"
        )
        assert search_kwargs["allow_redirects"] is True
        assert search_kwargs["headers"]["Accept-Language"] == "de-DE,de;q=0.9,en;q=0.8"

    @pytest.mark.parametrize(
        "status_code,html",
        [
            (403, "<html><h1>IP-Bereich vorübergehend gesperrt.</h1></html>"),
            (429, "<html>Too Many Requests</html>"),
            (503, "<html>Service Unavailable</html>"),
            (200, "<html><h1>IP-Bereich vor&uuml;bergehend gesperrt.</h1></html>"),
            (200, '<html><div class="cf-turnstile"></div></html>'),
            (200, '<html><div class="g-recaptcha"></div></html>'),
            (200, '<html><div class="hcaptcha"></div></html>'),
            (200, "<html><p>Please verify you are human</p></html>"),
            (200, "<html><title>Just a moment...</title></html>"),
            (200, "<html><title>Access Denied</title></html>"),
        ],
    )
    def test_block_detection_raises_when_no_browser(
        self, monkeypatch: pytest.MonkeyPatch, status_code: int, html: str
    ) -> None:
        class BlockedSession:
            def __enter__(self) -> BlockedSession:
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def get(self, url: str, **kwargs: Any) -> Any:
                return SimpleNamespace(
                    status_code=status_code,
                    url=url,
                    text=html,
                    encoding="utf-8",
                    content=html.encode("utf-8"),
                    headers={"Content-Type": "text/html"},
                )

        monkeypatch.setattr(api.requests, "Session", BlockedSession)
        with pytest.raises(api.KleinanzeigenBlockedError) as exc_info:
            api.search_listings("fahrrad", use_playwright_fallback=False)
        assert exc_info.value.url.startswith(api.BASE_URL)
        assert exc_info.value.reason

    def _patch_blocked_http_and_fake_playwright(
        self,
        monkeypatch: pytest.MonkeyPatch,
        pw_status: int,
        pw_html: str,
        capture: dict[str, Any] | None = None,
    ) -> None:
        class BlockedSession:
            def __enter__(self) -> BlockedSession:
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def get(self, url: str, **kwargs: Any) -> Any:
                return SimpleNamespace(
                    status_code=403,
                    url=url,
                    text="<h1>IP-Bereich vorübergehend gesperrt.</h1>",
                    encoding="utf-8",
                    content=b"",
                    headers={},
                )

        class FakePage:
            url = "https://www.kleinanzeigen.de/s-suchanfrage.html?keywords=fahrrad"

            def goto(self, url: str, **kwargs: Any) -> Any:
                if capture is not None:
                    capture["goto_kwargs"] = kwargs
                return SimpleNamespace(status=pw_status)

            def content(self) -> str:
                return pw_html

        class FakeContext:
            def new_page(self) -> FakePage:
                return FakePage()

            def close(self) -> None:
                return None

        class FakeBrowser:
            def new_context(self, **kwargs: Any) -> FakeContext:
                if capture is not None:
                    capture["context_kwargs"] = kwargs
                return FakeContext()

            def close(self) -> None:
                return None

        class FakePlaywrightCM:
            def __enter__(self) -> Any:
                return SimpleNamespace(
                    chromium=SimpleNamespace(launch=lambda **kw: FakeBrowser())
                )

            def __exit__(self, *args: object) -> None:
                return None

        monkeypatch.setattr(api.requests, "Session", BlockedSession)
        fake_sync_api = SimpleNamespace(sync_playwright=lambda: FakePlaywrightCM())
        monkeypatch.setitem(sys.modules, "playwright", SimpleNamespace(sync_api=fake_sync_api))
        monkeypatch.setitem(sys.modules, "playwright.sync_api", fake_sync_api)

    def test_playwright_fallback_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        capture: dict[str, Any] = {}
        self._patch_blocked_http_and_fake_playwright(
            monkeypatch, pw_status=200, pw_html=BEM_HTML, capture=capture
        )

        results = api.search_listings("fahrrad", use_playwright_fallback=True, limit=5)
        assert len(results) == 2
        assert capture["context_kwargs"]["locale"] == "de-DE"
        assert capture["goto_kwargs"]["wait_until"] == "domcontentloaded"

    def test_playwright_fallback_double_blocked_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._patch_blocked_http_and_fake_playwright(
            monkeypatch,
            pw_status=403,
            pw_html='<div class="cf-turnstile"></div>',
        )

        with pytest.raises(api.KleinanzeigenBlockedError) as exc_info:
            api.search_listings("fahrrad", use_playwright_fallback=True)
        assert exc_info.value.status_code == 403

    def test_playwright_unavailable_raises_blocked_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import builtins

        class BlockedSession:
            def __enter__(self) -> BlockedSession:
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def get(self, url: str, **kwargs: Any) -> Any:
                return SimpleNamespace(
                    status_code=403,
                    url=url,
                    text="<h1>IP-Bereich vorübergehend gesperrt.</h1>",
                    encoding="utf-8",
                    content=b"",
                    headers={},
                )

        real_import = builtins.__import__

        def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
            if name == "playwright.sync_api" or name == "playwright":
                raise ImportError("No module named 'playwright'")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(api.requests, "Session", BlockedSession)
        monkeypatch.setattr(builtins, "__import__", fake_import)

        with pytest.raises(api.KleinanzeigenBlockedError) as exc_info:
            api.search_listings("fahrrad", use_playwright_fallback=True)
        assert "unavailable" in exc_info.value.reason.lower()

    def test_user_agent_fallback_when_fake_useragent_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import builtins

        real_import = builtins.__import__

        def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
            if name == "fake_useragent":
                raise RuntimeError("offline cache missing")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        ua = api._get_user_agent()
        assert ua == api._DEFAULT_USER_AGENT

    def test_user_agent_rejects_mobile_and_handles_legacy_signature(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        recorded_kwargs: list[dict[str, Any]] = []
        mobile_ua = (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 18_3_2 like Mac OS X) "
            "AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1"
        )
        desktop_ua = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/135.0.0.0 Safari/537.36"
        )

        class LegacyUserAgent:
            def __init__(self, **kwargs: Any) -> None:
                recorded_kwargs.append(kwargs)
                if kwargs:
                    raise TypeError("unexpected keyword argument")
                self._calls = 0

            @property
            def random(self) -> str:
                self._calls += 1
                return mobile_ua if self._calls == 1 else desktop_ua

        monkeypatch.setitem(sys.modules, "fake_useragent", SimpleNamespace(UserAgent=LegacyUserAgent))
        assert api._get_user_agent() == desktop_ua
        assert recorded_kwargs[0] == {"browsers": ["Chrome", "Edge"], "platforms": ["desktop"]}
        assert recorded_kwargs[1] == {}

        class AlwaysMobileUserAgent:
            def __init__(self, **kwargs: Any) -> None:
                pass

            @property
            def random(self) -> str:
                return mobile_ua

        monkeypatch.setitem(
            sys.modules, "fake_useragent", SimpleNamespace(UserAgent=AlwaysMobileUserAgent)
        )
        assert api._get_user_agent() == api._DEFAULT_USER_AGENT


class TestSearchCli:
    """Subprocess integration tests for skills/kleinanzeigen/scripts/search_cli.py."""

    def test_search_cli_valid_json_from_external_cwd(self, tmp_path: Path) -> None:
        html_file = tmp_path / "results.html"
        html_file.write_text(BEM_HTML, encoding="utf-8")

        proc = _run_cli(
            "skills/kleinanzeigen/scripts/search_cli.py",
            [
                "fahrrad",
                "--plz",
                "10115",
                "--radius",
                "10",
                "--min-price",
                "50",
                "--max-price",
                "500",
                "--limit",
                "5",
                "--html-file",
                str(html_file),
            ],
            cwd=tmp_path,
        )

        assert proc.returncode == 0
        assert proc.stderr == ""
        parsed = json.loads(proc.stdout)
        assert isinstance(parsed, list)
        assert len(parsed) == 2
        assert set(parsed[0].keys()) == EXPECTED_KEYS

    def test_search_cli_validation_error_writes_only_stderr(self, tmp_path: Path) -> None:
        proc = _run_cli(
            "skills/kleinanzeigen/scripts/search_cli.py",
            ["fahrrad", "--radius", "10"],
            cwd=tmp_path,
        )
        assert proc.returncode == 1
        assert proc.stdout == ""
        assert "Validation error:" in proc.stderr

    def test_search_cli_missing_html_file_and_empty_query(self, tmp_path: Path) -> None:
        missing = _run_cli(
            "skills/kleinanzeigen/scripts/search_cli.py",
            ["fahrrad", "--html-file", str(tmp_path / "does_not_exist.html")],
        )
        assert missing.returncode == 1
        assert missing.stdout == ""
        assert missing.stderr.strip() != ""

        empty_q = _run_cli("skills/kleinanzeigen/scripts/search_cli.py", ["   "])
        assert empty_q.returncode == 1
        assert empty_q.stdout == ""
        assert "Validation error:" in empty_q.stderr

    def test_search_cli_include_top_ads_flag(self, tmp_path: Path) -> None:
        html_file = tmp_path / "bem.html"
        html_file.write_text(BEM_HTML, encoding="utf-8")
        proc = _run_cli(
            "skills/kleinanzeigen/scripts/search_cli.py",
            ["fahrrad", "--include-top-ads", "--html-file", str(html_file)],
        )
        assert proc.returncode == 0
        assert [item["id"] for item in json.loads(proc.stdout)] == [
            "900000001",
            "2987654321",
            "2987654322",
        ]

    def test_search_cli_blocked_error_returns_1_without_stdout(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        def _raise_blocked(*args: Any, **kwargs: Any) -> list[dict[str, str | None]]:
            raise api.KleinanzeigenBlockedError(
                status_code=403,
                url="https://www.kleinanzeigen.de/s-suchanfrage.html?keywords=thinkpad",
                reason="HTTP 403: Akamai IP range block",
            )

        monkeypatch.setattr(search_cli, "search_listings", _raise_blocked)
        exit_code = search_cli.main(["thinkpad", "--no-browser"])
        captured = capsys.readouterr()
        assert exit_code == 1
        assert captured.out == ""
        assert "Blocked by Kleinanzeigen (status=403)" in captured.err


class TestMonitorCliAndSqlite:
    """Subprocess and SQLite verification tests for skills/kleinanzeigen/scripts/monitor.py."""

    def test_resolve_db_path_precedence(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.delenv("KLEINANZEIGEN_DB_PATH", raising=False)
        expected_default = Path.home() / ".hermes" / "skills" / "kleinanzeigen" / "data" / "seen_ads.db"
        assert monitor.resolve_db_path(None) == expected_default

        env_db = str(tmp_path / "env.db")
        monkeypatch.setenv("KLEINANZEIGEN_DB_PATH", env_db)
        assert monitor.resolve_db_path(None) == Path(env_db)

        cli_db = str(tmp_path / "cli.db")
        assert monitor.resolve_db_path(cli_db) == Path(cli_db)

        with pytest.raises(api.ValidationError):
            monitor.resolve_db_path("   ")

    def test_monitor_sqlite_dedup_dry_run_and_schema(self, tmp_path: Path) -> None:
        db_path = tmp_path / "nested" / "seen_ads.db"
        html_v1 = tmp_path / "v1.html"
        html_v2 = tmp_path / "v2.html"

        ad1 = ("101", "Gravel Bike", "420 €", "10115 Berlin", "First bike description")
        ad2 = ("102", "City Bike", "180 €", "10117 Berlin", "Second bike description")
        ad3 = ("103", "Mountain Bike", "350 €", "10119 Berlin", "Third bike description")

        html_v1.write_text(_make_html_with_ads([ad1, ad2]), encoding="utf-8")
        html_v2.write_text(_make_html_with_ads([ad1, ad2, ad3]), encoding="utf-8")

        # Dry-run first: emits both ads, must NOT persist rows to SQLite
        dry_proc = _run_cli(
            "skills/kleinanzeigen/scripts/monitor.py",
            ["fahrrad", "--plz", "10115", "--radius", "10", "--db", str(db_path), "--html-file", str(html_v1), "--dry-run"],
        )
        assert dry_proc.returncode == 0
        assert [item["id"] for item in json.loads(dry_proc.stdout)] == ["101", "102"]

        with sqlite3.connect(str(db_path)) as conn:
            cols = conn.execute("PRAGMA table_info(seen_ads)").fetchall()
            assert [(c[1], c[2], c[5]) for c in cols] == [
                ("ad_id", "TEXT", 1),
                ("query_hash", "TEXT", 0),
                ("seen_at", "TIMESTAMP", 0),
            ]
            assert conn.execute("SELECT COUNT(*) FROM seen_ads").fetchone()[0] == 0

        # First real run: returns all 2 new ads and persists them
        run1 = _run_cli(
            "skills/kleinanzeigen/scripts/monitor.py",
            ["fahrrad", "--plz", "10115", "--radius", "10", "--db", str(db_path), "--html-file", str(html_v1)],
        )
        assert run1.returncode == 0
        assert [item["id"] for item in json.loads(run1.stdout)] == ["101", "102"]

        # Second run with identical ads: returns []
        run2 = _run_cli(
            "skills/kleinanzeigen/scripts/monitor.py",
            ["fahrrad", "--plz", "10115", "--radius", "10", "--db", str(db_path), "--html-file", str(html_v1)],
        )
        assert run2.returncode == 0
        assert json.loads(run2.stdout) == []

        # Third run with 1 new ad added: returns ONLY ad 103
        run3 = _run_cli(
            "skills/kleinanzeigen/scripts/monitor.py",
            ["fahrrad", "--plz", "10115", "--radius", "10", "--db", str(db_path), "--html-file", str(html_v2)],
        )
        assert run3.returncode == 0
        assert [item["id"] for item in json.loads(run3.stdout)] == ["103"]

        expected_hash = monitor.compute_query_hash("fahrrad", "10115", 10, None, None)
        with sqlite3.connect(str(db_path)) as conn:
            rows = conn.execute(
                "SELECT ad_id, query_hash, seen_at FROM seen_ads ORDER BY ad_id"
            ).fetchall()
        assert [r[0] for r in rows] == ["101", "102", "103"]
        assert all(r[1] == expected_hash for r in rows)
        for _, _, seen_at in rows:
            datetime.fromisoformat(seen_at)

    def test_monitor_telegram_format_and_empty_silence(self, tmp_path: Path) -> None:
        db_path = tmp_path / "telegram.db"
        long_desc = "Sehr gut erhaltenes Fahrrad mit Scheibenbremsen und neuem Sattel " * 4
        html_file = tmp_path / "tg.html"
        html_file.write_text(
            _make_html_with_ads(
                [("201", "Gravel Bike [28]", "420 € VB", "10115 Berlin-Mitte", long_desc)]
            ),
            encoding="utf-8",
        )

        proc = _run_cli(
            "skills/kleinanzeigen/scripts/monitor.py",
            [
                "fahrrad",
                "--plz",
                "10115",
                "--radius",
                "10",
                "--db",
                str(db_path),
                "--format",
                "telegram",
                "--html-file",
                str(html_file),
            ],
        )
        assert proc.returncode == 0
        assert proc.stderr == ""
        out = proc.stdout
        assert '🔍 **Kleinanzeigen: 1 объявлений по запросу "fahrrad"**' in out
        assert "📍 Локация: 10115 (+10 км)" in out
        assert (
            "1. **[Gravel Bike \\[28\\]](https://www.kleinanzeigen.de/s-anzeige/item/201-217-3352)** — **420 € VB**"
            in out
        )
        assert "   📍 10115 Berlin-Mitte" in out
        assert "   📝 " in out
        desc_line = [line for line in out.splitlines() if line.strip().startswith("📝")][0]
        assert desc_line.endswith("...")
        assert len(desc_line.split("📝 ", 1)[1]) <= monitor.MAX_DESCRIPTION_LENGTH

        # Second run with 0 new ads in telegram format -> empty stdout, "No new listings." on stderr
        proc_empty = _run_cli(
            "skills/kleinanzeigen/scripts/monitor.py",
            [
                "fahrrad",
                "--plz",
                "10115",
                "--radius",
                "10",
                "--db",
                str(db_path),
                "--format",
                "telegram",
                "--html-file",
                str(html_file),
            ],
        )
        assert proc_empty.returncode == 0
        assert proc_empty.stdout == ""
        assert "No new listings." in proc_empty.stderr

    def test_telegram_location_header_variants(self) -> None:
        sample = [
            {
                "id": "1",
                "title": "Test",
                "price": "10 €",
                "location": "",
                "url": "https://www.kleinanzeigen.de/s-anzeige/test/1",
                "image_url": None,
                "description": "",
            }
        ]
        assert "📍 Локация: Вся Германия" in monitor.format_telegram_message(sample, "test")
        assert "📍 Локация: 10115\n" in monitor.format_telegram_message(sample, "test", postal_code="10115")
        assert "📍 Локация: 10115 (+20 км)" in monitor.format_telegram_message(
            sample, "test", postal_code="10115", radius=20
        )

    def test_compute_query_hash_and_monitor_validation_error(self, tmp_path: Path) -> None:
        h1 = monitor.compute_query_hash("  Fahrrad ", " 10115 ", 10, 50, 500)
        h2 = monitor.compute_query_hash("fahrrad", "10115", 10, 50, 500)
        h3 = monitor.compute_query_hash("fahrrad", "10115", 20, 50, 500)
        assert h1 == h2
        assert h1 != h3
        assert len(h1) == 64

        proc = _run_cli(
            "skills/kleinanzeigen/scripts/monitor.py",
            ["fahrrad", "--plz", "abc", "--db", str(tmp_path / "x.db")],
        )
        assert proc.returncode == 1
        assert proc.stdout == ""
        assert "Validation error:" in proc.stderr


def _astro_encode(value: Any) -> Any:
    """Encode a Python structure using Astro island prop serialization."""
    if isinstance(value, dict):
        return [0, {k: _astro_encode(v) for k, v in value.items()}]
    if isinstance(value, list):
        return [1, [_astro_encode(v) for v in value]]
    return [0, value]


ASTRO_HTML = """
<!doctype html>
<html lang="de">
<head><meta charset="utf-8"></head>
<body>
  <div id="srp-breadcrumb-summary">1 - 3 von 3 Ergebnissen</div>
  <ul id="srchrslt-adtable">
    <li>
      <article class="flex justify-between p-medium" data-adid="3501957949" data-href="/s-anzeige/yamaha-r6-rj03/3501957949-305-5905">
        <div class="relative basis-[200px]">
          <script type="application/ld+json">{"title":"Yamaha R6 RJ03 Fallback","contentUrl":"https://img.kleinanzeigen.de/api/v1/prod-ads/images/57/570972ca?rule=$_59.AUTO"}</script>
          <a href="/s-anzeige/yamaha-r6-rj03/3501957949-305-5905">
            <div data-image-container>
              <img src="https://img.kleinanzeigen.de/api/v1/prod-ads/images/57/570972ca?rule=$_2.AUTO"
                   srcset="https://img.kleinanzeigen.de/api/v1/prod-ads/images/57/570972ca?rule=$_35.AUTO"
                   alt="Yamaha R6">
              <div>6</div>
            </div>
          </a>
        </div>
        <div class="flex grow flex-col">
          <div class="flex justify-between">
            <div><svg></svg><span>84489 Burghausen</span></div>
          </div>
          <div class="flex flex-col">
            <h3 class="mb-xsmall"><a href="/s-anzeige/yamaha-r6-rj03/3501957949-305-5905">Yamaha R6 RJ03 (48 PS Gedrosselt)</a></h3>
            <p class="mb-xsmall text-bodyRegular">## Yamaha YZF-R6 RJ03 – 48 PS gedrosselt</p>
            <div class="flex">
              <p class="m-xsmall text-title3 line-through">2.500 €</p>
              <p class="my-xsmall text-title3 font-strong text-secondary">2.300 € VB</p>
            </div>
          </div>
          <div>
            <p class="flex"><span data-dhl-promotion class="mr-xsmall">EZ 01/2001</span></p>
          </div>
        </div>
      </article>
    </li>
    <li>
      <article class="flex justify-between p-medium" data-adid="3525141008" data-href="/s-anzeige/bremspumpe-nissin/3525141008-306-7940">
        <div class="relative basis-[200px]">
          <a href="/s-anzeige/bremspumpe-nissin/3525141008-306-7940">
            <div data-image-container>
              <img src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw=="
                   srcset="https://img.kleinanzeigen.de/p/nissin_small.jpg 300w, https://img.kleinanzeigen.de/p/nissin_large.jpg 1200w"
                   alt="Bremspumpe">
            </div>
          </a>
        </div>
        <div class="flex grow flex-col">
          <div class="flex justify-between">
            <div><svg></svg><span>14979 Großbeeren</span></div>
            <div><svg></svg><span>Heute, 20:06</span></div>
          </div>
          <div class="flex flex-col">
            <h3><a href="/s-anzeige/bremspumpe-nissin/3525141008-306-7940">Bremspumpe Nissin Radial</a></h3>
            <p class="mb-xsmall">Absolut dicht, ohne Unfall.</p>
            <div class="flex"><p class="font-strong">120 €</p></div>
          </div>
          <div>
            <p class="flex"><span data-dhl-promotion>Versand möglich</span></p>
          </div>
        </div>
      </article>
    </li>
    <li>
      <article class="flex justify-between p-medium" data-adid="3523159642" data-href="/s-anzeige/yamaha-r6-rj11/3523159642-305-20854">
        <div class="flex grow flex-col">
          <div class="flex justify-between">
            <div><svg></svg><span>55469 Simmern</span></div>
            <div><svg></svg><span>25.09.2026</span></div>
          </div>
          <div class="flex flex-col">
            <h3><a href="/s-anzeige/yamaha-r6-rj11/3523159642-305-20854">Yamaha R6 RJ11</a></h3>
            <div class="flex"><p class="font-strong">6.999 €</p></div>
          </div>
          <div>
            <p class="flex"><span data-dhl-promotion>EZ 01/2006</span></p>
          </div>
        </div>
      </article>
    </li>
  </ul>
</body>
</html>
"""


class TestAstroHtmlParsing:
    """Tests for Kleinanzeigen Astro SSR HTML, astro-island, ld+json, and breadcrumb parsing."""

    def test_parse_astro_cards_price_description_badges_and_srcset(self) -> None:
        results = api.parse_listings_html(ASTRO_HTML, limit=10)
        assert [item["id"] for item in results] == ["3501957949", "3525141008", "3523159642"]

        first, second, third = results
        assert set(first.keys()) == EXPECTED_KEYS
        assert first["title"] == "Yamaha R6 RJ03 (48 PS Gedrosselt)"
        assert first["price"] == "2.300 € VB"
        assert first["location"] == "84489 Burghausen"
        assert first["description"] == "## Yamaha YZF-R6 RJ03 – 48 PS gedrosselt"
        assert first["image_url"] == (
            "https://img.kleinanzeigen.de/api/v1/prod-ads/images/57/570972ca?rule=$_35.AUTO"
        )
        assert "EZ 01/2001" not in (first["description"] or "")

        assert second["price"] == "120 €"
        assert second["location"] == "14979 Großbeeren"
        assert second["description"] == "Absolut dicht, ohne Unfall."
        assert second["image_url"] == "https://img.kleinanzeigen.de/p/nissin_large.jpg"

        # No h3 + p description: badge-only flex paragraph must not leak into description
        assert third["price"] == "6.999 €"
        assert third["description"] == ""

    def test_line_through_only_price_is_ignored(self) -> None:
        html = """
        <article data-adid="7001" data-href="/s-anzeige/x/7001">
          <h3><a href="/s-anzeige/x/7001">Reduced Item</a></h3>
          <div class="flex">
            <p class="font-strong line-through">500 €</p>
          </div>
        </article>
        """
        results = api.parse_listings_html(html)
        assert len(results) == 1
        assert results[0]["price"] == ""

    def test_astro_island_top_ad_filtering_and_invalid_props_resilience(self) -> None:
        island_payload = {
            "resultAds": _astro_encode(
                [
                    {
                        "sponsoredAdPresent": False,
                        "organicAdPreview": {
                            "id": 3436158201,
                            "topAd": True,
                            "sortingDate": "13.09.2026",
                            "appliedFeatures": [],
                        },
                    },
                    {
                        "sponsoredAdPresent": False,
                        "organicAdPreview": {
                            "id": 3532985509,
                            "topAd": False,
                            "sortingDate": "06.10.2026",
                            "appliedFeatures": ["TOP_AD"],
                        },
                    },
                    {"sponsoredAdPresent": True, "sponsoredAd": {"positionName": "srps-3"}},
                    {
                        "sponsoredAdPresent": False,
                        "organicAdPreview": {
                            "id": 3535050266,
                            "topAd": False,
                            "sortingDate": "Heute, 20:45",
                            "appliedFeatures": [],
                        },
                    },
                ]
            )
        }
        escaped_props = html_lib.escape(json.dumps(island_payload), quote=True)
        html = f"""
        <!doctype html><html><body>
          <ul>
            <li><article data-adid="3436158201" data-href="/s-anzeige/a/3436158201">
              <div><span>50259 Pulheim</span></div>
              <h3><a>Top Ad Flag</a></h3><p>Teaser 1</p>
            </article></li>
            <li><article data-adid="3532985509" data-href="/s-anzeige/b/3532985509">
              <div><span>77654 Offenburg</span></div>
              <h3><a>Applied Feature Top Ad</a></h3><p>Teaser 2</p>
            </article></li>
            <li><article data-adid="3535050266" data-href="/s-anzeige/c/3535050266">
              <div><span>28201 Buntentor</span><span>Heute, 20:45</span></div>
              <h3><a>Regular Bike</a></h3><p>Teaser 3</p>
            </article></li>
          </ul>
          <astro-island props="{escaped_props}"></astro-island>
          <astro-island props="not-valid-json"></astro-island>
        </body></html>
        """

        default_ads = api.parse_listings_html(html, limit=10)
        assert [ad["id"] for ad in default_ads] == ["3535050266"]

        with_top = api.parse_listings_html(html, limit=10, include_top_ads=True)
        assert [ad["id"] for ad in with_top] == ["3436158201", "3532985509", "3535050266"]

    def test_ld_json_title_and_image_fallback(self) -> None:
        html = """
        <article data-adid="8001" data-href="/s-anzeige/fallback-item/8001">
          <script type="application/ld+json">
            {"title": "JSON-LD ThinkPad X280", "contentUrl": "https://img.kleinanzeigen.de/ld_59.jpg?rule=$_59.AUTO"}
          </script>
          <a href="/s-anzeige/fallback-item/8001">
            <div data-image-container>
              <img src="https://img.kleinanzeigen.de/tiny.jpg?rule=$_2.AUTO" alt="thumb">
              <span>6</span>
            </div>
          </a>
          <div class="flex"><span>10115 Berlin</span></div>
        </article>
        <article data-adid="8002" data-href="/s-anzeige/no-img/8002">
          <script type="application/ld+json">
            [{"name": "JSON-LD Array Item", "image": "/static/fallback.png"}]
          </script>
        </article>
        """
        results = api.parse_listings_html(html, limit=10)
        assert len(results) == 2
        assert results[0]["title"] == "JSON-LD ThinkPad X280"
        assert results[0]["image_url"] == "https://img.kleinanzeigen.de/ld_59.jpg?rule=$_59.AUTO"
        assert results[1]["title"] == "JSON-LD Array Item"
        assert results[1]["image_url"] == "https://www.kleinanzeigen.de/static/fallback.png"

    def test_pre_h3_location_distance_siblings_and_prefix_cleaning(self) -> None:
        html = """
        <!doctype html><html><body><ul>
          <li><article data-adid="9001" data-href="/s-anzeige/a/9001">
            <div>
              <div><span>14979\xa0Großbeeren</span><span>(12 km)</span></div>
              <div><span>Heute, 10:00</span></div>
            </div>
            <h3><a>Bike 1</a></h3>
          </article></li>
          <li><article data-adid="9002" data-href="/s-anzeige/b/9002">
            <div>
              <div><span>Standort: 14979 Großbeeren</span></div>
              <div>(12,5 km)</div>
            </div>
            <h3><a>Bike 2</a></h3>
          </article></li>
          <li><article data-adid="9003" data-href="/s-anzeige/c/9003">
            <div><span>94496 Ortenburg</span></div>
            <h3><a>Bike 3</a></h3>
          </article></li>
          <li><article data-adid="9004" data-href="/s-anzeige/d/9004">
            <div><span>Ort: 80331 München</span></div>
            <h3><a>Bike 4</a></h3>
          </article></li>
        </ul></body></html>
        """
        ads = {ad["id"]: ad for ad in api.parse_listings_html(html, limit=10)}
        assert ads["9001"]["location"] == "14979 Großbeeren (12 km)"
        assert ads["9002"]["location"] == "14979 Großbeeren (12,5 km)"
        assert ads["9003"]["location"] == "94496 Ortenburg"
        assert ads["9004"]["location"] == "80331 München"

    @pytest.mark.parametrize(
        "raw_input,expected",
        [
            ('<div id="srp-breadcrumb-summary">1 - 25 von 1.234 Ergebnissen</div>', (1234, 50)),
            ('<span class="breadcrump-summary">1 - 12 von 12</span>', (12, 1)),
            ('<div id="srp-breadcrumb-summary">26 - 50 von 1.234</div>', (1234, None)),
            ("1 - 25 von 1.234 Ergebnissen", (1234, 50)),
            ("<html><body>Keine Treffer</body></html>", (None, None)),
            ("   ", (None, None)),
        ],
    )
    def test_parse_breadcrumb(
        self, raw_input: str, expected: tuple[int | None, int | None]
    ) -> None:
        assert api.parse_breadcrumb(raw_input) == expected


def _install_fake_playwright(
    monkeypatch: pytest.MonkeyPatch,
    page_factory: Any = None,
) -> tuple[MagicMock, MagicMock]:
    """Install a mocked playwright.sync_api module and return (chromium, context)."""
    context = MagicMock()
    if page_factory is not None:
        context.new_page.side_effect = page_factory
    browser = MagicMock()
    browser.new_context.return_value = context
    chromium = MagicMock()
    chromium.launch.return_value = browser
    chromium.connect_over_cdp.return_value = browser
    cm = MagicMock()
    cm.__enter__.return_value = SimpleNamespace(chromium=chromium)
    fake_sync_api = SimpleNamespace(sync_playwright=lambda: cm)
    monkeypatch.setitem(sys.modules, "playwright", SimpleNamespace(sync_api=fake_sync_api))
    monkeypatch.setitem(sys.modules, "playwright.sync_api", fake_sync_api)
    return chromium, context


class TestPlaywrightEngineAndPagination:
    """Mocked unit tests for Playwright route blocking, CDP, retries, and pagination."""

    @pytest.mark.parametrize(
        "resource_type,url,should_abort",
        [
            ("image", "https://img.kleinanzeigen.de/pic.jpg", True),
            ("media", "https://cdn.example.com/video.mp4", True),
            ("font", "https://www.kleinanzeigen.de/font.woff2", True),
            ("script", "https://www.kleinanzeigen.de/liberty/ads.js", True),
            ("xhr", "https://www.kleinanzeigen.de/gdpr/consent", True),
            ("script", "https://cdn.example.com/promotion-frontend/app.js", True),
            ("fetch", "https://cdn.example.com/kameleoon/engine.js", True),
            ("xhr", "https://metrics.kleinanzeigen.de/sgtm-legacy/collect", True),
            ("stylesheet", "https://www.kleinanzeigen.de/assets/main.css", False),
            ("document", "https://www.kleinanzeigen.de/s-seite:1?keywords=bike", False),
            ("script", "https://www.kleinanzeigen.de/assets/app.js", False),
        ],
    )
    def test_block_heavy_resources_rules(
        self,
        monkeypatch: pytest.MonkeyPatch,
        resource_type: str,
        url: str,
        should_abort: bool,
    ) -> None:
        monkeypatch.delenv("BROWSER_DISABLE_RESOURCE_BLOCKING", raising=False)
        route = MagicMock()
        route.request = SimpleNamespace(resource_type=resource_type, url=url)

        api._block_heavy_resources(route)
        if should_abort:
            route.abort.assert_called_once()
            route.continue_.assert_not_called()
        else:
            route.continue_.assert_called_once()
            route.abort.assert_not_called()

    def test_disable_resource_blocking_env_var_respected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("BROWSER_DISABLE_RESOURCE_BLOCKING", "1")
        route = MagicMock()
        route.request = SimpleNamespace(
            resource_type="image",
            url="https://www.kleinanzeigen.de/liberty/banner.png",
        )
        api._block_heavy_resources(route)
        route.continue_.assert_called_once()
        route.abort.assert_not_called()

        _, context = _install_fake_playwright(monkeypatch)

        with api._PlaywrightSession(headers={}, timeout=20.0):
            pass
        context.route.assert_not_called()

    def test_browser_cdp_url_connects_over_cdp(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BROWSER_CDP_URL", "http://127.0.0.1:9222")
        page = MagicMock()
        page.url = "https://www.kleinanzeigen.de/s-seite:1?keywords=fahrrad"
        page.goto.return_value = SimpleNamespace(status=200)
        page.content.return_value = BEM_HTML

        chromium, context = _install_fake_playwright(monkeypatch, page_factory=lambda: page)

        results = api.search_listings("fahrrad", fetch_mode="browser", limit=2)
        assert len(results) == 2
        chromium.connect_over_cdp.assert_called_once_with("http://127.0.0.1:9222")
        chromium.launch.assert_not_called()
        context.clear_cookies.assert_called_once()

    def test_http_transient_retry_backoff_and_no_retry_on_block(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sleep_calls: list[float] = []
        monkeypatch.setattr(api.time, "sleep", lambda sec: sleep_calls.append(sec))

        attempts = 0

        class FlakySession:
            def __enter__(self) -> FlakySession:
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def get(self, url: str, **kwargs: Any) -> Any:
                nonlocal attempts
                attempts += 1
                if attempts < 3:
                    raise requests.Timeout("read timed out")
                return SimpleNamespace(
                    status_code=200,
                    url=url,
                    text=BEM_HTML,
                    encoding="utf-8",
                    content=BEM_HTML.encode("utf-8"),
                    headers={"Content-Type": "text/html; charset=utf-8"},
                )

        monkeypatch.setattr(api.requests, "Session", FlakySession)
        results = api.search_listings("fahrrad", fetch_mode="http", limit=2)
        assert len(results) == 2
        assert attempts == 3
        assert len(sleep_calls) == 2
        assert all(0 < delay <= 5.0 for delay in sleep_calls)

        # HTTP 403 block must NOT be retried
        sleep_calls.clear()
        block_attempts = 0

        class BlockedSession:
            def __enter__(self) -> BlockedSession:
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def get(self, url: str, **kwargs: Any) -> Any:
                nonlocal block_attempts
                block_attempts += 1
                return SimpleNamespace(
                    status_code=403,
                    url=url,
                    text="<h1>IP-Bereich vorübergehend gesperrt.</h1>",
                    encoding="utf-8",
                    content=b"",
                    headers={},
                )

        monkeypatch.setattr(api.requests, "Session", BlockedSession)
        with pytest.raises(api.KleinanzeigenBlockedError):
            api.search_listings("fahrrad", fetch_mode="http")
        assert block_attempts == 1
        assert sleep_calls == []

    def test_playwright_transient_retry_and_no_retry_on_captcha(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sleep_calls: list[float] = []
        monkeypatch.setattr(api.time, "sleep", lambda sec: sleep_calls.append(sec))

        goto_attempts = 0

        class FlakyPage:
            url = "https://www.kleinanzeigen.de/s-seite:1?keywords=fahrrad"

            def goto(self, url: str, **kwargs: Any) -> Any:
                nonlocal goto_attempts
                goto_attempts += 1
                if goto_attempts < 3:
                    raise TimeoutError("net::ERR_TIMED_OUT")
                return SimpleNamespace(status=200)

            def content(self) -> str:
                return BEM_HTML

            def close(self) -> None:
                return None

        _, context = _install_fake_playwright(monkeypatch, page_factory=lambda: FlakyPage())

        results = api.search_listings("fahrrad", fetch_mode="browser", limit=2)
        assert len(results) == 2
        assert goto_attempts == 3
        assert len(sleep_calls) == 2
        assert context.clear_cookies.call_count == 3

        # CAPTCHA / 403 block in Playwright must NOT be retried
        sleep_calls.clear()
        captcha_attempts = 0
        context.clear_cookies.reset_mock()

        class CaptchaPage:
            url = "https://www.kleinanzeigen.de/s-seite:1?keywords=fahrrad"

            def goto(self, url: str, **kwargs: Any) -> Any:
                nonlocal captcha_attempts
                captcha_attempts += 1
                return SimpleNamespace(status=200)

            def content(self) -> str:
                return '<html><div class="cf-turnstile"></div></html>'

            def close(self) -> None:
                return None

        context.new_page.side_effect = lambda: CaptchaPage()
        with pytest.raises(api.KleinanzeigenBlockedError):
            api.search_listings("fahrrad", fetch_mode="browser", limit=2)
        assert captcha_attempts == 1
        assert sleep_calls == []
        assert context.clear_cookies.call_count == 1

    def test_sequential_multipage_pagination_with_playwright_and_auto_fallback(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sleep_calls: list[float] = []
        monkeypatch.setattr(api.time, "sleep", lambda sec: sleep_calls.append(sec))

        page1_html = (
            '<div id="srp-breadcrumb-summary">1 - 2 von 5</div>'
            + _make_html_with_ads(
                [
                    ("101", "Ad 1", "10 €", "10115 Berlin", "Desc 1"),
                    ("102", "Ad 2", "20 €", "10115 Berlin", "Desc 2"),
                ]
            )
        )
        page2_html = _make_html_with_ads(
            [
                ("102", "Ad 2 Dup", "20 €", "10115 Berlin", "Dup"),
                ("103", "Ad 3", "30 €", "10115 Berlin", "Desc 3"),
            ]
        )
        page3_html = _make_html_with_ads(
            [
                ("104", "Ad 4", "40 €", "10115 Berlin", "Desc 4"),
                ("105", "Ad 5", "50 €", "10115 Berlin", "Desc 5"),
            ]
        )
        pages_by_num = {"s-seite:1": page1_html, "s-seite:2": page2_html, "s-seite:3": page3_html}

        visited_urls: list[str] = []

        class MultiPageFakePage:
            def __init__(self) -> None:
                self.url = ""
                self._html = ""

            def goto(self, url: str, **kwargs: Any) -> Any:
                visited_urls.append(url)
                self.url = url
                for key, payload in pages_by_num.items():
                    if key in url:
                        self._html = payload
                        return SimpleNamespace(status=200)
                return SimpleNamespace(status=404)

            def content(self) -> str:
                return self._html

            def close(self) -> None:
                return None

        _, context = _install_fake_playwright(
            monkeypatch, page_factory=lambda: MultiPageFakePage()
        )

        results = api.search_listings("fahrrad", fetch_mode="browser", limit=4)
        assert [item["id"] for item in results] == ["101", "102", "103", "104"]
        assert len(visited_urls) == 3
        assert "s-seite:1" in visited_urls[0]
        assert "s-seite:2" in visited_urls[1]
        assert "s-seite:3" in visited_urls[2]
        assert sleep_calls == [2.0, 2.0]
        assert context.clear_cookies.call_count == 3

        # Auto mode: page 1 succeeds over HTTP, page 2 hits 403 -> Playwright fallback finishes pagination
        visited_urls.clear()
        sleep_calls.clear()
        context.clear_cookies.reset_mock()

        class MidFallbackSession:
            def __enter__(self) -> MidFallbackSession:
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def get(self, url: str, **kwargs: Any) -> Any:
                if "s-seite:1" in url:
                    return SimpleNamespace(
                        status_code=200,
                        url=url,
                        text=page1_html,
                        encoding="utf-8",
                        content=page1_html.encode("utf-8"),
                        headers={"Content-Type": "text/html; charset=utf-8"},
                    )
                return SimpleNamespace(
                    status_code=403,
                    url=url,
                    text="<h1>IP-Bereich vorübergehend gesperrt.</h1>",
                    encoding="utf-8",
                    content=b"",
                    headers={},
                )

        monkeypatch.setattr(api.requests, "Session", MidFallbackSession)
        auto_results = api.search_listings("fahrrad", fetch_mode="auto", limit=4)
        assert [item["id"] for item in auto_results] == ["101", "102", "103", "104"]
        assert len(visited_urls) == 2
        assert "s-seite:2" in visited_urls[0]
        assert "s-seite:3" in visited_urls[1]
        assert context.clear_cookies.call_count == 2


class TestFetchModeAndCliFlags:
    """Tests for fetch_mode validation and --browser / --no-browser CLI flags."""

    def test_fetch_mode_validation_errors(self) -> None:
        with pytest.raises(api.ValidationError):
            api.search_listings("fahrrad", fetch_mode="fast")  # type: ignore[arg-type]
        with pytest.raises(api.ValidationError):
            api.search_listings("fahrrad", fetch_mode="browser", use_playwright_fallback=False)
        with pytest.raises(api.ValidationError):
            api.search_listings("fahrrad", use_playwright_fallback="yes")  # type: ignore[arg-type]
        with pytest.raises(api.ValidationError):
            api.search_listings("fahrrad", timeout=0)

    def test_browser_mode_skips_http_and_http_mode_skips_playwright(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _fail_session() -> Any:
            raise AssertionError("HTTP session must not be opened in browser mode")

        monkeypatch.setattr(api.requests, "Session", _fail_session)
        page = MagicMock()
        page.url = "https://www.kleinanzeigen.de/s-seite:1?keywords=fahrrad"
        page.goto.return_value = SimpleNamespace(status=200)
        page.content.return_value = BEM_HTML
        _install_fake_playwright(monkeypatch, page_factory=lambda: page)

        results = api.search_listings("fahrrad", fetch_mode="browser", limit=2)
        assert len(results) == 2

        class BlockedSession:
            def __enter__(self) -> BlockedSession:
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def get(self, url: str, **kwargs: Any) -> Any:
                return SimpleNamespace(
                    status_code=403,
                    url=url,
                    text="<h1>IP-Bereich vorübergehend gesperrt.</h1>",
                    encoding="utf-8",
                    content=b"",
                    headers={},
                )

        def _fail_pw(*args: Any, **kwargs: Any) -> Any:
            raise AssertionError("Playwright must not be invoked in http mode")

        monkeypatch.setattr(api.requests, "Session", BlockedSession)
        monkeypatch.setattr(api, "_PlaywrightSession", _fail_pw)
        with pytest.raises(api.KleinanzeigenBlockedError):
            api.search_listings("fahrrad", fetch_mode="http")

    def test_cli_mutual_exclusion_and_fetch_mode_forwarding(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        for mod in (search_cli, monitor):
            parser = mod.build_parser()
            with pytest.raises(SystemExit) as exc_info:
                parser.parse_args(["fahrrad", "--browser", "--no-browser"])
            assert exc_info.value.code == 2

        with pytest.raises(api.ValidationError):
            search_cli.resolve_fetch_options(SimpleNamespace(browser=True, no_browser=True))

        captured: list[tuple[str, bool]] = []

        def fake_search(*args: Any, **kwargs: Any) -> list[dict[str, str | None]]:
            captured.append((kwargs["fetch_mode"], kwargs["use_playwright_fallback"]))
            return []

        monkeypatch.setattr(search_cli, "search_listings", fake_search)
        monkeypatch.setattr(monitor, "search_listings", fake_search)

        db_path = str(tmp_path / "m.db")
        assert search_cli.main(["fahrrad"]) == 0
        assert search_cli.main(["fahrrad", "--browser"]) == 0
        assert search_cli.main(["fahrrad", "--no-browser"]) == 0
        assert monitor.main(["fahrrad", "--db", db_path]) == 0
        assert monitor.main(["fahrrad", "--browser", "--db", db_path]) == 0
        assert monitor.main(["fahrrad", "--no-browser", "--db", db_path]) == 0

        assert captured == [
            ("auto", True),
            ("browser", True),
            ("http", False),
            ("auto", True),
            ("browser", True),
            ("http", False),
        ]

    def test_monitor_query_hash_ignores_fetch_mode(self, tmp_path: Path) -> None:
        db_path = tmp_path / "shared_hash.db"
        html_file = tmp_path / "ads.html"
        html_file.write_text(
            _make_html_with_ads([("501", "ThinkPad T14", "350 €", "10115 Berlin", "Clean")]),
            encoding="utf-8",
        )

        run_browser = _run_cli(
            "skills/kleinanzeigen/scripts/monitor.py",
            ["ThinkPad", "--plz", "10115", "--radius", "20", "--browser", "--db", str(db_path), "--html-file", str(html_file)],
        )
        assert run_browser.returncode == 0
        assert [item["id"] for item in json.loads(run_browser.stdout)] == ["501"]

        run_no_browser = _run_cli(
            "skills/kleinanzeigen/scripts/monitor.py",
            ["ThinkPad", "--plz", "10115", "--radius", "20", "--no-browser", "--db", str(db_path), "--html-file", str(html_file)],
        )
        assert run_no_browser.returncode == 0
        assert json.loads(run_no_browser.stdout) == []


def _parse_simple_yaml_manifest(text: str) -> dict[str, Any]:
    """Parse plugin.yaml's flat keys, string lists, and optional_env maps without PyYAML."""
    data: dict[str, Any] = {}
    current_key: str | None = None
    current_item: dict[str, Any] | None = None

    def _parse_scalar(raw: str) -> Any:
        val = raw.strip()
        if (val.startswith('"') and val.endswith('"')) or (
            val.startswith("'") and val.endswith("'")
        ):
            return val[1:-1]
        if val == "true":
            return True
        if val == "false":
            return False
        if val.isdigit():
            return int(val)
        return val

    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        stripped = raw_line.strip()
        if indent == 0 and ":" in stripped:
            key, rest = stripped.split(":", 1)
            key = key.strip()
            rest = rest.strip()
            current_item = None
            if rest:
                data[key] = _parse_scalar(rest)
                current_key = None
            else:
                data[key] = []
                current_key = key
        elif current_key is not None and stripped.startswith("- "):
            item_text = stripped[2:].strip()
            if ":" in item_text and not (
                item_text.startswith('"') or item_text.startswith("'")
            ):
                k, v = item_text.split(":", 1)
                current_item = {k.strip(): _parse_scalar(v)}
                data[current_key].append(current_item)
            else:
                current_item = None
                data[current_key].append(_parse_scalar(item_text))
        elif current_key is not None and current_item is not None and ":" in stripped:
            k, v = stripped.split(":", 1)
            current_item[k.strip()] = _parse_scalar(v)

    return data


def _load_plugin_module(
    monkeypatch: pytest.MonkeyPatch, *, as_hermes_package: bool = True
) -> ModuleType:
    """Load root __init__.py as a Hermes plugin package or standalone module."""
    init_path = REPO_ROOT / "__init__.py"
    if as_hermes_package:
        pkg_name = "hermes_plugins_test_pkg"
        mod_name = f"{pkg_name}.kleinanzeigen"
        parent_pkg = ModuleType(pkg_name)
        parent_pkg.__path__ = []
        monkeypatch.setitem(sys.modules, pkg_name, parent_pkg)
        spec = importlib.util.spec_from_file_location(
            mod_name,
            init_path,
            submodule_search_locations=[str(REPO_ROOT)],
        )
    else:
        mod_name = "kleinanzeigen_plugin_standalone_test"
        spec = importlib.util.spec_from_file_location(mod_name, init_path)

    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, mod_name, module)
    spec.loader.exec_module(module)
    return module


class _FakePluginContext:
    """Minimal PluginContext stub recording register_tool and register_skill calls."""

    def __init__(self) -> None:
        self.tools: dict[str, dict[str, Any]] = {}
        self.skills: dict[str, dict[str, Any]] = {}

    def register_tool(
        self,
        name: str,
        toolset: str,
        schema: dict[str, Any],
        handler: Any,
        check_fn: Any = None,
        requires_env: list[str] | None = None,
        is_async: bool = False,
        description: str = "",
        emoji: str = "",
        override: bool = False,
    ) -> None:
        self.tools[name] = {
            "name": name,
            "toolset": toolset,
            "schema": schema,
            "handler": handler,
            "check_fn": check_fn,
            "requires_env": requires_env,
            "is_async": is_async,
            "description": description,
            "emoji": emoji,
            "override": override,
        }

    def register_skill(
        self,
        name: str,
        path: Path,
        description: str = "",
        frontmatter: dict[str, Any] | None = None,
    ) -> None:
        self.skills[name] = {
            "name": name,
            "path": Path(path),
            "description": description,
            "frontmatter": dict(frontmatter or {}),
        }


class TestPluginManifestAndPackaging:
    """Tests for plugin.yaml, pyproject.toml, and dual plugin+skill repo layout."""

    def test_plugin_yaml_schema_and_fields(self) -> None:
        manifest_path = REPO_ROOT / "plugin.yaml"
        assert manifest_path.is_file()
        manifest = _parse_simple_yaml_manifest(manifest_path.read_text(encoding="utf-8"))

        assert manifest["manifest_version"] == 2
        assert manifest["name"] == "kleinanzeigen"
        assert manifest["version"] == "1.0.0"
        assert manifest["kind"] == "standalone"
        assert manifest["license"] == "MIT"
        assert manifest["requires_hermes"] == ">=0.20.0"
        assert manifest["provides_tools"] == [
            "kleinanzeigen_search",
            "kleinanzeigen_monitor",
        ]
        assert manifest["pip_dependencies"] == [
            "requests>=2.31,<3",
            "beautifulsoup4>=4.12,<5",
            "fake-useragent>=1.4,<3",
        ]
        opt_env_names = [entry["name"] for entry in manifest["optional_env"]]
        assert opt_env_names == [
            "KLEINANZEIGEN_DB_PATH",
            "BROWSER_CDP_URL",
            "BROWSER_DISABLE_RESOURCE_BLOCKING",
            "BROWSER_EXECUTABLE_PATH",
        ]
        assert "entry_point" not in manifest
        assert "skills" not in manifest

    def test_pyproject_toml_metadata_and_optional_browser(self) -> None:
        pyproject_path = REPO_ROOT / "pyproject.toml"
        assert pyproject_path.is_file()
        data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

        assert data["build-system"]["build-backend"] == "setuptools.build_meta"
        project = data["project"]
        assert project["name"] == "hermes-kleinanzeigen"
        assert project["version"] == "1.0.0"
        assert project["requires-python"] == ">=3.11"
        assert project["license"] == "MIT"
        assert project["dependencies"] == [
            "requests>=2.31,<3",
            "beautifulsoup4>=4.12,<5",
            "fake-useragent>=1.4,<3",
        ]
        assert project["optional-dependencies"]["browser"] == ["playwright>=1.49,<2"]
        assert project["optional-dependencies"]["dev"] == ["pytest>=8.0"]
        assert data["tool"]["setuptools"]["packages"] == []
        assert data["tool"]["setuptools"]["py-modules"] == []

    def test_skill_layout_and_required_files(self) -> None:
        skill_dir = REPO_ROOT / "skills" / "kleinanzeigen"
        for rel in (
            "SKILL.md",
            "LICENSE",
            "requirements.txt",
            "scripts/__init__.py",
            "scripts/kleinanzeigen_api.py",
            "scripts/search_cli.py",
            "scripts/monitor.py",
        ):
            assert (skill_dir / rel).is_file(), f"Missing {rel}"

        for root_file in ("README.md", "LICENSE", ".gitignore", "__init__.py"):
            assert (REPO_ROOT / root_file).is_file(), f"Missing root {root_file}"

        assert not (REPO_ROOT / "scripts").exists()
        assert not (REPO_ROOT / "SKILL.md").exists()
        assert not (REPO_ROOT / "requirements.txt").exists()


class TestPluginRegistrationAndTools:
    """Tests for root __init__.py register(ctx), tool handlers, DB resolution, and errors."""

    @pytest.mark.parametrize("as_hermes_package", [True, False])
    def test_register_tools_and_skill_matches_manifest(
        self, monkeypatch: pytest.MonkeyPatch, as_hermes_package: bool
    ) -> None:
        plugin = _load_plugin_module(monkeypatch, as_hermes_package=as_hermes_package)
        ctx = _FakePluginContext()
        plugin.register(ctx)

        manifest = _parse_simple_yaml_manifest(
            (REPO_ROOT / "plugin.yaml").read_text(encoding="utf-8")
        )
        assert list(ctx.tools.keys()) == manifest["provides_tools"]

        search_entry = ctx.tools["kleinanzeigen_search"]
        assert search_entry["toolset"] == "kleinanzeigen"
        search_params = search_entry["schema"]["parameters"]
        assert search_params["required"] == ["query"]
        assert search_params["additionalProperties"] is False
        assert search_params["properties"]["radius"]["enum"] == list(api.ALLOWED_RADII)
        assert search_params["properties"]["fetch_mode"]["enum"] == ["auto", "http", "browser"]

        monitor_entry = ctx.tools["kleinanzeigen_monitor"]
        assert monitor_entry["toolset"] == "kleinanzeigen"
        mon_params = monitor_entry["schema"]["parameters"]
        assert mon_params["required"] == ["query"]
        assert mon_params["additionalProperties"] is False
        assert mon_params["properties"]["format"]["enum"] == ["json", "telegram"]
        assert "dry_run" in mon_params["properties"]
        assert "db_path" in mon_params["properties"]

        assert list(ctx.skills.keys()) == ["kleinanzeigen"]
        skill_entry = ctx.skills["kleinanzeigen"]
        assert skill_entry["path"] == (REPO_ROOT / "skills" / "kleinanzeigen" / "SKILL.md").resolve()
        assert skill_entry["path"].is_file()
        assert skill_entry["frontmatter"]["name"] == "kleinanzeigen"
        assert skill_entry["frontmatter"]["platforms"] == ["linux", "macos", "windows"]

    def test_kleinanzeigen_search_tool_success_and_fetch_mode(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        plugin = _load_plugin_module(monkeypatch, as_hermes_package=True)
        ctx = _FakePluginContext()
        plugin.register(ctx)
        handler = ctx.tools["kleinanzeigen_search"]["handler"]

        class OkSession:
            def __enter__(self) -> OkSession:
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def get(self, url: str, **kwargs: Any) -> Any:
                return SimpleNamespace(
                    status_code=200,
                    url=url,
                    text=BEM_HTML,
                    encoding="utf-8",
                    content=BEM_HTML.encode("utf-8"),
                    headers={"Content-Type": "text/html; charset=utf-8"},
                )

        monkeypatch.setattr(requests, "Session", OkSession)
        result = json.loads(
            handler(
                {
                    "query": "  fahrrad  ",
                    "postal_code": "10115",
                    "radius": 10,
                    "limit": 5,
                }
            )
        )
        assert result["ok"] is True
        assert result["query"] == "fahrrad"
        assert result["postal_code"] == "10115"
        assert result["radius"] == 10
        assert result["fetch_mode"] == "auto"
        assert result["count"] == 2
        assert [item["id"] for item in result["listings"]] == ["2987654321", "2987654322"]

        class BlockedSession:
            def __enter__(self) -> BlockedSession:
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def get(self, url: str, **kwargs: Any) -> Any:
                return SimpleNamespace(
                    status_code=403,
                    url=url,
                    text="<h1>IP-Bereich vorübergehend gesperrt.</h1>",
                    encoding="utf-8",
                    content=b"",
                    headers={},
                )

        monkeypatch.setattr(requests, "Session", BlockedSession)
        blocked = json.loads(handler({"query": "fahrrad", "fetch_mode": "http"}))
        assert blocked["ok"] is False
        assert blocked["error_type"] == "blocked"
        assert blocked["status_code"] == 403
        assert "IP-Bereich" in blocked["reason"]

    def test_kleinanzeigen_search_tool_error_payloads(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        plugin = _load_plugin_module(monkeypatch, as_hermes_package=True)
        ctx = _FakePluginContext()
        plugin.register(ctx)
        handler = ctx.tools["kleinanzeigen_search"]["handler"]

        empty_err = json.loads(handler({"query": "   "}))
        assert empty_err["ok"] is False
        assert empty_err["error_type"] == "validation_error"

        radius_err = json.loads(handler({"query": "fahrrad", "radius": 10}))
        assert radius_err == {
            "ok": False,
            "error_type": "validation_error",
            "error": "radius cannot be specified without postal_code.",
        }

        bool_err = json.loads(handler({"query": "fahrrad", "include_top_ads": "yes"}))
        assert bool_err["ok"] is False
        assert bool_err["error_type"] == "validation_error"

        plugin_api = plugin._load_api()
        for exc_cls, expected_type in [
            (plugin_api.KleinanzeigenError, "kleinanzeigen_error"),
            (sqlite3.OperationalError, "database_error"),
            (OSError, "io_error"),
            (RuntimeError, "unexpected_error"),
        ]:
            monkeypatch.setattr(
                plugin_api,
                "search_listings",
                lambda *a, _cls=exc_cls, **kw: (_ for _ in ()).throw(_cls("boom")),
            )
            err = json.loads(handler({"query": "fahrrad"}))
            assert err == {"ok": False, "error_type": expected_type, "error": "boom"}

    def test_kleinanzeigen_monitor_tool_dedup_dry_run_and_telegram(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        plugin = _load_plugin_module(monkeypatch, as_hermes_package=True)
        ctx = _FakePluginContext()
        plugin.register(ctx)
        handler = ctx.tools["kleinanzeigen_monitor"]["handler"]

        ad1 = ("101", "Gravel Bike [28]", "420 €", "10115 Berlin", "First bike")
        ad2 = ("102", "City Bike", "180 €", "10117 Berlin", "Second bike")
        ad3 = ("103", "Mountain Bike", "350 €", "10119 Berlin", "Third bike")
        current_html = _make_html_with_ads([ad1, ad2])

        class SwitchingSession:
            def __enter__(self) -> SwitchingSession:
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def get(self, url: str, **kwargs: Any) -> Any:
                return SimpleNamespace(
                    status_code=200,
                    url=url,
                    text=current_html,
                    encoding="utf-8",
                    content=current_html.encode("utf-8"),
                    headers={"Content-Type": "text/html; charset=utf-8"},
                )

        monkeypatch.setattr(requests, "Session", SwitchingSession)
        db_file = tmp_path / "plugin_seen.db"

        dry = json.loads(
            handler(
                {
                    "query": "fahrrad",
                    "postal_code": "10115",
                    "radius": 10,
                    "dry_run": True,
                    "db_path": str(db_file),
                }
            )
        )
        assert dry["ok"] is True
        assert dry["dry_run"] is True
        assert dry["total_fetched"] == 2
        assert dry["new_count"] == 2
        with sqlite3.connect(str(db_file)) as conn:
            assert conn.execute("SELECT COUNT(*) FROM seen_ads").fetchone()[0] == 0

        first_run = json.loads(
            handler(
                {
                    "query": "fahrrad",
                    "postal_code": "10115",
                    "radius": 10,
                    "db_path": str(db_file),
                }
            )
        )
        assert first_run["ok"] is True
        assert first_run["new_count"] == 2
        assert "message" not in first_run

        second_run = json.loads(
            handler(
                {
                    "query": "fahrrad",
                    "postal_code": "10115",
                    "radius": 10,
                    "format": "telegram",
                    "db_path": str(db_file),
                }
            )
        )
        assert second_run["ok"] is True
        assert second_run["new_count"] == 0
        assert second_run["listings"] == []
        assert second_run["message"] == ""

        current_html = _make_html_with_ads([ad1, ad2, ad3])
        third_run = json.loads(
            handler(
                {
                    "query": "fahrrad",
                    "postal_code": "10115",
                    "radius": 10,
                    "format": "telegram",
                    "db_path": str(db_file),
                }
            )
        )
        assert third_run["ok"] is True
        assert third_run["total_fetched"] == 3
        assert third_run["new_count"] == 1
        assert [item["id"] for item in third_run["listings"]] == ["103"]
        assert '🔍 **Kleinanzeigen: 1 объявлений по запросу "fahrrad"**' in third_run["message"]
        assert "📍 Локация: 10115 (+10 км)" in third_run["message"]
        assert "Mountain Bike" in third_run["message"]

        assert json.loads(handler({"query": "fahrrad", "format": "xml"}))["error_type"] == "validation_error"
        assert json.loads(handler({"query": "fahrrad", "dry_run": "no"}))["error_type"] == "validation_error"
        assert json.loads(handler({"query": "fahrrad", "db_path": "  "}))["error_type"] == "validation_error"

    def test_kleinanzeigen_monitor_db_path_precedence(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        plugin = _load_plugin_module(monkeypatch, as_hermes_package=True)
        plugin_api = plugin._load_api()

        # 1. Explicit db_path beats env var and plugin_data_dir
        monkeypatch.setenv("KLEINANZEIGEN_DB_PATH", str(tmp_path / "env.db"))
        explicit = plugin._resolve_plugin_db_path(str(tmp_path / "arg.db"), plugin_api.ValidationError)
        assert explicit == tmp_path / "arg.db"

        # 2. KLEINANZEIGEN_DB_PATH beats plugin_data_dir
        from_env = plugin._resolve_plugin_db_path(None, plugin_api.ValidationError)
        assert from_env == tmp_path / "env.db"
        monkeypatch.delenv("KLEINANZEIGEN_DB_PATH", raising=False)

        # 3. plugins.plugin_storage.plugin_data_dir when importable
        storage_dir = tmp_path / "plugin-storage"
        fake_plugins_pkg = ModuleType("plugins")
        fake_storage_mod = ModuleType("plugins.plugin_storage")
        fake_storage_mod.plugin_data_dir = lambda name: storage_dir / name  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "plugins", fake_plugins_pkg)
        monkeypatch.setitem(sys.modules, "plugins.plugin_storage", fake_storage_mod)
        assert plugin._resolve_plugin_db_path(None, plugin_api.ValidationError) == (
            storage_dir / "kleinanzeigen" / "seen_ads.db"
        )

        # 4. hermes_constants.get_hermes_home fallback when plugin_storage unavailable
        monkeypatch.setitem(sys.modules, "plugins", None)  # type: ignore[arg-type]
        monkeypatch.setitem(sys.modules, "plugins.plugin_storage", None)  # type: ignore[arg-type]
        hermes_const_dir = tmp_path / "hermes-const-home"
        fake_const_mod = ModuleType("hermes_constants")
        fake_const_mod.get_hermes_home = lambda: hermes_const_dir  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "hermes_constants", fake_const_mod)
        assert plugin._resolve_plugin_db_path(None, plugin_api.ValidationError) == (
            hermes_const_dir / "plugin-data" / "kleinanzeigen" / "seen_ads.db"
        )

        # 5. HERMES_HOME env fallback when neither plugin_storage nor hermes_constants exists
        monkeypatch.setitem(sys.modules, "hermes_constants", None)  # type: ignore[arg-type]
        env_home = tmp_path / "env-hermes"
        monkeypatch.setenv("HERMES_HOME", str(env_home))
        assert plugin._resolve_plugin_db_path(None, plugin_api.ValidationError) == (
            env_home / "plugin-data" / "kleinanzeigen" / "seen_ads.db"
        )

        # 6. Platform fallback when HERMES_HOME is unset
        monkeypatch.delenv("HERMES_HOME", raising=False)
        monkeypatch.setattr(plugin.sys, "platform", "win32")
        local_appdata = tmp_path / "LocalAppData"
        monkeypatch.setenv("LOCALAPPDATA", str(local_appdata))
        assert plugin._resolve_plugin_db_path(None, plugin_api.ValidationError) == (
            local_appdata / "hermes" / "plugin-data" / "kleinanzeigen" / "seen_ads.db"
        )

        monkeypatch.setattr(plugin.sys, "platform", "linux")
        assert plugin._resolve_plugin_db_path(None, plugin_api.ValidationError) == (
            Path.home() / ".hermes" / "plugin-data" / "kleinanzeigen" / "seen_ads.db"
        )


class TestChromiumDiscoveryAndPlaywrightErrors:
    """Tests for cross-platform Chromium executable discovery and Playwright error reporting."""

    def test_browser_executable_path_env_var_used_and_missing_raises(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        fake_chrome = tmp_path / "custom-chrome"
        fake_chrome.write_text("#!/bin/sh\n", encoding="utf-8")
        monkeypatch.setenv("BROWSER_EXECUTABLE_PATH", str(fake_chrome))

        page = MagicMock()
        page.url = "https://www.kleinanzeigen.de/s-seite:1?keywords=fahrrad"
        page.goto.return_value = SimpleNamespace(status=200)
        page.content.return_value = BEM_HTML
        chromium, _ = _install_fake_playwright(monkeypatch, page_factory=lambda: page)

        results = api.search_listings("fahrrad", fetch_mode="browser", limit=2)
        assert len(results) == 2
        chromium.launch.assert_called_once_with(
            headless=True, executable_path=str(fake_chrome)
        )

        # Command name resolved via shutil.which
        chromium.launch.reset_mock()
        monkeypatch.setenv("BROWSER_EXECUTABLE_PATH", "my-chromium-bin")
        monkeypatch.setattr(
            api.shutil,
            "which",
            lambda name: str(fake_chrome) if name == "my-chromium-bin" else None,
        )
        api.search_listings("fahrrad", fetch_mode="browser", limit=1)
        chromium.launch.assert_called_once_with(
            headless=True, executable_path=str(fake_chrome)
        )

        # Non-existent configured executable fails cleanly with BROWSER_EXECUTABLE_PATH message
        monkeypatch.setattr(api.shutil, "which", lambda name: None)
        missing_path = str(tmp_path / "missing-chrome")
        monkeypatch.setenv("BROWSER_EXECUTABLE_PATH", missing_path)
        with pytest.raises(api.KleinanzeigenError) as exc_info:
            api.search_listings("fahrrad", fetch_mode="browser")
        assert "BROWSER_EXECUTABLE_PATH" in str(exc_info.value)
        assert missing_path in str(exc_info.value)

    def test_discover_chromium_from_hermes_home_tools_and_which(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.delenv("BROWSER_EXECUTABLE_PATH", raising=False)
        monkeypatch.delenv("BROWSER_CDP_URL", raising=False)
        hermes_home = tmp_path / "hermes-home"
        monkeypatch.setenv("HERMES_HOME", str(hermes_home))

        old_exe = hermes_home / "tools" / "chromium-1100" / "chrome-linux64" / "chrome"
        new_exe = hermes_home / "tools" / "chromium-1208" / "chrome-linux64" / "chrome"
        old_exe.parent.mkdir(parents=True, exist_ok=True)
        new_exe.parent.mkdir(parents=True, exist_ok=True)
        old_exe.write_text("old", encoding="utf-8")
        new_exe.write_text("new", encoding="utf-8")
        if sys.platform != "win32":
            old_exe.chmod(0o755)
            new_exe.chmod(0o755)

        page = MagicMock()
        page.url = "https://www.kleinanzeigen.de/s-seite:1?keywords=fahrrad"
        page.goto.return_value = SimpleNamespace(status=200)
        page.content.return_value = BEM_HTML
        chromium, _ = _install_fake_playwright(monkeypatch, page_factory=lambda: page)

        launched_paths: list[str | None] = []

        def fake_launch(**kwargs: Any) -> Any:
            exe = kwargs.get("executable_path")
            launched_paths.append(exe)
            if exe is None:
                raise RuntimeError(
                    "BrowserType.launch: Executable doesn't exist at /root/.cache/ms-playwright/chrome"
                )
            browser = MagicMock()
            browser.new_context.return_value = chromium.launch.return_value.new_context()
            return browser

        chromium.launch.side_effect = fake_launch
        monkeypatch.setattr(api.shutil, "which", lambda cmd: None)

        results = api.search_listings("fahrrad", fetch_mode="browser", limit=2)
        assert len(results) == 2
        assert launched_paths == [None, str(new_exe)]

        # When $HERMES_HOME has no Chromium, shutil.which("google-chrome") is discovered
        monkeypatch.setenv("HERMES_HOME", str(tmp_path / "empty-hermes"))
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "empty-local"))
        monkeypatch.setattr(api.Path, "home", lambda: tmp_path / "empty-home")
        monkeypatch.setattr(
            api.shutil,
            "which",
            lambda cmd: "/usr/bin/google-chrome" if cmd == "google-chrome" else None,
        )
        launched_paths.clear()
        api.search_listings("fahrrad", fetch_mode="browser", limit=1)
        assert launched_paths == [None, "/usr/bin/google-chrome"]

    @pytest.mark.parametrize(
        "launch_error,expected_substrings",
        [
            (
                "BrowserType.launch: Executable doesn't exist at /home/user/.cache/ms-playwright/chromium",
                ["playwright install chromium --only-shell", "BROWSER_EXECUTABLE_PATH", "fetch_mode='http'"],
            ),
            (
                "BrowserType.launch: Host system is missing dependencies to run browsers.",
                ["libnspr4.so", "libnss3.so", "playwright install-deps chromium", "BROWSER_CDP_URL", "fetch_mode='http'"],
            ),
            (
                "error while loading shared libraries: libnss3.so: cannot open shared object file",
                ["libnspr4.so", "libnss3.so", "playwright install-deps chromium", "fetch_mode='http'"],
            ),
        ],
    )
    def test_playwright_missing_binary_and_missing_shared_libs_errors(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        launch_error: str,
        expected_substrings: list[str],
    ) -> None:
        monkeypatch.delenv("BROWSER_EXECUTABLE_PATH", raising=False)
        monkeypatch.delenv("BROWSER_CDP_URL", raising=False)
        monkeypatch.setenv("HERMES_HOME", str(tmp_path / "no-tools"))
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "no-local"))
        monkeypatch.setattr(api.Path, "home", lambda: tmp_path / "no-home")
        monkeypatch.setattr(api.shutil, "which", lambda cmd: None)
        monkeypatch.setattr(api.sys, "platform", "win32")

        chromium, _ = _install_fake_playwright(monkeypatch)
        chromium.launch.side_effect = RuntimeError(launch_error)

        with pytest.raises(api.KleinanzeigenError) as exc_info:
            api.search_listings("fahrrad", fetch_mode="browser")
        for expected in expected_substrings:
            assert expected in str(exc_info.value)

        # In auto mode after HTTP 403, missing binary/shared libs surface as KleinanzeigenBlockedError
        class BlockedSession:
            def __enter__(self) -> BlockedSession:
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def get(self, url: str, **kwargs: Any) -> Any:
                return SimpleNamespace(
                    status_code=403,
                    url=url,
                    text="<h1>IP-Bereich vorübergehend gesperrt.</h1>",
                    encoding="utf-8",
                    content=b"",
                    headers={},
                )

        monkeypatch.setattr(api.requests, "Session", BlockedSession)
        with pytest.raises(api.KleinanzeigenBlockedError) as blocked_exc:
            api.search_listings("fahrrad", fetch_mode="auto")
        assert blocked_exc.value.status_code == 403
        for expected in expected_substrings:
            assert expected in blocked_exc.value.reason
