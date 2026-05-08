"""Process-safe file I/O helpers.

Writing a JSON state file (seen.json, manifest.json, an archive) in
one shot looks atomic but is not — if the process is interrupted
mid-write (Ctrl-C, OOM, GitHub Actions runner shutdown, disk full)
the file is left half-written and the next run can't load it.

`atomic_write_text` writes to a temp file in the same directory as
the target, then issues a single rename which IS atomic on every
POSIX filesystem and on Windows NTFS via os.replace().
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path


def atomic_write_text(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    """Write `content` to `path` atomically.

    Writes to a temp file in the same directory as `path`, fsyncs it,
    then os.replace() into the final name. The temp lives in the same
    directory so the rename is on the same filesystem (renames across
    filesystems aren't atomic).

    On any error the temp file is cleaned up before the exception
    propagates, so a failed write never leaves stale .tmp files behind.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="") as f:
            f.write(content)
            f.flush()
            try:
                os.fsync(f.fileno())
            except (OSError, AttributeError):
                # fsync may not be supported on every fs (e.g. some
                # network mounts). The os.replace below is still
                # crash-safe in the common case.
                pass
        os.replace(tmp_path, path)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
