from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def canonical_json(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha1_text(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk_size)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def now_iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def try_read_git_sha(project_root: Path) -> str | None:
    head = project_root / ".git" / "HEAD"
    if not head.exists():
        return None
    raw = head.read_text(encoding="utf-8").strip()
    if raw.startswith("ref:"):
        ref = raw.split(":", 1)[1].strip()
        ref_path = project_root / ".git" / ref
        if ref_path.exists():
            return ref_path.read_text(encoding="utf-8").strip()[:40] or None
        packed = project_root / ".git" / "packed-refs"
        if packed.exists():
            for line in packed.read_text(encoding="utf-8").splitlines():
                if not line or line.startswith("#") or line.startswith("^"):
                    continue
                parts = line.split()
                if len(parts) == 2 and parts[1].strip() == ref:
                    return parts[0].strip()[:40] or None
        return None
    return raw[:40] or None

