"""
CapWifi – git tabanlı güncelleyici.

Uygulama bir git klonu olarak çalıştığı için "güncelleme" = origin/master ile
eşitleme. Buradaki fonksiyonlar bloklayıcıdır (ağ + subprocess); çağıran taraf
bunları bir thread içinde çalıştırmalı. Hiçbiri arayüze dokunmaz, yalnızca saf
sonuç döndürür.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List

REPO_DIR = Path(__file__).resolve().parent.parent
REMOTE = "origin"
BRANCH = "master"
_TIMEOUT = 45


@dataclass
class UpdateStatus:
    is_repo: bool
    ok: bool
    behind: int = 0
    local: str = ""
    remote: str = ""
    message: str = ""


def _run(args: List[str], timeout: int = _TIMEOUT) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(REPO_DIR), *args],
        capture_output=True, text=True, timeout=timeout,
    )


def is_git_repo() -> bool:
    try:
        r = _run(["rev-parse", "--is-inside-work-tree"], timeout=10)
        return r.returncode == 0 and r.stdout.strip() == "true"
    except Exception:
        return False


def _ensure_safe_directory() -> None:
    # Uygulama sudo ile çalışırsa git "dubious ownership" diyebilir; bunu önler.
    try:
        _run(["config", "--global", "--add", "safe.directory", str(REPO_DIR)],
             timeout=10)
    except Exception:
        pass


def check_for_update() -> UpdateStatus:
    """origin/master'a bakar; kaç commit geride olduğumuzu döndürür."""
    if not is_git_repo():
        return UpdateStatus(is_repo=False, ok=False, message="not a git repo")
    _ensure_safe_directory()
    try:
        fetch = _run(["fetch", REMOTE, BRANCH])
        if fetch.returncode != 0:
            return UpdateStatus(is_repo=True, ok=False,
                                message=(fetch.stderr or "fetch failed").strip())
        local = _run(["rev-parse", "HEAD"]).stdout.strip()
        remote = _run(["rev-parse", f"{REMOTE}/{BRANCH}"]).stdout.strip()
        if not remote:
            return UpdateStatus(is_repo=True, ok=False, local=local,
                                message="remote ref missing")
        behind = 0
        if local != remote:
            cnt = _run(["rev-list", "--count",
                        f"HEAD..{REMOTE}/{BRANCH}"]).stdout.strip()
            behind = int(cnt) if cnt.isdigit() else 0
        return UpdateStatus(is_repo=True, ok=True, behind=behind,
                            local=local[:7], remote=remote[:7])
    except subprocess.TimeoutExpired:
        return UpdateStatus(is_repo=True, ok=False, message="timeout")
    except Exception as e:
        return UpdateStatus(is_repo=True, ok=False, message=str(e))


def apply_update() -> UpdateStatus:
    """origin/master ile birebir eşitle (hard reset); yerel değişiklikler gider."""
    if not is_git_repo():
        return UpdateStatus(is_repo=False, ok=False, message="not a git repo")
    _ensure_safe_directory()
    try:
        fetch = _run(["fetch", REMOTE, BRANCH])
        if fetch.returncode != 0:
            return UpdateStatus(is_repo=True, ok=False,
                                message=(fetch.stderr or "fetch failed").strip())
        reset = _run(["reset", "--hard", f"{REMOTE}/{BRANCH}"])
        if reset.returncode != 0:
            return UpdateStatus(is_repo=True, ok=False,
                                message=(reset.stderr or "reset failed").strip())
        local = _run(["rev-parse", "HEAD"]).stdout.strip()
        return UpdateStatus(is_repo=True, ok=True, behind=0,
                            local=local[:7], remote=local[:7],
                            message=(reset.stdout or "").strip())
    except subprocess.TimeoutExpired:
        return UpdateStatus(is_repo=True, ok=False, message="timeout")
    except Exception as e:
        return UpdateStatus(is_repo=True, ok=False, message=str(e))
