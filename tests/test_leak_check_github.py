"""scripts/leak-check-github.sh against a stub `gh`: no network, no real terms."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "leak-check-github.sh"
TERM = "Zorblax"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")

STUB = r"""#!/usr/bin/env bash
# api [--paginate] <endpoint> --jq <filter>: print $STUB_DIR/<name>.tsv if it exists.
endpoint=""
for a in "$@"; do
  case "$a" in repos/*) endpoint="$a"; break ;; esac
done
name="${endpoint#repos/\{owner\}/\{repo\}}"
name="${name%%\?*}"
name="$(printf '%s' "$name" | tr '/' '_')"
[ -z "$name" ] && name="repo"
if [ -f "$STUB_DIR/fail" ] && grep -qx -- "$name" "$STUB_DIR/fail"; then
  exit 1
fi
[ -f "$STUB_DIR/$name.tsv" ] && cat "$STUB_DIR/$name.tsv"
exit 0
"""

CLEAN = {
    "_pulls": "12\tAdd a thing\tA body\tfeature/thing\n5\tOther\t\tfix/other\n7\tThird\tx\ty",
    "_pulls_12_reviews": "12\tLooks good",
    "_pulls_comments": "7\tnit: rename",
    "_issues": "3\tAn issue\tdetails",
    "_issues_comments": "3\tthanks",
    "_comments": "abcdef123456\tfine",
    "repo": "repo\tA scoring tool\tsales leads\t",
}


@pytest.fixture
def env(tmp_path):
    bin_dir = tmp_path / "bin"
    stub_dir = tmp_path / "stub"
    bin_dir.mkdir()
    stub_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(STUB)
    gh.chmod(0o755)
    e = dict(os.environ)
    e["PATH"] = f"{bin_dir}{os.pathsep}{e['PATH']}"
    e["STUB_DIR"] = str(stub_dir)
    e["LEAK_TERMS"] = TERM
    return tmp_path, stub_dir, e


def write(stub_dir, files):
    for name, text in files.items():
        (stub_dir / f"{name}.tsv").write_text(text + "\n")


def run(tmp_path, e):
    return subprocess.run(
        ["bash", str(SCRIPT)], cwd=tmp_path, env=e, capture_output=True, text=True, check=False
    )


def test_clean(env):
    tmp_path, stub_dir, e = env
    write(stub_dir, CLEAN)
    r = run(tmp_path, e)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "GitHub text check passed" in r.stdout
    assert "3 PRs" in r.stdout


def test_hits(env):
    tmp_path, stub_dir, e = env
    files = dict(CLEAN)
    files["_pulls"] = f"12\tAdd a thing\tmentions {TERM}\tfeature/thing\n5\tOther\t\t{TERM.upper()}/x\n7\tThird\tx\ty"
    files["_pulls_comments"] = f"7\t{TERM} here"
    files["_issues_comments"] = f"3\tsee {TERM}"
    files["repo"] = f"repo\t{TERM} tool\t\t"
    write(stub_dir, files)
    r = run(tmp_path, e)
    out = r.stdout + r.stderr
    assert r.returncode == 1
    for needle in ("#12", "#5", "#7", "#3", "repository"):
        assert needle in out
    assert TERM.lower() not in out.lower()
    assert "passed" not in out


def test_gh_failure_is_not_a_pass(env):
    tmp_path, stub_dir, e = env
    write(stub_dir, CLEAN)
    (stub_dir / "fail").write_text("_issues_comments\n")
    r = run(tmp_path, e)
    assert r.returncode == 2
    assert "Could not read comment on from GitHub." in r.stdout


def test_no_terms_warns(env):
    tmp_path, _stub_dir, e = env
    e["LEAK_TERMS"] = ""
    r = run(tmp_path, e)
    assert r.returncode == 0
    assert "::warning::" in r.stdout
