"""Isolated import probe used by :mod:`core_provenance`.

Kept as a real module so syntax and behavior can be tested independently of
the subprocess launcher.
"""
from __future__ import annotations

import importlib
import json
import os
import runpy
import sys


def main() -> int:
    request = json.loads(os.environ["CORE_PROVENANCE_REQUEST"])
    consumer_root = request["consumer_root"]
    vendor_root = request["vendor_root"]
    mode = request["mode"]
    if mode == "vendor":
        sys.path.insert(0, os.path.dirname(vendor_root))
    elif mode in {"script", "module"}:
        sys.path.insert(0, consumer_root)

    run_error = None
    exit_code = None
    try:
        if mode == "script":
            sys.argv = [request["script"], "--help"]
            runpy.run_path(request["script"], run_name="__main__")
        elif mode == "module":
            sys.argv = [request["module"], "--help"]
            runpy.run_module(request["module"], run_name="__main__")
        else:
            importlib.import_module("predictor_core")
    except SystemExit as exc:
        exit_code = int(exc.code) if isinstance(exc.code, int) else 1
    except BaseException as exc:
        run_error = f"{type(exc).__name__}: {exc}"

    module = sys.modules.get("predictor_core")
    print(json.dumps({
        "run_error": run_error,
        "entrypoint_exit_code": exit_code,
        "module_file": getattr(module, "__file__", None),
        "sys_path": sys.path,
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
