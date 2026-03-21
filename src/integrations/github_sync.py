import json
import logging
import os
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml


LOGGER = logging.getLogger(__name__)
GITHUB_API_BASE = "https://api.github.com"
DEFAULT_TIMEOUT_SECONDS = 30

_PROJECTS_YAML = Path(__file__).resolve().parents[1] / "config" / "projects.yaml"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat().replace("+00:00", "Z")


def _github_headers(accept: str = "application/vnd.github+json") -> dict[str, str]:
    headers = {
        "Accept": accept,
        "User-Agent": "telegram-research-agent",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _request_json(url: str, accept: str = "application/vnd.github+json") -> tuple[Any | None, bool]:
    request = urllib.request.Request(url, headers=_github_headers(accept=accept), method="GET")
    try:
        with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
            payload = response.read().decode("utf-8")
            return json.loads(payload), False
    except urllib.error.HTTPError as exc:
        remaining = exc.headers.get("X-RateLimit-Remaining")
        if exc.code == 403 and remaining == "0":
            LOGGER.warning("GitHub API rate limit reached for url=%s", url)
            return None, True
        LOGGER.warning("GitHub API request failed status=%s url=%s", exc.code, url)
    except urllib.error.URLError:
        LOGGER.warning("GitHub API network failure url=%s", url, exc_info=True)
    except Exception:
        LOGGER.warning("GitHub API unexpected failure url=%s", url, exc_info=True)
    return None, False


def _load_curated_projects() -> list[dict[str, Any]]:
    with open(_PROJECTS_YAML, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return [p for p in data.get("projects", []) if isinstance(p, dict)]


def _fetch_repo_metadata(repo_full_name: str) -> tuple[dict[str, Any] | None, bool]:
    url = f"{GITHUB_API_BASE}/repos/{repo_full_name}"
    payload, rate_limited = _request_json(url)
    if not isinstance(payload, dict):
        return None, rate_limited
    return payload, rate_limited


def _fetch_weekly_commits(repo_full_name: str, since_iso: str) -> tuple[int, bool]:
    query = urllib.parse.urlencode({"since": since_iso, "per_page": 100})
    url = f"{GITHUB_API_BASE}/repos/{repo_full_name}/commits?{query}"
    payload, rate_limited = _request_json(url)
    if not isinstance(payload, list):
        return 0, rate_limited
    return len(payload), rate_limited


def _sync_project(
    connection: sqlite3.Connection,
    repo: dict[str, Any],
    keywords_json: str,
    synced_at: str,
) -> None:
    full_name = str(repo.get("full_name") or "").strip()
    description = str(repo.get("description") or "")
    pushed_at = str(repo.get("pushed_at") or "")

    cursor = connection.execute(
        """
        INSERT OR IGNORE INTO projects (
            name,
            description,
            keywords,
            github_repo,
            last_commit_at,
            github_synced_at,
            active
        )
        VALUES (?, ?, ?, ?, ?, ?, 1)
        """,
        (full_name, description, keywords_json, full_name, pushed_at, synced_at),
    )
    if cursor.rowcount == 0:
        connection.execute(
            """
            UPDATE projects
            SET github_repo = ?,
                last_commit_at = ?,
                github_synced_at = ?,
                keywords = ?
            WHERE name = ?
            """,
            (full_name, pushed_at, synced_at, keywords_json, full_name),
        )


def sync_github_projects(db_path: str) -> list[dict]:
    if not os.environ.get("GITHUB_TOKEN"):
        LOGGER.warning("GITHUB_TOKEN is not set; GitHub sync will use unauthenticated requests")

    synced_at = _utc_now_iso()
    since_iso = (_utc_now() - timedelta(days=7)).isoformat().replace("+00:00", "Z")

    curated = _load_curated_projects()
    results: list[dict[str, Any]] = []

    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON;")
        connection.execute("PRAGMA journal_mode = WAL;")

        for project in curated:
            repo_full_name = str(project.get("repo") or "").strip()
            focus = str(project.get("focus") or "")
            if not repo_full_name:
                continue

            repo_meta, rate_limited = _fetch_repo_metadata(repo_full_name)
            if rate_limited:
                break
            if repo_meta is None:
                LOGGER.warning("Could not fetch metadata for repo=%s", repo_full_name)
                continue

            weekly_commits, rate_limited = _fetch_weekly_commits(repo_full_name, since_iso)
            if rate_limited:
                break

            keywords_list = [kw.strip() for kw in focus.split(",") if kw.strip()]

            # Use description from yaml if GitHub description is empty
            github_description = str(repo_meta.get("description") or "")
            yaml_description = str(project.get("description") or "")
            description = github_description if github_description else yaml_description

            repo_dict = {
                "full_name": repo_full_name,
                "description": description,
                "pushed_at": str(repo_meta.get("pushed_at") or ""),
            }

            try:
                connection.execute("BEGIN")
                _sync_project(
                    connection=connection,
                    repo=repo_dict,
                    keywords_json=json.dumps(keywords_list, ensure_ascii=True),
                    synced_at=synced_at,
                )
                connection.commit()
            except sqlite3.IntegrityError:
                connection.rollback()
                try:
                    connection.execute("BEGIN")
                    connection.execute(
                        """
                        UPDATE projects
                        SET github_repo = ?,
                            last_commit_at = ?,
                            github_synced_at = ?,
                            keywords = ?
                        WHERE name = ?
                        """,
                        (
                            repo_full_name,
                            str(repo_meta.get("pushed_at") or ""),
                            synced_at,
                            json.dumps(keywords_list, ensure_ascii=True),
                            repo_full_name,
                        ),
                    )
                    connection.commit()
                except Exception:
                    connection.rollback()
                    LOGGER.warning("Failed to update existing project row for repo=%s", repo_full_name, exc_info=True)
                    continue
            except Exception:
                connection.rollback()
                LOGGER.warning("Failed to sync repo=%s into projects table", repo_full_name, exc_info=True)
                continue

            results.append(
                {
                    "name": repo_full_name,
                    "description": description,
                    "keywords_list": keywords_list,
                    "weekly_commits": weekly_commits,
                    "last_commit_at": str(repo_meta.get("pushed_at") or ""),
                    "github_repo": repo_full_name,
                }
            )

    LOGGER.info("GitHub sync complete repos_synced=%d", len(results))
    return results
