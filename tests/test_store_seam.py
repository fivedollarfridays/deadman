"""Locks the zero-dependency seam the store is allowed to have.

``pyproject.toml`` declares ``dependencies = []`` and the test suite must run
with no cloud SDK present at all. That guarantee is one stray top-level
``from google.cloud import firestore`` away from being false, and the failure
would be invisible to anyone whose machine happens to have the SDK installed —
which is every machine that has ever deployed the service.

These tests fail on that import instead, statically, on every machine.
:mod:`deadman.diagnose.gemini` makes the same promise about the model SDK; the
store makes it about the storage SDK for the same reason.
"""

from __future__ import annotations

import ast
import importlib.util
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from deadman.store.firestore import FirestoreEvidenceStore, StoreSdkMissing

REPO_ROOT = Path(__file__).resolve().parents[1]
STORE_PACKAGE = REPO_ROOT / "src" / "deadman" / "store"

#: Every distribution the store may reach for, none of which may be imported
#: at module scope. Named rather than inferred so adding an SDK is a decision.
VENDOR_ROOTS = {"google", "firebase_admin"}


def _sdk_installed() -> bool:
    """``find_spec`` raises rather than returning ``None`` when a *parent*
    package is missing, which is the ordinary case here."""
    try:
        return importlib.util.find_spec("google.cloud.firestore") is not None
    except ModuleNotFoundError:
        return False


def _module_scope_imports(source: str) -> set[str]:
    """Root package names imported anywhere except inside a function body."""
    tree = ast.parse(source)
    deferred = {
        node
        for function in ast.walk(tree)
        if isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef)
        for node in ast.walk(function)
        if isinstance(node, ast.Import | ast.ImportFrom)
    }

    roots: set[str] = set()
    for node in ast.walk(tree):
        if node in deferred:
            continue
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            roots.add(node.module.split(".", 1)[0])
    return roots


@pytest.mark.parametrize("module", sorted(STORE_PACKAGE.glob("*.py")), ids=lambda p: p.name)
def test_no_store_module_imports_an_sdk_at_module_scope(module: Path) -> None:
    offenders = _module_scope_imports(module.read_text()) & VENDOR_ROOTS

    assert not offenders, (
        f"{module.name} imports {sorted(offenders)} at module scope; the SDK "
        f"belongs inside the constructor, as GeminiClient does"
    )


def test_the_deferred_import_is_actually_present_in_the_firestore_backend() -> None:
    """The negative test above would also pass on a backend that never reaches
    for the SDK at all, so prove the import exists and is merely deferred."""
    source = (STORE_PACKAGE / "firestore.py").read_text()

    assert "from google.cloud import firestore" in source
    assert "google" not in _module_scope_imports(source)


def test_importing_the_store_package_pulls_in_no_vendor_sdk() -> None:
    """The runtime half of the same claim, in a fresh interpreter.

    A module-scope import is the obvious way to break this; an import executed
    as a side effect of a class body or a default argument is the subtle one,
    and only running it catches that.
    """
    probe = (
        "import sys; import deadman.store; "
        f"leaked = sorted(m for m in sys.modules if m.split('.')[0] in {sorted(VENDOR_ROOTS)!r}); "
        "assert not leaked, leaked"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, cwd=REPO_ROOT
    )

    assert result.returncode == 0, result.stderr


def test_firestore_backend_refuses_to_construct_without_the_sdk() -> None:
    """Construction fails loudly; it does not degrade to a store that drops
    evidence. A monitor that discovers its storage is absent while recording
    an outage has become part of the outage."""
    if _sdk_installed():
        pytest.skip("the Firestore SDK is installed in this environment")

    with pytest.raises(StoreSdkMissing) as exc_info:
        FirestoreEvidenceStore(project="deadman-20260810")

    assert "deadman[firestore]" in str(exc_info.value)


def test_pyproject_keeps_zero_runtime_dependencies_and_puts_firestore_in_an_extra() -> None:
    config = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    project = config["project"]

    assert project["dependencies"] == []
    extra = project["optional-dependencies"]["firestore"]
    assert any("google-cloud-firestore" in requirement for requirement in extra)
    assert not any("google-cloud-firestore" in r for r in project["optional-dependencies"]["dev"])
