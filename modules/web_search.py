"""
web_search.py
-------------
Stage 2 of the pipeline: OSINT face identification via SerpAPI Google Lens.

Public surface
--------------
    WebSearchEngine(api_key=None)
        .search_by_image(image_path, top_n=5)  -> dict
        .generate_payload_hash(source_url, image_bytes, metadata=None) -> dict

Payload dict schema
-------------------
    {
        "title":          str,
        "source_url":     str,
        "domain":         str,
        "thumbnail_url":  str,
        "image_bytes":    bytes,
        "confidence_bps": int,       # 0 – 10 000
        "raw_matches":    list[dict]
    }

Hash dict schema (generate_payload_hash)
-----------------------------------------
    {
        "hex":     "0x<64 hex chars>",   # for display / JSON
        "bytes32": bytes                 # for Web3 / Solidity calls
    }
"""

from __future__ import annotations

import hashlib
import io
import os
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional
from urllib.parse import urlparse

import requests
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

# ── Social / authoritative and junk domain definitions for scoring ──────────
_AUTHORITATIVE_HIGH: List[str] = [
    "x.com",
    "twitter.com",
    "linkedin.com",
    "instagram.com",
    "wikipedia.org",
    "youtube.com",
    "facebook.com",
    "github.com",
]

_AUTHORITATIVE_MED: List[str] = [
    "imdb.com",
    "themoviedb.org",
    "tmdb.org",
    "bbc.com",
    "reuters.com",
    "forbes.com",
    "nytimes.com",
    "theguardian.com",
]

_JUNK_DOMAINS: List[str] = [
    "pinterest",
    "alamy",
    "stock",
    "shutterstock",
    "gettyimages",
    "istockphoto",
    "depositphotos",
    "vectorstock",
    "tupaki",
    "greatandhra",
    "idlebrain",
]

_SERPAPI_ENDPOINT = "https://serpapi.com/search"
_DOWNLOAD_TIMEOUT = 10   # seconds

_search_cache: Dict[str, Dict] = {}


# ─────────────────────────────────────────────────────────────────────────────
#  Internal dataclass (used for scoring and sorting)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class _Match:
    title:          str
    source_url:     str
    domain:         str
    thumbnail_url:  str
    rank:           int    # original rank from SerpAPI (0-based)
    confidence_bps: int    # final calculated score (0-10000)


# ─────────────────────────────────────────────────────────────────────────────
#  Main class
# ─────────────────────────────────────────────────────────────────────────────


class WebSearchEngine:
    """
    Reverse-image OSINT engine backed by SerpAPI Google Lens.

    Parameters
    ----------
    api_key : SerpAPI key.  Falls back to ``SERPAPI_KEY`` env var if omitted.
    """

    def __init__(self, api_key: Optional[str] = None) -> None:
        self._api_key = api_key or os.getenv("SERPAPI_KEY", "")
        if not self._api_key:
            console.print(
                Panel(
                    "[bold yellow]SERPAPI_KEY is not set.[/]\n"
                    "Add it to your [cyan].env[/] file or pass it to "
                    "[cyan]WebSearchEngine(api_key=...)[/].\n\n"
                    "[dim]Calls will fail until a valid key is provided.[/]",
                    title="⚠  WebSearchEngine — Missing API Key",
                    border_style="yellow",
                )
            )

    # ─────────────────────────────────────────────────────────────────────────
    #  Public: search_by_image
    # ─────────────────────────────────────────────────────────────────────────

    def search_by_image(
        self,
        image_path: str,
        top_n: int = 5,
    ) -> Dict:
        """
        Submit *image_path* to SerpAPI Google Lens and return the best match.

        Parameters
        ----------
        image_path : Path to the face crop (JPG / PNG).
        top_n      : How many raw matches to preserve in ``raw_matches``.

        Returns
        -------
        dict — see module docstring for schema.

        Raises
        ------
        EnvironmentError  if SERPAPI_KEY is missing.
        FileNotFoundError if image_path does not exist.
        RuntimeError      if the API returns an error or no matches found.
        """
        img_path = self._validate_image(image_path)

        with open(img_path, "rb") as f:
            img_bytes = f.read()
        img_hash = hashlib.sha256(img_bytes).hexdigest()

        global _search_cache
        if img_hash in _search_cache:
            console.log("[green]Retrieved search result from in-memory cache.[/]")
            return _search_cache[img_hash]

        console.log(
            f"[bold cyan]WebSearchEngine[/] → Google Lens on "
            f"[yellow]{image_path}[/]"
        )

        # ── Upload image & call SerpAPI ───────────────────────────────────────
        raw_matches = []
        fallback_reason = "No image results found"
        try:
            self._require_key()
            raw_response = self._call_serpapi(img_path)
            raw_matches  = raw_response.get("visual_matches", [])
        except (EnvironmentError, RuntimeError) as e:
            fallback_reason = str(e)
            console.log(f"[yellow]SerpAPI encountered an error: {e}[/]")

        if not raw_matches:
            console.log(f"[yellow]Trying Bing fallback. Reason: {fallback_reason}[/]")
            raw_matches = self._bing_search(img_path)

        if not raw_matches:
            _warn(
                "Google Lens and Bing returned no visual matches for this image.\n"
                "• Ensure the face crop is clear and well-lit.\n"
                "• The person may not have a public web presence."
            )
            payload = _empty_payload()
            _search_cache[img_hash] = payload
            return payload

        # ── Sort / prioritise ─────────────────────────────────────────────────
        scored   = _score_matches(raw_matches)
        best     = scored[0]

        # ── Download thumbnail ────────────────────────────────────────────────
        image_bytes = _download_bytes(best.thumbnail_url)

        # ── Build payload ─────────────────────────────────────────────────────
        payload: Dict = {
            "title":          best.title,
            "source_url":     best.source_url,
            "domain":         best.domain,
            "thumbnail_url":  best.thumbnail_url,
            "image_bytes":    image_bytes,
            "confidence_bps": best.confidence_bps,
            "raw_matches":    raw_matches[:top_n],
        }

        _print_result(payload, scored[:top_n])
        _search_cache[img_hash] = payload
        return payload

    # ─────────────────────────────────────────────────────────────────────────
    #  Public: generate_payload_hash
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def generate_payload_hash(
        source_url:  str,
        image_bytes: bytes,
        metadata:    Optional[Dict] = None,
    ) -> Dict:
        """
        Compute a deterministic SHA-256 fingerprint of the OSINT payload.

        The hash input is the UTF-8 encoding of *source_url* concatenated with
        the raw *image_bytes*.  An optional *metadata* dict is JSON-serialised
        and appended for extra determinism when needed.

        Parameters
        ----------
        source_url  : Canonical URL of the identified social page / post.
        image_bytes : Raw bytes of the matched thumbnail image.
        metadata    : Optional extra fields (e.g. title, domain, confidence).

        Returns
        -------
        dict:
            "hex"     – "0x" + 64-char lowercase hex string   (for JSON / logs)
            "bytes32" – 32-byte ``bytes`` object              (for Web3 calls)
        """
        h = hashlib.sha256()
        h.update(source_url.encode("utf-8"))
        h.update(image_bytes)

        if metadata:
            import json as _json
            h.update(_json.dumps(metadata, sort_keys=True).encode("utf-8"))

        digest: bytes = h.digest()        # 32 bytes
        hex_str = "0x" + digest.hex()

        console.log(
            f"[bold cyan]WebSearchEngine[/] → payload hash "
            f"[green]{hex_str[:18]}…[/]"
        )
        return {"hex": hex_str, "bytes32": digest}

    # ─────────────────────────────────────────────────────────────────────────
    #  Private helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _require_key(self) -> None:
        if not self._api_key:
            raise EnvironmentError(
                "SERPAPI_KEY is not set.  Add it to .env or pass to "
                "WebSearchEngine(api_key=...)."
            )

    @staticmethod
    def _validate_image(image_path: str) -> str:
        from pathlib import Path
        p = Path(image_path)
        if not p.exists():
            raise FileNotFoundError(
                f"Image not found: {image_path}\n"
                "Run the face detection stage first to generate the crop."
            )
        return str(p.resolve())

    def _call_serpapi(self, image_path: str) -> Dict:
        """
        Upload the face crop to a temporary public host, then query
        SerpAPI Google Lens via GET with the ``url`` parameter.

        SerpAPI Google Lens does not accept raw multipart file uploads —
        the image must be passed as a publicly accessible URL.
        We use 0x0.st as a zero-auth temporary image host (365-day retention).
        """
        # Step 1: get a public URL for the local image
        public_url = self._upload_image(image_path)
        console.log(f"[dim]Image hosted at: {public_url}[/]")

        # Step 2: call SerpAPI Google Lens with url param (GET)
        params = {
            "engine":  "google_lens",
            "api_key": self._api_key,
            "url":     public_url,
            "hl":      "en",
        }
        try:
            resp = requests.get(
                _SERPAPI_ENDPOINT,
                params=params,
                timeout=30,
            )
            if resp.status_code != 200:
                print(f"[ERROR] SerpAPI returned {resp.status_code}: {resp.text[:200]}")
                return {}

        except requests.exceptions.Timeout:
            raise RuntimeError("SerpAPI request timed out after 30 s.")
        except requests.exceptions.ConnectionError as exc:
            raise RuntimeError(f"Network error reaching SerpAPI: {exc}")

        if resp.status_code == 429:
            raise RuntimeError(
                "SerpAPI rate limit exceeded.  Wait a moment and retry."
            )
        if resp.status_code in (401, 403):
            raise RuntimeError(
                f"SerpAPI rejected the key (HTTP {resp.status_code}). "
                "Verify SERPAPI_KEY at https://serpapi.com/manage-api-key"
            )
        if not resp.ok:
            raise RuntimeError(
                f"SerpAPI returned HTTP {resp.status_code}: {resp.text[:300]}"
            )

        data = resp.json()
        if "error" in data:
            raise RuntimeError(f"SerpAPI error: {data['error']}")
        return data

    @staticmethod
    def _upload_image(image_path: str) -> str:
        """
        Upload *image_path* to a free public host and return the URL.

        Tries in order:
          1. catbox.moe  — no account, permanent storage, 200 MB limit
          2. transfer.sh — no account, 14-day retention
        """
        console.log("[dim]Uploading face crop to temporary host...[/]")
        fname = os.path.basename(image_path)

        # ── 1. catbox.moe ─────────────────────────────────────────────────────
        try:
            with open(image_path, "rb") as fh:
                resp = requests.post(
                    "https://catbox.moe/user/api.php",
                    data={"reqtype": "fileupload"},
                    files={"fileToUpload": (fname, fh, "image/jpeg")},
                    timeout=20,
                )
            if resp.ok and resp.text.strip().startswith("http"):
                url = resp.text.strip()
                console.log(f"[dim]Hosted at: {url}[/]")
                return url
        except requests.exceptions.RequestException:
            pass

        # ── 2. transfer.sh fallback ───────────────────────────────────────────
        try:
            with open(image_path, "rb") as fh:
                resp = requests.put(
                    f"https://transfer.sh/{fname}",
                    data=fh,
                    timeout=20,
                )
            if resp.ok and resp.text.strip().startswith("http"):
                url = resp.text.strip()
                console.log(f"[dim]Hosted at: {url} (transfer.sh)[/]")
                return url
        except requests.exceptions.RequestException:
            pass

        raise RuntimeError(
            "Could not upload the face crop to any public host.\n"
            "Check your internet connection, or use --offline-mock."
        )

    def _bing_search(self, image_path: str) -> List[Dict]:
        """
        Fallback search using Bing Visual Search API.
        Returns a list of dicts with 'title', 'link', 'thumbnail' keys 
        similar to SerpAPI visual_matches.
        """
        bing_key = os.getenv("BING_API_KEY", "")
        if not bing_key:
            console.log("[yellow]BING_API_KEY is not set. Skipping Bing fallback.[/]")
            return []

        endpoint = "https://api.bing.microsoft.com/v7.0/images/visualsearch"
        headers = {"Ocp-Apim-Subscription-Key": bing_key}

        console.log("[dim]Uploading face crop to Bing Visual Search...[/]")
        try:
            with open(image_path, "rb") as fh:
                file_dict = {"image": ("image.jpg", fh, "image/jpeg")}
                resp = requests.post(endpoint, headers=headers, files=file_dict, timeout=30)
            
            resp.raise_for_status()
            data = resp.json()
            
            raw_matches = []
            for tag in data.get("tags", []):
                for action in tag.get("actions", []):
                    if action.get("actionType") == "PagesIncluding":
                        for item in action.get("data", {}).get("value", []):
                            raw_matches.append({
                                "title": item.get("name", "Untitled"),
                                "link": item.get("hostPageUrl", ""),
                                "thumbnail": item.get("thumbnailUrl", "")
                            })
            return raw_matches

        except Exception as exc:
            console.log(f"[yellow]Bing search failed: {exc}[/]")
            return []



# ─────────────────────────────────────────────────────────────────────────────
#  Module-level utilities
# ─────────────────────────────────────────────────────────────────────────────

def _score_matches(raw_matches: List[Dict]) -> List[_Match]:
    """
    Convert raw SerpAPI visual_matches to sorted _Match objects.

    Scoring Algorithm:
      1. Base Score: Tapers down from 7500 based on original SerpAPI rank (min 1000).
      2. Domain Bonus: +2500 for tier-1 social/authoritative domains (x.com, linkedin, instagram, etc.)
                       +1500 for tier-2 news/entertainment databases (imdb, tmdb, bbc, etc.)
      3. Domain Penalty: -5000 for junk, stock photos, or low-quality aggregators (pinterest, alamy, stock, tupaki, etc.)
      4. Final Score: Clamped between 0 and 10000 (basis points).
    """
    scored: List[_Match] = []
    for rank, item in enumerate(raw_matches):
        url    = item.get("link", "")
        domain = _extract_domain(url)

        base_score = max(1000, 7500 - (rank * 200))

        bonus = 0
        penalty = 0

        domain_lower = domain.lower()
        if any(d in domain_lower for d in _AUTHORITATIVE_HIGH):
            bonus = 2500
        elif any(d in domain_lower for d in _AUTHORITATIVE_MED):
            bonus = 1500

        if any(d in domain_lower for d in _JUNK_DOMAINS):
            penalty = 5000

        confidence_bps = max(0, min(10000, base_score + bonus - penalty))

        scored.append(
            _Match(
                title=item.get("title", "Untitled"),
                source_url=url,
                domain=domain,
                thumbnail_url=item.get("thumbnail", ""),
                rank=rank,
                confidence_bps=confidence_bps,
            )
        )

    # Sort descending by calculated confidence_bps (highest score #1)
    scored.sort(key=lambda m: (m.confidence_bps, -m.rank), reverse=True)
    return scored


def _extract_domain(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
        # Strip www. prefix
        return host.removeprefix("www.")
    except Exception:
        return ""



def _download_bytes(url: str) -> bytes:
    """Download *url* into memory.  Returns empty bytes on failure."""
    if not url:
        return b""
    try:
        resp = requests.get(url, timeout=_DOWNLOAD_TIMEOUT)
        resp.raise_for_status()
        return resp.content
    except Exception as exc:
        console.log(f"[yellow]⚠  Thumbnail download failed: {exc}[/]")
        return b""


def _empty_payload() -> Dict:
    return {
        "title":          "",
        "source_url":     "",
        "domain":         "",
        "thumbnail_url":  "",
        "image_bytes":    b"",
        "confidence_bps": 0,
        "raw_matches":    [],
    }


def _warn(message: str) -> None:
    console.print(
        Panel(f"[bold yellow]{message}[/]", title="⚠  No Matches", border_style="yellow")
    )


def _print_result(payload: Dict, top_matches: List[_Match]) -> None:
    tbl = Table(title="🔍 Google Lens — OSINT Results", show_lines=True)
    tbl.add_column("#",          style="dim",         width=4)
    tbl.add_column("Domain",     style="bold cyan",   width=20)
    tbl.add_column("Title",      style="white",       max_width=40)
    tbl.add_column("Conf (bps)", style="green",       justify="right", width=12)
    tbl.add_column("URL",        style="dim",         max_width=50)

    for i, m in enumerate(top_matches, 1):
        marker = "⭐ " if i == 1 else ""
        tbl.add_row(
            str(i),
            marker + m.domain,
            m.title,
            str(m.confidence_bps),
            m.source_url,
        )

    console.print(tbl)
    console.print(
        Panel(
            f"[bold]Best match:[/]    [green]{payload['title']}[/]\n"
            f"[bold]Domain:[/]        [cyan]{payload['domain']}[/]\n"
            f"[bold]Confidence:[/]    [magenta]{payload['confidence_bps']} bps "
            f"({payload['confidence_bps']/100:.1f}%)[/]\n"
            f"[bold]Source URL:[/]    {payload['source_url']}\n"
            f"[bold]Thumbnail:[/]     {payload['thumbnail_url']}\n"
            f"[bold]Image bytes:[/]   {len(payload['image_bytes']):,} bytes",
            title="✅ Top Identification Match",
            border_style="green",
        )
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Smoke test  (python modules/web_search.py inputs/target_cropped.jpg)
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    if len(sys.argv) < 2:
        console.print(
            "[bold red]Usage:[/]  python modules/web_search.py <image_path> [top_n]"
        )
        sys.exit(1)

    img   = sys.argv[1]
    top_n = int(sys.argv[2]) if len(sys.argv) > 2 else 5

    console.rule("[bold blue]WebSearchEngine — Smoke Test")
    engine  = WebSearchEngine()
    payload = engine.search_by_image(img, top_n=top_n)

    if payload["source_url"]:
        h = engine.generate_payload_hash(
            source_url=payload["source_url"],
            image_bytes=payload["image_bytes"],
            metadata={"title": payload["title"], "domain": payload["domain"]},
        )
        console.print(f"\n[bold]Payload hash (hex):[/]    [green]{h['hex']}[/]")
        console.print(f"[bold]Payload hash (bytes32):[/] {h['bytes32'].hex()}")
    else:
        console.print("[yellow]No match found — hash skipped.[/]")

    console.rule("[bold green]Done")
