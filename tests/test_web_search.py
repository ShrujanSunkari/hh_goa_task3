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
        {"title": "Elon", "link": "https://x.com/elon", "thumbnail": "thumb1"}, # Duplicate
        {"title": "Elon Wikipedia", "link": "https://en.wikipedia.org/wiki/Elon", "thumbnail": "thumb3"},
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

def test_search_by_image_mocked(mocker, tmp_path):
    mocker.patch("modules.web_search.WebSearchEngine._upload_image", return_value="http://dummy.url/img.jpg")
    
    mock_response = mocker.MagicMock()
    mock_response.status_code = 200
    mock_response.ok = True
    mock_response.json.return_value = {
        "visual_matches": [
            {"title": "Test Title", "link": "https://x.com/test", "thumbnail": "http://thumb"}
        ]
    }
    mocker.patch("requests.get", return_value=mock_response)
    
    engine = WebSearchEngine(api_key="dummy")
    
    img_path = str(tmp_path / "dummy.jpg")
    with open(img_path, 'wb') as f:
        f.write(b"dummy")
        
    mocker.patch("modules.web_search.WebSearchEngine._enhance_image", return_value=img_path)
    
    payload = engine.search_by_image(img_path)
    
    assert payload["source_url"] == "https://x.com/test"
    assert payload["domain"] == "x.com"
    assert payload["confidence_bps"] > 0
    assert payload["num_engines_matched"] >= 1
