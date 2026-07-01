from __future__ import annotations

import os
import sys
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parent


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def executable_dir() -> Path:
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return PACKAGE_DIR.parents[1]


def resource_root() -> Path:
    explicit = os.getenv("ER_RESOURCE_ROOT", "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", executable_dir())).resolve()
    return executable_dir()


def project_root() -> Path:
    explicit = os.getenv("ER_PROJECT_ROOT", "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()
    return executable_dir()


def web_dist_dir() -> Path:
    explicit = os.getenv("ER_WEB_DIST", "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()

    runtime_root = project_root()
    bundled_root = resource_root()
    candidates = [
        runtime_root / "web_dist",
        runtime_root / "web" / "dist",
        bundled_root / "web_dist",
        bundled_root / "web" / "dist",
    ]
    for candidate in candidates:
        if (candidate / "index.html").is_file():
            return candidate
    return candidates[0]
