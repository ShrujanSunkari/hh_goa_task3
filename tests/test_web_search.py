import pytest
from modules.web_search import WebSearchEngine, _extract_domain, _merge_and_deduplicate


def test_extract_domain():
    assert _extract_domain("https://www.google.com/search") == "google.com"
    assert _extract_domain("http://x.com/elonmusk") == "x.com"
    assert _extract_domain("https://linkedin.com/in/foo") == "linkedin.com"


def test_web_search_engine_merge_and_deduplicate():
    raw_serp = [
        {"title": "Elon", "link": "https://x.com/elon", "thumbnail": "thumb1"},
        {"title": "Junk", "link": "https://pinterest.com/elon", "thumbnail": "thumb2"},
    ]
    raw_bing = [
        {
            "title": "Elon",
            "link": "https://x.com/elon",
            "thumbnail": "thumb1",
        },  # Duplicate
        {
            "title": "Elon Wikipedia",
            "link": "https://en.wikipedia.org/wiki/Elon",
            "thumbnail": "thumb3",
        },
    ]

    scored = _merge_and_deduplicate([raw_serp, raw_bing, []])

    # x.com should be deduplicated (1), pinterest (1), wikipedia (1) = 3 total matches
    assert len(scored) == 3

    # High authority domains should score higher
    x_match = next(m for m in scored if m.domain == "x.com")
    wiki_match = next(m for m in scored if m.domain == "en.wikipedia.org")
    junk_match = next(m for m in scored if m.domain == "pinterest.com")

    assert x_match.confidence_bps > 9000
    assert wiki_match.confidence_bps > 8000
    assert junk_match.confidence_bps < 5000


def test_serpapi_success(mocker, tmp_path):
    mocker.patch(
        "modules.web_search.WebSearchEngine._call_serpapi",
        return_value={
            "visual_matches": [
                {
                    "title": "Test Title",
                    "link": "https://x.com/test",
                    "thumbnail": "http://thumb",
                }
            ]
        },
    )
    mocker.patch("modules.web_search.WebSearchEngine._bing_search")
    mocker.patch("modules.web_search.WebSearchEngine._yandex_search")

    engine = WebSearchEngine(api_key="dummy")

    img_path = str(tmp_path / "dummy1.jpg")
    with open(img_path, "wb") as f:
        f.write(b"dummy1")
    mocker.patch(
        "modules.web_search.WebSearchEngine._enhance_image", return_value=img_path
    )

    payload = engine.search_by_image(img_path)

    assert payload["engine_used"] == "serpapi"
    assert engine._bing_search.call_count == 0
    assert engine._yandex_search.call_count == 0


def test_bing_fallback(mocker, tmp_path):
    mocker.patch("modules.web_search.WebSearchEngine._call_serpapi", return_value={})
    mocker.patch(
        "modules.web_search.WebSearchEngine._bing_search",
        return_value=[
            {
                "title": "Test Title Bing",
                "link": "https://x.com/bing",
                "thumbnail": "http://thumb",
            }
        ],
    )
    mocker.patch("modules.web_search.WebSearchEngine._yandex_search")

    engine = WebSearchEngine(api_key="dummy")

    img_path = str(tmp_path / "dummy2.jpg")
    with open(img_path, "wb") as f:
        f.write(b"dummy2")
    mocker.patch(
        "modules.web_search.WebSearchEngine._enhance_image", return_value=img_path
    )

    payload = engine.search_by_image(img_path)

    assert payload["engine_used"] == "bing"
    assert engine._call_serpapi.call_count == 1
    assert engine._bing_search.call_count == 1
    assert engine._yandex_search.call_count == 0


def test_yandex_fallback(mocker, tmp_path):
    mocker.patch("modules.web_search.WebSearchEngine._call_serpapi", return_value={})
    mocker.patch("modules.web_search.WebSearchEngine._bing_search", return_value=[])
    mocker.patch(
        "modules.web_search.WebSearchEngine._yandex_search",
        return_value=[
            {
                "title": "Test Title Yandex",
                "link": "https://x.com/yandex",
                "thumbnail": "http://thumb",
            }
        ],
    )

    engine = WebSearchEngine(api_key="dummy")

    img_path = str(tmp_path / "dummy3.jpg")
    with open(img_path, "wb") as f:
        f.write(b"dummy3")
    mocker.patch(
        "modules.web_search.WebSearchEngine._enhance_image", return_value=img_path
    )

    payload = engine.search_by_image(img_path)

    assert payload["engine_used"] == "yandex"
    assert engine._call_serpapi.call_count == 1
    assert engine._bing_search.call_count == 1
    assert engine._yandex_search.call_count == 1


def test_all_fail(mocker, tmp_path):
    mocker.patch("modules.web_search.WebSearchEngine._call_serpapi", return_value={})
    mocker.patch("modules.web_search.WebSearchEngine._bing_search", return_value=[])
    mocker.patch("modules.web_search.WebSearchEngine._yandex_search", return_value=[])

    engine = WebSearchEngine(api_key="dummy")

    img_path = str(tmp_path / "dummy4.jpg")
    with open(img_path, "wb") as f:
        f.write(b"dummy4")
    mocker.patch(
        "modules.web_search.WebSearchEngine._enhance_image", return_value=img_path
    )

    payload = engine.search_by_image(img_path)

    assert payload["engine_used"] == ""
    assert engine._call_serpapi.call_count == 1
    assert engine._bing_search.call_count == 1
    assert engine._yandex_search.call_count == 1
