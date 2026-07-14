"""Surface-neutral helpers for strict immutable report packages.

The helpers in this module deliberately operate on bytes and filesystem paths
only.  Report contracts remain responsible for deciding which artifacts belong
in a package and for validating their semantic content.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import secrets
import stat
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


_SAFE_PATH_SEGMENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_DIRECTORY_OPEN_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


class ReportPackageSecurityError(ValueError):
    """Raised when report package bytes or paths cannot be trusted."""


@dataclass(frozen=True, slots=True)
class StrictJsonRecord:
    """A strict JSON value together with the identity of its source bytes."""

    value: object
    sha256: str
    size: int


def canonical_json_bytes(value: object) -> bytes:
    """Serialize a JSON value deterministically and reject non-finite numbers."""

    try:
        rendered = (
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                indent=2,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError, OverflowError) as exc:
        raise ReportPackageSecurityError(
            f"cannot serialize canonical JSON: {exc}"
        ) from exc
    return rendered


def canonical_output_directory(
    output_root: str | Path,
    directory_name: str,
    run_id: str,
) -> Path:
    """Return a canonical per-run target below a non-symlink output root."""

    _require_safe_path_segment(directory_name, label="package directory name")
    _require_safe_path_segment(run_id, label="run_id")
    try:
        requested_root = Path(output_root).expanduser().absolute()
        resolved_root = requested_root.resolve()
        if requested_root != resolved_root:
            raise ReportPackageSecurityError(
                "requested output root must be canonical and contain no symlinks"
            )
        requested_root.mkdir(parents=True, exist_ok=True)
        _require_canonical_directory(requested_root, label="output root")

        package_root = requested_root / directory_name
        package_root.mkdir(exist_ok=True)
        _require_canonical_directory(package_root, label="package output root")

        target = package_root / run_id
        if os.path.lexists(target):
            _require_canonical_directory(target, label="package run directory")
        return target
    except ReportPackageSecurityError:
        raise
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise ReportPackageSecurityError(
            f"report package output directory is invalid: {exc}"
        ) from exc


def publish_immutable_directory(
    artifacts: Sequence[tuple[Path, bytes]],
) -> bool:
    """Atomically publish one immutable directory.

    Returns ``False`` for a new publication and ``True`` when an existing
    private directory contains exactly the requested names and bytes.
    """

    normalized = _normalize_artifacts(artifacts)
    paths = tuple(path for path, _data in normalized)
    target_directory = paths[0].parent
    parent = target_directory.parent

    try:
        parent.mkdir(parents=True, exist_ok=True)
        _require_canonical_directory(parent, label="immutable package parent")
    except ReportPackageSecurityError:
        raise
    except OSError as exc:
        raise ReportPackageSecurityError(
            f"cannot prepare immutable package parent: {exc}"
        ) from exc

    if os.path.lexists(target_directory):
        _require_exact_package(target_directory, normalized)
        return True

    staging_name = f".{target_directory.name}.{secrets.token_hex(12)}"
    parent_fd: int | None = None
    staging_fd: int | None = None
    staging_created = False
    published = False
    try:
        parent_fd = os.open(parent, _DIRECTORY_OPEN_FLAGS)
        os.mkdir(staging_name, mode=0o700, dir_fd=parent_fd)
        staging_created = True
        staging_fd = os.open(staging_name, _DIRECTORY_OPEN_FLAGS, dir_fd=parent_fd)
        os.fchmod(staging_fd, 0o700)

        for path, data in normalized:
            file_fd: int | None = None
            try:
                file_fd = os.open(
                    path.name,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=staging_fd,
                )
                os.fchmod(file_fd, 0o600)
                with os.fdopen(file_fd, "wb") as handle:
                    file_fd = None
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())
            finally:
                if file_fd is not None:
                    os.close(file_fd)

        os.fsync(staging_fd)
        os.rename(
            staging_name,
            target_directory.name,
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
        )
        published = True
        os.fsync(parent_fd)
        return False
    except OSError as exc:
        if not published and os.path.lexists(target_directory):
            _require_exact_package(target_directory, normalized)
            return True
        raise ReportPackageSecurityError(
            f"immutable report package could not be published: {exc}"
        ) from exc
    finally:
        if not published and staging_fd is not None:
            for path in paths:
                try:
                    os.unlink(path.name, dir_fd=staging_fd)
                except FileNotFoundError:
                    pass
        if staging_fd is not None:
            os.close(staging_fd)
        if not published and staging_created and parent_fd is not None:
            try:
                os.rmdir(staging_name, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
        if parent_fd is not None:
            os.close(parent_fd)


def read_strict_json_record(
    path: str | Path,
    *,
    label: str,
    maximum: int,
    require_private: bool = False,
) -> StrictJsonRecord:
    """Read bounded UTF-8 JSON while rejecting duplicate keys and infinities."""

    normalized_label = _normalized_label(label)
    data = read_bounded_bytes(
        path,
        label=normalized_label,
        maximum=maximum,
        require_private=require_private,
    )
    try:
        text = data.decode("utf-8")
    except UnicodeError as exc:
        raise ReportPackageSecurityError(
            f"cannot decode {normalized_label} as UTF-8: {exc}"
        ) from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
            parse_float=_strict_json_float,
        )
    except (
        json.JSONDecodeError,
        RecursionError,
        OverflowError,
        ValueError,
        ReportPackageSecurityError,
    ) as exc:
        raise ReportPackageSecurityError(f"invalid {normalized_label}: {exc}") from exc
    return StrictJsonRecord(
        value=value,
        sha256=sha256_bytes(data),
        size=len(data),
    )


def read_bounded_bytes(
    path: str | Path,
    *,
    label: str,
    maximum: int,
    require_private: bool = False,
) -> bytes:
    """Read at most ``maximum`` bytes from a regular non-symlink file."""

    normalized_label = _normalized_label(label)
    _require_nonnegative_maximum(maximum)
    try:
        normalized_path = Path(path)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise ReportPackageSecurityError(
            f"cannot read {normalized_label}: path is invalid"
        ) from exc

    file_descriptor: int | None = None
    try:
        file_descriptor = os.open(
            normalized_path,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
        )
        metadata = os.fstat(file_descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ReportPackageSecurityError(
                f"{normalized_label} is not a regular file"
            )
        if require_private and metadata.st_mode & 0o077:
            raise ReportPackageSecurityError(f"{normalized_label} is not private")
        if metadata.st_size > maximum:
            raise ReportPackageSecurityError(
                f"{normalized_label} exceeds byte limit {maximum}"
            )
        with os.fdopen(file_descriptor, "rb") as handle:
            file_descriptor = None
            data = handle.read(maximum + 1)
        if len(data) > maximum:
            raise ReportPackageSecurityError(
                f"{normalized_label} exceeds byte limit {maximum}"
            )
        return data
    except ReportPackageSecurityError:
        raise
    except OSError as exc:
        raise ReportPackageSecurityError(
            f"cannot read {normalized_label}: {exc}"
        ) from exc
    finally:
        if file_descriptor is not None:
            os.close(file_descriptor)


def require_private_directory(path: str | Path, *, label: str) -> None:
    """Require an existing canonical non-symlink directory with private mode."""

    normalized_label = _normalized_label(label)
    try:
        normalized_path = Path(path).absolute()
        metadata = normalized_path.lstat()
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or metadata.st_mode & 0o077
            or normalized_path.resolve(strict=True) != normalized_path
        ):
            raise ReportPackageSecurityError(
                f"{normalized_label} is not a private canonical directory"
            )
    except ReportPackageSecurityError:
        raise
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise ReportPackageSecurityError(
            f"cannot inspect {normalized_label}: {exc}"
        ) from exc


def require_exact_directory_entries(
    path: str | Path,
    expected_names: Sequence[str],
    *,
    label: str,
) -> None:
    """Require one private directory to contain exactly the named entries."""

    normalized_label = _normalized_label(label)
    names = tuple(expected_names)
    if not names or len(names) != len(set(names)):
        raise ReportPackageSecurityError(
            f"{normalized_label} expected entries must be non-empty and unique"
        )
    for name in names:
        _require_safe_path_segment(name, label=f"{normalized_label} entry name")
    require_private_directory(path, label=normalized_label)
    directory_fd: int | None = None
    try:
        directory_fd = os.open(Path(path), _DIRECTORY_OPEN_FLAGS)
        actual_names = set(os.listdir(directory_fd))
    except ReportPackageSecurityError:
        raise
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise ReportPackageSecurityError(
            f"cannot inspect {normalized_label} entries: {exc}"
        ) from exc
    finally:
        if directory_fd is not None:
            os.close(directory_fd)
    expected = set(names)
    missing = sorted(expected - actual_names)
    unexpected = sorted(actual_names - expected)
    if missing:
        raise ReportPackageSecurityError(
            f"{normalized_label} is incomplete; missing: " + ", ".join(missing)
        )
    if unexpected:
        raise ReportPackageSecurityError(
            f"{normalized_label} contains unexpected files: "
            + ", ".join(unexpected)
        )


def contained_source_path(
    value: str | Path | object,
    roots: Sequence[Path],
) -> Path:
    """Resolve one existing source and require containment in an allowed root."""

    if not roots:
        raise ReportPackageSecurityError("allowed source roots must not be empty")
    try:
        raw_value = str(value)
        if not raw_value:
            raise ValueError("source path is empty")
        path = Path(raw_value).resolve(strict=True)
        resolved_roots = tuple(Path(root).resolve(strict=True) for root in roots)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise ReportPackageSecurityError(
            f"source artifact path is invalid: {exc}"
        ) from exc
    if not any(path.is_relative_to(root) for root in resolved_roots):
        raise ReportPackageSecurityError("source artifact escapes allowed roots")
    return path


def unique_paths(values: Sequence[Path]) -> tuple[Path, ...]:
    """Resolve and de-duplicate paths without changing their first-seen order."""

    result: list[Path] = []
    try:
        for value in values:
            resolved = Path(value).resolve()
            if resolved not in result:
                result.append(resolved)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise ReportPackageSecurityError(f"cannot normalize paths: {exc}") from exc
    return tuple(result)


def sha256_bytes(data: bytes) -> str:
    """Return the lowercase SHA-256 identity of bytes."""

    if not isinstance(data, bytes):
        raise ReportPackageSecurityError("SHA-256 input must be bytes")
    return hashlib.sha256(data).hexdigest()


def _normalize_artifacts(
    artifacts: Sequence[tuple[Path, bytes]],
) -> tuple[tuple[Path, bytes], ...]:
    if not artifacts:
        raise ReportPackageSecurityError("immutable report package is empty")
    result: list[tuple[Path, bytes]] = []
    try:
        for path, data in artifacts:
            normalized_path = Path(path).absolute()
            _require_safe_path_segment(
                normalized_path.name,
                label="immutable artifact name",
            )
            if not isinstance(data, bytes):
                raise ReportPackageSecurityError(
                    f"immutable artifact {normalized_path.name!r} must contain bytes"
                )
            result.append((normalized_path, data))
    except ReportPackageSecurityError:
        raise
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise ReportPackageSecurityError(
            "immutable report package entries must be (path, bytes) pairs"
        ) from exc

    paths = tuple(path for path, _data in result)
    if len(paths) != len(set(paths)):
        raise ReportPackageSecurityError(
            "immutable report package contains duplicate paths"
        )
    parents = {path.parent for path in paths}
    if len(parents) != 1:
        raise ReportPackageSecurityError(
            "immutable report package must share one directory"
        )
    target_directory = paths[0].parent
    _require_safe_path_segment(
        target_directory.name,
        label="immutable package target name",
    )
    try:
        resolved_target = target_directory.resolve()
    except (OSError, RuntimeError, ValueError) as exc:
        raise ReportPackageSecurityError(
            f"immutable report package target is invalid: {exc}"
        ) from exc
    if resolved_target != target_directory:
        raise ReportPackageSecurityError(
            "immutable report package target must be canonical and contain no symlinks"
        )
    return tuple(result)


def _require_exact_package(
    target_directory: Path,
    artifacts: Sequence[tuple[Path, bytes]],
) -> None:
    require_private_directory(
        target_directory,
        label="immutable report package directory",
    )
    expected_names = {path.name for path, _data in artifacts}
    try:
        actual_names = set(os.listdir(target_directory))
    except OSError as exc:
        raise ReportPackageSecurityError(
            f"cannot inspect immutable report package: {exc}"
        ) from exc
    missing = sorted(expected_names - actual_names)
    if missing:
        raise ReportPackageSecurityError(
            "immutable report package is incomplete; missing: " + ", ".join(missing)
        )
    unexpected = sorted(actual_names - expected_names)
    if unexpected:
        raise ReportPackageSecurityError(
            "immutable report package contains unexpected files: "
            + ", ".join(unexpected)
        )
    for path, expected in artifacts:
        actual = read_bounded_bytes(
            path,
            label=f"immutable report package file {path.name}",
            maximum=len(expected),
            require_private=True,
        )
        if actual != expected:
            raise ReportPackageSecurityError(
                "immutable report package differs; create a new run_id"
            )


def _require_canonical_directory(path: Path, *, label: str) -> None:
    metadata = path.lstat()
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or path.resolve(strict=True) != path.absolute()
    ):
        raise ReportPackageSecurityError(
            f"{label} must be a canonical non-symlink directory"
        )


def _require_safe_path_segment(value: object, *, label: str) -> None:
    if not isinstance(value, str) or not _SAFE_PATH_SEGMENT_RE.fullmatch(value):
        raise ReportPackageSecurityError(f"{label} is invalid")


def _normalized_label(value: object) -> str:
    normalized = str(value).strip()
    return normalized or "artifact"


def _require_nonnegative_maximum(maximum: int) -> None:
    if isinstance(maximum, bool) or not isinstance(maximum, int) or maximum < 0:
        raise ReportPackageSecurityError(
            "artifact byte limit must be a non-negative integer"
        )


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ReportPackageSecurityError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> object:
    raise ReportPackageSecurityError(f"non-finite JSON constant: {value}")


def _strict_json_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ReportPackageSecurityError(f"non-finite JSON number: {value}")
    return parsed


__all__ = (
    "ReportPackageSecurityError",
    "StrictJsonRecord",
    "canonical_json_bytes",
    "canonical_output_directory",
    "contained_source_path",
    "publish_immutable_directory",
    "read_bounded_bytes",
    "read_strict_json_record",
    "require_exact_directory_entries",
    "require_private_directory",
    "sha256_bytes",
    "unique_paths",
)
