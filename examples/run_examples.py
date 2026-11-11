"""Check the exit code and exact output of each example in checks.json."""

import json
from pathlib import Path
import subprocess
import sys


def main():
    root = Path(__file__).resolve().parents[1]
    checks = json.loads((root / "checks.json").read_text(encoding="utf-8"))
    for check in checks:
        result = subprocess.run(
            [sys.executable, "-I", *check["args"]],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
        )
        stdout = ""
        if "report" in check:
            stdout = json.dumps(check["report"], separators=(",", ":")) + "\n"
        actual = (result.returncode, result.stdout, result.stderr)
        expected = (check["exit"], stdout, check.get("stderr", ""))
        if actual != expected:
            raise SystemExit(f"FAIL {check['name']}\nexpected {expected!r}\nactual   {actual!r}")
        print(f"PASS {check['name']} (exit {check['exit']})")


if __name__ == "__main__":
    main()
