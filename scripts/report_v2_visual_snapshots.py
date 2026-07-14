#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path
from typing import Iterable

from output.report_v2_regression_fixtures import (
    load_report_v2_regression_manifest,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGET = PROJECT_ROOT / "tests" / "fixtures" / "report_v2" / "visual_components.v1.html"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "output" / "report_v2_visual_snapshots"


class SnapshotHarnessError(RuntimeError):
    pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Capture deterministic Report V2 visual snapshots.")
    parser.add_argument(
        "--manifest",
        default="tests/fixtures/intelligence_report_v2/irx13_fixture_manifest.v1.json",
        help="Path to the IRX-13 regression fixture manifest.",
    )
    parser.add_argument(
        "--viewports",
        nargs="+",
        default=["1440x1000", "375x1000"],
        help="Viewport sizes to capture, e.g. 1440x1000 375x1000.",
    )
    parser.add_argument(
        "--target-html",
        default=str(DEFAULT_TARGET.relative_to(PROJECT_ROOT)),
        help="Sanitized HTML file to capture. Private generated reports are not allowed.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR.relative_to(PROJECT_ROOT)),
        help="Directory for generated local screenshots.",
    )
    parser.add_argument(
        "--check-prerequisites",
        action="store_true",
        help="Validate manifest and local Playwright/Chromium availability without writing screenshots.",
    )
    args = parser.parse_args(argv)

    manifest_path = _repo_path(args.manifest)
    manifest = load_report_v2_regression_manifest(manifest_path)
    target_html = _repo_path(args.target_html)
    output_dir = _repo_path(args.output_dir)
    viewports = [_parse_viewport(item) for item in args.viewports]

    try:
        _validate_target_html(target_html)
        playwright = _load_playwright()
        _check_chromium(playwright)
    except SnapshotHarnessError as exc:
        print(f"Report V2 visual snapshot prerequisites unavailable: {exc}", file=sys.stderr)
        print(
            "Install the Python Playwright package and Chromium, then rerun the documented IRX-13 command.",
            file=sys.stderr,
        )
        return 2

    if args.check_prerequisites:
        print("Report V2 visual snapshot harness ready.")
        return 0

    approved_hashes = manifest["visual_regression"].get("approved_snapshot_hashes") or {}
    baseline_status = str(manifest["visual_regression"].get("baseline_status") or "")
    hashes = _capture_snapshots(
        playwright,
        target_html=target_html,
        output_dir=output_dir,
        viewports=viewports,
    )
    for viewport_id, digest in hashes.items():
        print(f"{viewport_id} sha256:{digest}")

    if baseline_status != "recorded":
        print(
            "No approved visual baselines are recorded in the manifest; review screenshots before recording hashes.",
            file=sys.stderr,
        )
        return 3

    mismatches = [
        f"{viewport_id}: expected {approved_hashes.get(viewport_id)} got {digest}"
        for viewport_id, digest in hashes.items()
        if approved_hashes.get(viewport_id) != digest
    ]
    if mismatches:
        print("Report V2 visual snapshot mismatch:", file=sys.stderr)
        for item in mismatches:
            print(f"- {item}", file=sys.stderr)
        return 1
    print("Report V2 visual snapshots match approved hashes.")
    return 0


def _repo_path(value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _parse_viewport(value: str) -> tuple[str, int, int]:
    match = re.fullmatch(r"(\d+)x(\d+)", value.strip())
    if not match:
        raise SystemExit(f"Invalid viewport {value!r}; expected WIDTHxHEIGHT")
    width = int(match.group(1))
    height = int(match.group(2))
    viewport_id = "desktop_1440" if width == 1440 else "mobile_375" if width == 375 else f"custom_{width}"
    return viewport_id, width, height


def _validate_target_html(path: Path) -> None:
    if not path.exists():
        raise SnapshotHarnessError(f"target HTML does not exist: {path}")
    if not path.is_relative_to(PROJECT_ROOT / "tests" / "fixtures"):
        raise SnapshotHarnessError("target HTML must be a committed sanitized fixture under tests/fixtures")
    text = path.read_text(encoding="utf-8")
    forbidden = ("<script", "<link", "@import", "http://", "https://")
    found = [item for item in forbidden if item in text.lower()]
    if found:
        raise SnapshotHarnessError("target HTML contains active or external presentation sources: " + ", ".join(found))


def _load_playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as exc:
        raise SnapshotHarnessError("Playwright Python package is not installed") from exc
    return sync_playwright


def _check_chromium(sync_playwright) -> None:
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            browser.close()
    except Exception as exc:  # pragma: no cover - depends on local browser install.
        raise SnapshotHarnessError(f"Chromium browser is not available: {exc}") from exc


def _capture_snapshots(
    sync_playwright,
    *,
    target_html: Path,
    output_dir: Path,
    viewports: Iterable[tuple[str, int, int]],
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    hashes: dict[str, str] = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            for viewport_id, width, height in viewports:
                page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=1)
                page.goto(target_html.as_uri(), wait_until="load")
                output_path = output_dir / f"{target_html.stem}.{viewport_id}.png"
                page.screenshot(path=str(output_path), full_page=True)
                digest = hashlib.sha256(output_path.read_bytes()).hexdigest()
                hashes[viewport_id] = digest
                page.close()
        finally:
            browser.close()
    return hashes


if __name__ == "__main__":
    raise SystemExit(main())
