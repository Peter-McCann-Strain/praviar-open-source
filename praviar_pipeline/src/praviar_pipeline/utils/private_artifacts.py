"""Owner-only filesystem primitives for confidential pipeline artifacts."""

from __future__ import annotations

import os
import secrets
import stat
from contextlib import suppress
from pathlib import Path

PRIVATE_DIR_MODE = 0o700
PRIVATE_FILE_MODE = 0o600


def _lexists(path: Path) -> bool:
    return os.path.lexists(path)


def _reject_symlink_components(path: Path) -> None:
    current = path
    while True:
        if _lexists(current) and stat.S_ISLNK(current.lstat().st_mode):
            # macOS exposes /tmp and /var as immutable root-owned aliases into
            # /private. Those two platform aliases are safe prefixes; every
            # caller-controlled component beneath them is still rejected.
            # These are trusted root-owned OS aliases, never artifact targets.
            trusted_target = {
                Path("/tmp"): Path("/private/tmp"),  # nosec B108
                Path("/var"): Path("/private/var"),
            }.get(current)
            link_stat = current.lstat()
            if trusted_target is not None and link_stat.st_uid == 0:
                try:
                    resolved = current.resolve(strict=True)
                    target_stat = resolved.stat()
                except OSError:
                    resolved = None
                if (
                    resolved == trusted_target
                    and target_stat.st_uid == 0
                    and stat.S_ISDIR(target_stat.st_mode)
                ):
                    current = current.parent
                    continue
            raise OSError(f"Private artifact path contains a symlink: {current}")
        if current.parent == current:
            return
        current = current.parent


def _require_owner(st: os.stat_result, path: Path) -> None:
    getuid = getattr(os, "getuid", None)
    if getuid is not None and st.st_uid != getuid():
        raise PermissionError(f"Private artifact path is not owned by the current user: {path}")


def ensure_private_directory(path: Path) -> Path:
    """Create or harden ``path`` as an owner-only, non-symlink directory."""
    path = Path(path)
    _reject_symlink_components(path)
    missing: list[Path] = []
    current = path
    while not _lexists(current):
        missing.append(current)
        current = current.parent
    for directory in reversed(missing):
        os.mkdir(directory, PRIVATE_DIR_MODE)
    st = path.lstat()
    if not stat.S_ISDIR(st.st_mode):
        raise NotADirectoryError(path)
    _require_owner(st, path)
    os.chmod(path, PRIVATE_DIR_MODE, follow_symlinks=False)
    for directory in missing:
        os.chmod(directory, PRIVATE_DIR_MODE, follow_symlinks=False)
    return path


def prepare_private_output_path(path: Path) -> Path:
    """Validate a future output path without following or replacing symlinks."""
    path = Path(path)
    ensure_private_directory(path.parent)
    _reject_symlink_components(path)
    if _lexists(path):
        _validate_private_file(path)
    return path


def _validate_private_file(path: Path) -> None:
    st = path.lstat()
    if not stat.S_ISREG(st.st_mode):
        raise OSError(f"Private artifact is not a regular file: {path}")
    _require_owner(st, path)
    os.chmod(path, PRIVATE_FILE_MODE, follow_symlinks=False)


def private_file_for_read(path: Path) -> Path:
    """Harden and return an existing private regular file for reading."""
    path = prepare_private_output_path(path)
    if not _lexists(path):
        raise FileNotFoundError(path)
    _validate_private_file(path)
    return path


def read_private_bytes(path: Path, *, max_bytes: int) -> bytes:
    """Read an owner-only regular file through a no-follow descriptor with a cap."""
    if max_bytes < 1:
        raise ValueError("max_bytes must be positive")
    path = prepare_private_output_path(path)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise OSError(f"Private artifact is not a regular file: {path}")
        _require_owner(st, path)
        if st.st_size > max_bytes:
            raise OSError(f"Private artifact exceeds byte limit: {path}")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(fd, min(1024 * 1024, max_bytes - total + 1))
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise OSError(f"Private artifact exceeds byte limit: {path}")
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(fd)


def read_private_text(path: Path, *, max_bytes: int, encoding: str = "utf-8") -> str:
    """Read bounded private text without following a final-component symlink."""
    return read_private_bytes(path, max_bytes=max_bytes).decode(encoding, errors="replace")


def enforce_private_file(path: Path) -> Path:
    """Validate and chmod a file written by a trusted third-party renderer."""
    path = Path(path)
    _reject_symlink_components(path)
    _validate_private_file(path)
    return path


def atomic_write_bytes(path: Path, payload: bytes) -> None:
    """Atomically replace ``path`` with owner-only bytes in the same directory."""
    path = prepare_private_output_path(path)
    tmp = path.parent / f".{path.name}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(tmp, flags, PRIVATE_FILE_MODE)
    try:
        with os.fdopen(fd, "wb", closefd=True) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if _lexists(path):
            _validate_private_file(path)
        os.replace(tmp, path)
        os.chmod(path, PRIVATE_FILE_MODE, follow_symlinks=False)
    except BaseException:
        with suppress(FileNotFoundError):
            tmp.unlink()
        raise


def atomic_write_text(path: Path, payload: str, *, encoding: str = "utf-8") -> None:
    atomic_write_bytes(path, payload.encode(encoding))


def append_private_text(path: Path, payload: str, *, encoding: str = "utf-8") -> None:
    """Append one payload to a private regular file without following symlinks."""
    path = prepare_private_output_path(path)
    flags = os.O_WRONLY | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
    if not _lexists(path):
        flags |= os.O_CREAT | os.O_EXCL
    fd = os.open(path, flags, PRIVATE_FILE_MODE)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise OSError(f"Private artifact is not a regular file: {path}")
        _require_owner(st, path)
        os.fchmod(fd, PRIVATE_FILE_MODE)
        data = payload.encode(encoding)
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written == 0:
                raise OSError("Incomplete private artifact append")
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)
