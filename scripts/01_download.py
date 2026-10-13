"""Step 1: download the corpus PDFs listed in data/raw/manifest.yaml.

    uv run python scripts/01_download.py

Skips files that already exist. Only accepts responses that really are PDFs.
"""

import sys

import httpx

from rag.ingest.manifest import load_manifest


def main() -> int:
    failed = 0
    with httpx.Client(follow_redirects=True, timeout=60) as client:
        for entry in load_manifest():
            if entry.path.exists():
                print(f"  skip  {entry.doc_id} (already downloaded)")
                continue
            tmp = entry.path.with_suffix(".part")
            try:
                with client.stream("GET", entry.source_url) as resp:
                    resp.raise_for_status()
                    with tmp.open("wb") as f:
                        for chunk in resp.iter_bytes():
                            f.write(chunk)
                if tmp.read_bytes()[:5] != b"%PDF-":
                    raise ValueError("response is not a PDF")
                tmp.rename(entry.path)
                print(f"  ok    {entry.doc_id} ({entry.path.stat().st_size / 1e6:.1f} MB)")
            except Exception as e:  # noqa: BLE001 - report and continue with the rest
                tmp.unlink(missing_ok=True)
                failed += 1
                print(f"  FAIL  {entry.doc_id}: {e}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
