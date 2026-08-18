#!/usr/bin/env python3
"""Pin the Docker base images to the digests currently in use.

`python:3.12-slim`, `node:20-slim`, `postgres:16-alpine` and `redis:7-alpine` are
FLOATING tags: upstream repoints them whenever they publish, so two rebuilds of the
same commit can produce different images. That turns "it worked yesterday" into a
question nobody can answer, and it means a compromised or merely broken upstream push
lands in production on the next unrelated deploy.

This pins each tag to the digest of the image ALREADY PULLED ON THIS HOST - that is,
the exact bytes the current, working deployment was built from. The tag is kept
alongside the digest (`python:3.12-slim@sha256:...`) so the file still says at a
glance which version it is.

Run this ON THE SERVER, after a successful build, so the digests are the tested ones.

Upgrading later is deliberate and one command:
    docker pull python:3.12-slim && python3 scripts/pin-image-digests.py --repin
`--repin` re-reads whatever is now local and rewrites the pins.

Partial application is ALLOWED here and is safe: each pin is independent, so an image
that cannot be resolved is reported and skipped rather than blocking the others. This
is a supply-chain nicety, not a security fix whose halves depend on each other.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

TARGETS: dict[Path, tuple[str, ...]] = {
    Path("backend/Dockerfile"): ("python:3.12-slim",),
    Path("frontend/Dockerfile"): ("node:20-slim",),
    Path("docker-compose.prod.yml"): ("postgres:16-alpine", "redis:7-alpine"),
}

REPIN = "--repin" in sys.argv


def digest_for(ref: str) -> str | None:
    """The repo digest of the locally-present image, e.g. sha256:abc... ."""
    try:
        out = subprocess.run(
            ["docker", "image", "inspect", "--format", "{{index .RepoDigests 0}}", ref],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0 or "@sha256:" not in out.stdout:
        return None
    return out.stdout.strip().split("@", 1)[1]


def main() -> None:
    missing = [p for p in TARGETS if not p.exists()]
    if missing:
        print(f"ABORTED: not found: {', '.join(str(p) for p in missing)}", file=sys.stderr)
        print("Run from the repository root.", file=sys.stderr)
        raise SystemExit(1)

    pinned, skipped, already = 0, [], 0

    for path, refs in TARGETS.items():
        text = path.read_text()
        original = text
        for ref in refs:
            name, tag = ref.split(":", 1)
            # An existing pin for this tag, so --repin can replace it.
            pinned_re = re.compile(rf"{re.escape(ref)}@sha256:[0-9a-f]{{64}}")
            has_pin = bool(pinned_re.search(text))
            if has_pin and not REPIN:
                already += 1
                continue

            digest = digest_for(ref)
            if digest is None:
                skipped.append(ref)
                continue

            if has_pin:
                text = pinned_re.sub(f"{ref}@{digest}", text)
            else:
                # Only bare occurrences - never a tag that is already pinned.
                text = re.sub(rf"{re.escape(ref)}(?!@)", f"{ref}@{digest}", text)
            pinned += 1

        if text != original:
            path.write_text(text)
            print(f"pinned {path}")

    if already and not pinned:
        print(f"already pinned ({already} image(s)) - nothing to do")
    if skipped:
        print(f"\nSKIPPED (not present locally): {', '.join(skipped)}")
        print("Pull them and rerun to pin those too:")
        for ref in skipped:
            print(f"  docker pull {ref}")
    if pinned:
        print(f"\n{pinned} image(s) pinned to the digests this host already built from.")
        print("Rebuild to confirm nothing moved: docker compose -f docker-compose.prod.yml build")


if __name__ == "__main__":
    main()
