"""Repo-local skill sync manager.

Keeps approved skill mirrors aligned across this repository only. The manifest is
the source of truth; this script never scans or writes global skill directories.
"""

from __future__ import annotations

import argparse
import filecmp
import hashlib
import json
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "docs" / "skill-sync-manifest.json"
BACKUP_ROOT = ROOT / ".artifacts" / "skill-sync-backups"
SKILL_SURFACES = (
    ROOT / ".agents" / "skills",
    ROOT / ".claude" / "skills",
    ROOT / "docs" / "skills",
)
IGNORE_DIRS = {"__pycache__", ".git"}
IGNORE_SUFFIXES = {".pyc", ".pyo"}


@dataclass(frozen=True)
class SyncGroup:
    id: str
    canonical: Path
    mirrors: tuple[Path, ...]
    mode: str
    reason: str


def _repo_path(raw: str) -> Path:
    path = (ROOT / raw).resolve()
    root = ROOT.resolve()
    if path != root and root not in path.parents:
        raise ValueError(f"path escapes repo: {raw}")
    return path


def _rel(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def _load_manifest() -> tuple[list[SyncGroup], set[Path], dict[str, Any]]:
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    groups = [
        SyncGroup(
            id=str(item["id"]),
            canonical=_repo_path(str(item["canonical"])),
            mirrors=tuple(_repo_path(str(path)) for path in item.get("mirrors", [])),
            mode=str(item.get("mode", "copy")),
            reason=str(item.get("reason", "")),
        )
        for item in payload.get("sync_groups", [])
    ]
    standalone = {_repo_path(str(path)) for path in payload.get("standalone_skills", [])}
    return groups, standalone, payload


def _iter_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    files: list[Path] = []
    for path in root.rglob("*"):
        if any(part in IGNORE_DIRS for part in path.relative_to(root).parts):
            continue
        if path.is_file() and path.suffix not in IGNORE_SUFFIXES:
            files.append(path)
    return sorted(files)


def _tree_digest(root: Path) -> str | None:
    if not root.exists():
        return None
    digest = hashlib.sha256()
    for path in _iter_files(root):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _compare_trees(left: Path, right: Path) -> list[str]:
    if not left.exists():
        return [f"missing canonical: {_rel(left)}"]
    if not right.exists():
        return [f"missing mirror: {_rel(right)}"]

    left_files = {path.relative_to(left).as_posix(): path for path in _iter_files(left)}
    right_files = {path.relative_to(right).as_posix(): path for path in _iter_files(right)}
    diffs: list[str] = []

    for relative in sorted(left_files.keys() - right_files.keys()):
        diffs.append(f"mirror missing file: {_rel(right)}/{relative}")
    for relative in sorted(right_files.keys() - left_files.keys()):
        diffs.append(f"mirror extra file: {_rel(right)}/{relative}")
    for relative in sorted(left_files.keys() & right_files.keys()):
        if not filecmp.cmp(left_files[relative], right_files[relative], shallow=False):
            diffs.append(f"mirror file differs: {_rel(right)}/{relative}")
    return diffs


def _inventory_skill_dirs() -> list[Path]:
    dirs: list[Path] = []
    for surface in SKILL_SURFACES:
        if not surface.exists():
            continue
        for skill_file in surface.rglob("SKILL.md"):
            dirs.append(skill_file.parent.resolve())
        for skill_file in surface.rglob("SKILLS.md"):
            dirs.append(skill_file.parent.resolve())
    return sorted(set(dirs))


def _coverage(groups: list[SyncGroup], standalone: set[Path]) -> dict[str, list[str]]:
    known: set[Path] = set(standalone)
    for group in groups:
        known.add(group.canonical)
        known.update(group.mirrors)
    actual = set(_inventory_skill_dirs())
    return {
        "unknown": sorted(_rel(path) for path in actual - known),
        "missing_declared": sorted(_rel(path) for path in known if not path.exists()),
    }


def _status() -> dict[str, Any]:
    groups, standalone, manifest = _load_manifest()
    group_status = []
    has_drift = False

    for group in groups:
        mirror_status = []
        canonical_digest = _tree_digest(group.canonical)
        for mirror in group.mirrors:
            diffs = _compare_trees(group.canonical, mirror)
            has_drift = has_drift or bool(diffs)
            mirror_status.append(
                {
                    "path": _rel(mirror),
                    "digest": _tree_digest(mirror),
                    "in_sync": not diffs,
                    "diffs": diffs,
                }
            )
        group_status.append(
            {
                "id": group.id,
                "canonical": _rel(group.canonical),
                "canonical_digest": canonical_digest,
                "mode": group.mode,
                "reason": group.reason,
                "mirrors": mirror_status,
            }
        )

    coverage = _coverage(groups, standalone)
    return {
        "manifest": _rel(MANIFEST_PATH),
        "version": manifest.get("version"),
        "has_drift": has_drift,
        "coverage_ok": not coverage["unknown"] and not coverage["missing_declared"],
        "coverage": coverage,
        "sync_groups": group_status,
        "standalone_skills": sorted(_rel(path) for path in standalone),
        "planned_conversions": manifest.get("planned_conversions", []),
    }


def _backup_path(group_id: str, mirror: Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_mirror = _rel(mirror).replace("/", "__").replace("\\", "__").replace(":", "")
    return BACKUP_ROOT / timestamp / group_id / safe_mirror


def _copy_tree(canonical: Path, mirror: Path, group_id: str, force: bool) -> dict[str, Any]:
    diffs = _compare_trees(canonical, mirror)
    if not diffs:
        return {"mirror": _rel(mirror), "changed": False, "backup": None}
    if not force:
        return {
            "mirror": _rel(mirror),
            "changed": False,
            "backup": None,
            "refused": True,
            "reason": "mirror differs; rerun with --force to overwrite after backup",
            "diffs": diffs,
        }
    if not canonical.exists():
        raise FileNotFoundError(f"canonical skill missing: {_rel(canonical)}")

    backup: Path | None = None
    if mirror.exists():
        backup = _backup_path(group_id, mirror)
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(mirror, backup)
        shutil.rmtree(mirror)
    mirror.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(canonical, mirror)
    return {"mirror": _rel(mirror), "changed": True, "backup": _rel(backup) if backup else None}


def _sync(write: bool, force: bool) -> dict[str, Any]:
    groups, _, _ = _load_manifest()
    results = []
    refused = False
    for group in groups:
        if group.mode != "copy":
            results.append({"id": group.id, "error": f"unsupported mode: {group.mode}"})
            refused = True
            continue
        mirror_results = []
        for mirror in group.mirrors:
            if write:
                result = _copy_tree(group.canonical, mirror, group.id, force=force)
            else:
                diffs = _compare_trees(group.canonical, mirror)
                result = {"mirror": _rel(mirror), "changed": bool(diffs), "diffs": diffs}
            refused = refused or bool(result.get("refused"))
            mirror_results.append(result)
        results.append({"id": group.id, "canonical": _rel(group.canonical), "mirrors": mirror_results})
    return {"write": write, "force": force, "refused": refused, "results": results}


def main() -> int:
    parser = argparse.ArgumentParser(description="Repo-local skill sync manager")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("audit", help="Inventory manifest coverage and drift.")
    subparsers.add_parser("check", help="Return nonzero if mirrors drift or manifest coverage is incomplete.")
    sync_parser = subparsers.add_parser("sync", help="Preview or write approved mirror syncs.")
    sync_parser.add_argument("--write", action="store_true", help="Copy canonical skills to mirrors.")
    sync_parser.add_argument("--force", action="store_true", help="Overwrite drifted mirrors after backing them up.")
    args = parser.parse_args()

    if args.command == "audit":
        print(json.dumps(_status(), indent=2, sort_keys=True))
        return 0
    if args.command == "check":
        status = _status()
        print(json.dumps(status, indent=2, sort_keys=True))
        return 0 if not status["has_drift"] and status["coverage_ok"] else 1
    if args.command == "sync":
        result = _sync(write=args.write, force=args.force)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 1 if result["refused"] else 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
