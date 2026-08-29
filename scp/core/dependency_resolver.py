"""
Mảnh ghép #31 — Dynamic Dependency Resolver: tự phát hiện import thiếu.

TẠI SAO: Autofix sinh code `import aiohttp` nhưng .venv chưa cài →
ModuleNotFoundError → Judge báo UNKNOWN → mọi nỗ lực tư duy sụp đổ vì thiếu
một câu pip install. Resolver quét AST toàn bộ import của một file, phân
loại: STDLIB (bỏ qua), LOCAL (bỏ qua), INSTALLED (OK), MISSING (báo cáo).

An toàn: auto-install MẶT ĐỊNH TẮT (SCP_AUTO_INSTALL=1 mới bật) — tự chạy
pip là hành vi cấp hệ thống, phải có opt-out rõ ràng (DNA #9). Mapping
package-name ↔ import-name dùng cho các gói quen thuộc (pywin32, pyjwt...).
"""
from __future__ import annotations

import ast
import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Mapping import-name -> pip-package cho các gói quen thuộc tên lệch chuẩn
IMPORT_TO_PACKAGE = {
    "cv2": "opencv-python", "PIL": "pillow", "sklearn": "scikit-learn",
    "yaml": "pyyaml", "dotenv": "python-dotenv", "jwt": "pyjwt",
    "win32api": "pywin32", "win32con": "pywin32", "win32job": "pywin32",
    "win32process": "pywin32", "win32file": "pywin32", "win32pipe": "pywin32",
    "win32event": "pywin32", "pywintypes": "pywin32", "pythoncom": "pywin32",
    "slowapi": "slowapi", "multipart": "python-multipart",
    " prometheus_client": "prometheus-client", "prometheus_client": "prometheus-client",
}


@dataclass
class DependencyReport:
    missing_imports: list[str] = field(default_factory=list)
    missing_packages: list[str] = field(default_factory=list)
    installed: list[str] = field(default_factory=list)
    local_or_stdlib: list[str] = field(default_factory=list)


def _import_names(source: str) -> set[str]:
    names: set[str] = set()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return names
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


def resolve(source: str, local_modules: set[str] | None = None) -> DependencyReport:
    """Phân loại mọi import của source. Không cài gì — chỉ báo cáo."""
    local = local_modules or {"scp", "tests", "scripts"}
    report = DependencyReport()
    for name in sorted(_import_names(source)):
        if name in local:
            report.local_or_stdlib.append(name)
            continue
        spec = importlib.util.find_spec(name)
        if spec is not None:
            report.installed.append(name)
            continue
        # stdlib dynamic: thử import trực tiếp (find_spec miss một số edge)
        try:
            __import__(name)
            report.installed.append(name)
            continue
        except ImportError:
            pass
        report.missing_imports.append(name)
        report.missing_packages.append(IMPORT_TO_PACKAGE.get(name, name))
    return report


def auto_install(report: DependencyReport, timeout: int = 120) -> dict[str, Any]:
    """Cài các package thiếu qua pip. CHỈ chạy khi SCP_AUTO_INSTALL=1
    (opt-out mặc định — DNA #9: tự chạy pip là hành vi cấp hệ thống)."""
    import os
    import subprocess

    if not report.missing_packages:
        return {"installed": [], "skipped": "nothing missing"}
    if os.environ.get("SCP_AUTO_INSTALL", "0") != "1":
        return {"installed": [], "skipped": "SCP_AUTO_INSTALL is not 1 (default off)"}
    installed = []
    for package in report.missing_packages:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", package],
            capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode == 0:
            installed.append(package)
    return {"installed": installed}


def ensure_importable(source: str, local_modules: set[str] | None = None) -> dict[str, Any]:
    """One-shot: resolve + (nếu được phép) auto-install + re-resolve."""
    report = resolve(source, local_modules)
    if report.missing_imports:
        install_result = auto_install(report)
        if install_result.get("installed"):
            report = resolve(source, local_modules)
        return {"report": report, "install": install_result}
    return {"report": report, "install": {"skipped": "nothing missing"}}
