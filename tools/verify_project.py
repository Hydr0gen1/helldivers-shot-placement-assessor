from __future__ import annotations

import argparse
import re
from pathlib import Path

from PIL import Image


PNG_RE = re.compile(r'"([^"\r\n]+\.png)"', re.IGNORECASE)
def calculation_core(html: str) -> str:
    script = html.split("<script>", 1)[1]
    for marker in ("// ============ DERIVED RANKING", "// ============ UI ============"):
        if marker in script:
            return script.split(marker, 1)[0].rstrip()
    raise AssertionError("Could not locate the preserved calculation core")


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify the deployable assessor and its local image bundle.")
    parser.add_argument("html", type=Path, nargs="?", default=Path("shot-placement-assessor.html"))
    parser.add_argument("--original", type=Path)
    parser.add_argument("--assets", type=Path, default=Path("assets/anatomy"))
    args = parser.parse_args()

    html = args.html.read_text(encoding="utf-8")
    references = sorted(set(PNG_RE.findall(html)), key=str.casefold)
    expected = {re.sub(r"\.png$", ".webp", name, flags=re.IGNORECASE) for name in references}
    actual = {path.name for path in args.assets.glob("*.webp")}
    missing = sorted(expected - actual, key=str.casefold)
    if missing:
        raise AssertionError(f"Missing {len(missing)} local images; first: {missing[:5]}")

    invalid = []
    for path in args.assets.glob("*.webp"):
        try:
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                if image.format != "WEBP" or image.width > 300 or image.height > 300:
                    invalid.append(f"{path.name}: {image.format} {image.size}")
        except Exception as exc:  # noqa: BLE001 - aggregate verification failures
            invalid.append(f"{path.name}: {exc}")
    if invalid:
        raise AssertionError(f"Invalid assets: {invalid[:5]}")

    required = [
        'role="tablist"',
        "function rankParts",
        "function rankWeapons",
        "function renderCompare",
        "function formatShareSummary",
        "hd2-shot-placement:v3",
        'rel="noopener noreferrer"',
        'assets/favicon.svg',
        "localStorage.setItem",
    ]
    absent = [marker for marker in required if marker not in html]
    if absent:
        raise AssertionError(f"Missing expected implementation markers: {absent}")

    if args.original:
        original = args.original.read_text(encoding="utf-8")
        if calculation_core(original) != calculation_core(html):
            raise AssertionError("Data/calculation core differs from the original")

    print(f"Verified {len(references)} image references and {len(actual)} WebP files")
    print("Data/calculation core unchanged" if args.original else "Core comparison skipped")
    print("Project verification passed")


if __name__ == "__main__":
    main()
