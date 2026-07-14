"""Regenerate text-free hero images for selected font statuses or slugs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.database import get_db
from app.services.admin_actions import regenerate_font_poster


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("slugs", nargs="*")
    parser.add_argument("--statuses", nargs="+", default=["active", "queued"])
    args = parser.parse_args()

    with get_db() as conn:
        if args.slugs:
            slugs = list(dict.fromkeys(args.slugs))
        else:
            placeholders = ",".join("?" for _ in args.statuses)
            rows = conn.execute(
                f"SELECT slug FROM font_registry WHERE status IN ({placeholders}) ORDER BY slug",
                tuple(args.statuses),
            ).fetchall()
            slugs = [row["slug"] for row in rows]

    failures: list[tuple[str, str]] = []
    for index, slug in enumerate(slugs, start=1):
        print(f"[{index}/{len(slugs)}] {slug}", flush=True)
        try:
            with get_db() as conn:
                regenerate_font_poster(conn, slug)
        except Exception as exc:
            failures.append((slug, str(exc)))
            print(f"  failed: {exc}", flush=True)
        else:
            print("  regenerated", flush=True)

    print(f"Completed: {len(slugs) - len(failures)}/{len(slugs)}", flush=True)
    if failures:
        print("Failures:", flush=True)
        for slug, error in failures:
            print(f"- {slug}: {error}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
