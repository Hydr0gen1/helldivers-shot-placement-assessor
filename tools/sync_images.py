from __future__ import annotations

import argparse
import io
import json
import re
import time
import threading
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PIL import Image


FILE_RE = re.compile(r'"([^"\r\n]+\.png)"', re.IGNORECASE)
API_URL = "https://helldivers.wiki.gg/api.php"
_request_lock = threading.Lock()
_last_request = 0.0


def pace_requests(minimum_interval: float = 0.3) -> None:
    global _last_request
    with _request_lock:
        delay = minimum_interval - (time.monotonic() - _last_request)
        if delay > 0:
            time.sleep(delay)
        _last_request = time.monotonic()


def normalize_name(filename: str) -> str:
    return filename.replace("_", " ").casefold()


def resolve_thumbnail_urls(filenames: list[str]) -> tuple[dict[str, str], list[str]]:
    resolved: dict[str, str] = {}
    missing: list[str] = []
    lookup = {normalize_name(name): name for name in filenames}
    for offset in range(0, len(filenames), 40):
        batch = filenames[offset : offset + 40]
        query = urllib.parse.urlencode({
            "action": "query",
            "format": "json",
            "prop": "imageinfo",
            "iiprop": "url",
            "iiurlwidth": "300",
            "titles": "|".join("File:" + name for name in batch),
        })
        pace_requests(0.5)
        request = urllib.request.Request(API_URL + "?" + query, headers={"User-Agent": "HD2-Shot-Placement-Asset-Sync/1.0"})
        with urllib.request.urlopen(request, timeout=45) as response:
            payload = json.load(response)
        found = set()
        for page in payload.get("query", {}).get("pages", {}).values():
            key = normalize_name(page.get("title", "").removeprefix("File:"))
            original = lookup.get(key)
            info = page.get("imageinfo", [])
            if original and info and info[0].get("thumburl"):
                resolved[original] = info[0]["thumburl"]
                found.add(original)
        missing.extend(name for name in batch if name not in found)
    return resolved, missing


def sync_one(filename: str, url: str, output_dir: Path, force: bool) -> tuple[str, str]:
    destination = output_dir / re.sub(r"\.png$", ".webp", filename, flags=re.IGNORECASE)
    if destination.exists() and destination.stat().st_size > 0 and not force:
        return filename, "cached"
    error = None
    for attempt in range(6):
        try:
            pace_requests()
            request = urllib.request.Request(url, headers={"User-Agent": "HD2-Shot-Placement-Asset-Sync/1.0"})
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read()
            with Image.open(io.BytesIO(raw)) as image:
                image.load()
                if image.mode not in ("RGB", "RGBA"):
                    image = image.convert("RGBA")
                image.thumbnail((300, 300), Image.Resampling.LANCZOS)
                destination.parent.mkdir(parents=True, exist_ok=True)
                image.save(destination, "WEBP", quality=82, method=6)
            return filename, "downloaded"
        except urllib.error.HTTPError as exc:
            error = exc
            if exc.code == 429:
                retry_after = exc.headers.get("Retry-After")
                time.sleep(float(retry_after) if retry_after and retry_after.isdigit() else min(30, 3 * (attempt + 1)))
                continue
            break
        except Exception as exc:  # noqa: BLE001 - report each failed remote asset
            error = exc
            time.sleep(min(10, 0.8 * (attempt + 1)))
    return filename, f"FAILED: {error}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Download and optimize all anatomy images referenced by the assessor.")
    parser.add_argument("html", type=Path, nargs="?", default=Path("index.html"))
    parser.add_argument("--output", type=Path, default=Path("assets/anatomy"))
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    filenames = sorted(set(FILE_RE.findall(args.html.read_text(encoding="utf-8"))), key=str.casefold)
    args.output.mkdir(parents=True, exist_ok=True)
    cached = [name for name in filenames if (args.output / re.sub(r"\.png$", ".webp", name, flags=re.IGNORECASE)).exists() and not args.force]
    pending = [name for name in filenames if name not in cached]
    print(f"Resolving {len(pending)} direct thumbnail URLs ({len(cached)} cached)")
    urls, missing = resolve_thumbnail_urls(pending)
    failures = [(name, "FAILED: image not returned by MediaWiki API") for name in missing]
    counts = {"cached": len(cached), "downloaded": 0}
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = [pool.submit(sync_one, name, url, args.output, args.force) for name, url in urls.items()]
        for index, future in enumerate(as_completed(futures), 1):
            name, status = future.result()
            if status.startswith("FAILED"):
                failures.append((name, status))
            else:
                counts[status] += 1
            if index % 25 == 0 or index == len(futures):
                print(f"Processed {index}/{len(futures)}")
    print(f"Images: {counts['downloaded']} downloaded, {counts['cached']} cached, {len(failures)} failed")
    if failures:
        for name, status in failures:
            print(f"  {name}: {status}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
