"""Secure resolution of opaque dataset IDs to uploaded files."""
import os
import stat
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID

BASE_DIR = Path(__file__).resolve().parents[1]
UPLOAD_DIR = BASE_DIR / "data" / "uploads"
SUPPORTED_DATASET_EXTENSIONS = (".csv", ".xlsx", ".json")


def _canonical_dataset_id(dataset_id: str) -> str:
    try:
        parsed_id = UUID(str(dataset_id))
    except (ValueError, TypeError, AttributeError):
        raise FileNotFoundError("Dataset not found.") from None
    canonical_id = str(parsed_id)
    if str(dataset_id) != canonical_id:
        raise FileNotFoundError("Dataset not found.")
    return canonical_id


def resolve_dataset_path(dataset_id: str) -> Path:
    """Resolve a canonical UUID only to a regular file in UPLOAD_DIR.

    Client-supplied paths are never interpreted as filesystem paths. Symlinks
    are rejected so a file placed in the upload directory cannot redirect a
    lookup outside the permitted storage root.
    """
    canonical_id = _canonical_dataset_id(dataset_id)
    upload_root = UPLOAD_DIR.resolve()
    for extension in SUPPORTED_DATASET_EXTENSIONS:
        candidate = UPLOAD_DIR / f"{canonical_id}{extension}"
        if candidate.is_symlink():
            continue
        if not candidate.is_file():
            continue
        resolved = candidate.resolve()
        if resolved.parent != upload_root:
            continue
        return resolved

    raise FileNotFoundError("Dataset not found.")


@contextmanager
def open_dataset_by_id(dataset_id: str):
    """Open a dataset relative to the trusted upload directory and keep the
    descriptor stable for all validation and parser passes.

    POSIX uses openat-style dir_fd plus O_NOFOLLOW. Windows lacks that Python
    interface, so it verifies lstat/fstat identity around the open and relies
    on the upload directory being writable only by the application/trusted
    operators. The caller must not reopen the returned file by path.
    """
    canonical_id = _canonical_dataset_id(dataset_id)
    upload_root = UPLOAD_DIR.resolve(strict=True)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    dir_flag = getattr(os, "O_DIRECTORY", 0)
    supports_dir_fd = os.open in getattr(os, "supports_dir_fd", set()) and dir_flag and nofollow

    for extension in SUPPORTED_DATASET_EXTENSIONS:
        name = f"{canonical_id}{extension}"
        candidate = upload_root / name
        file_fd = None
        try:
            if supports_dir_fd:
                directory_fd = os.open(upload_root, os.O_RDONLY | dir_flag)
                try:
                    file_fd = os.open(name, flags | nofollow, dir_fd=directory_fd)
                finally:
                    os.close(directory_fd)
            else:
                before = candidate.lstat()
                if stat.S_ISLNK(before.st_mode):
                    continue
                file_fd = os.open(candidate, flags | nofollow)
                opened = os.fstat(file_fd)
                after = candidate.lstat()
                if (not stat.S_ISREG(opened.st_mode)
                        or not os.path.samestat(before, opened)
                        or not os.path.samestat(after, opened)):
                    os.close(file_fd)
                    continue
            opened = os.fstat(file_fd)
            if not stat.S_ISREG(opened.st_mode):
                os.close(file_fd)
                continue
        except (FileNotFoundError, NotADirectoryError, OSError):
            if file_fd is not None:
                try:
                    os.close(file_fd)
                except OSError:
                    pass
            continue
        with os.fdopen(file_fd, "rb") as source:
            yield source, extension
        return
    raise FileNotFoundError("Dataset not found.")


@contextmanager
def open_dataset_path(path: str | Path):
    """Open a server-selected path once, rejecting final-component symlinks."""
    candidate = Path(path)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        if os.name == "nt":
            before = candidate.lstat()
            if stat.S_ISLNK(before.st_mode):
                raise FileNotFoundError("Dataset not found.")
            file_fd = os.open(candidate, flags)
            opened = os.fstat(file_fd)
            after = candidate.lstat()
            if (not stat.S_ISREG(opened.st_mode)
                    or not os.path.samestat(before, opened)
                    or not os.path.samestat(after, opened)):
                os.close(file_fd)
                raise FileNotFoundError("Dataset not found.")
        else:
            parent = candidate.parent.resolve(strict=True)
            dir_flag = getattr(os, "O_DIRECTORY", 0)
            nofollow = getattr(os, "O_NOFOLLOW", 0)
            if dir_flag and nofollow and os.open in getattr(os, "supports_dir_fd", set()):
                directory_fd = os.open(parent, os.O_RDONLY | dir_flag)
                try:
                    file_fd = os.open(candidate.name, flags | nofollow, dir_fd=directory_fd)
                finally:
                    os.close(directory_fd)
            else:
                file_fd = os.open(candidate, flags | nofollow)
            if not stat.S_ISREG(os.fstat(file_fd).st_mode):
                os.close(file_fd)
                raise FileNotFoundError("Dataset not found.")
    except OSError:
        raise FileNotFoundError("Dataset not found.") from None
    with os.fdopen(file_fd, "rb") as source:
        yield source
