#!/usr/bin/env python3
"""Reject tracked Terraform state and saved-plan artifacts.

Terraform saved plans can embed state snapshots and sensitive values.  This
check deliberately uses Git's tracked-file inventory instead of a filesystem
walk so local, ignored operator artifacts do not make CI fail.
"""

from __future__ import annotations

import subprocess
from pathlib import Path, PurePosixPath


def _tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        check=True,
        capture_output=True,
    )
    return [
        entry.decode("utf-8", errors="surrogateescape")
        for entry in result.stdout.split(b"\0")
        if entry
    ]


def _is_terraform_artifact(path: str) -> bool:
    name = PurePosixPath(path).name.casefold()
    if name.endswith((".example", ".template")):
        return False
    return (
        name == "tfplan"
        or name.startswith("tfplan-")
        or name.startswith("tfplan.")
        or name.endswith(".tfplan")
        or name.endswith(".tfstate")
        or ".tfstate." in name
    )


def main() -> int:
    artifacts = sorted(
        path
        for path in _tracked_files()
        if _is_terraform_artifact(path) and Path(path).exists()
    )
    if not artifacts:
        print("Terraform artifact gate passed: no saved plans or state are tracked.")
        return 0

    print("Terraform artifact gate failed: tracked plan/state artifacts are forbidden:")
    for path in artifacts:
        print(f"  - {path}")
    print(
        "Remove the files from Git and rotate any credentials represented by their state."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
