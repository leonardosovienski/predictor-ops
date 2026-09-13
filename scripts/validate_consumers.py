"""Linux-only controlled integration of pinned, real consumer distributions."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

REVISIONS = {
    "ecosystem-predictor": "6b236fc57fccc35ad50aff223f7cf21ec4ab1ae9",
    "cripto-predictor": "4c4d97ec9bfff185df089a6edb6da9ccd71f306f",
    "brasileirao-predictor": "5cc4125071761973cea37c2116b4a1a34b233eb7",
    "stocks-predictor": "3066321e599ee15dd0ace4167d2791545ce6eb95",
}


def run(*args, cwd=None, env=None):
    subprocess.run(args, cwd=cwd, env=env, check=True, timeout=300)


def main():
    if sys.platform != "linux":
        raise SystemExit("Consumer distribution builds are authorized here only on Linux CI")
    source = Path(__file__).resolve().parents[1]
    destination = Path(os.environ["CONSUMER_RECEIPT"]).resolve()
    with tempfile.TemporaryDirectory(prefix="ops-consumers-") as temporary:
        root = Path(temporary)
        wheels = root / "wheels"
        run("uv", "build", "--wheel", "--out-dir", str(wheels), cwd=source)
        manifest = {"consumers": {}, "shared": {}}
        for name, sha in REVISIONS.items():
            checkout = root / name
            run("git", "clone", "--no-checkout", f"https://github.com/leonardosovienski/{name}.git", str(checkout))
            run("git", "checkout", "--detach", sha, cwd=checkout)
            run("uv", "build", "--wheel", "--out-dir", str(wheels), cwd=checkout)
            version = tomllib.loads((checkout / "pyproject.toml").read_text())["project"]["version"]
            wheel = next(wheels.glob(f"{name.replace('-', '_')}-{version}-*.whl"))
            digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
            if name == "ecosystem-predictor":
                manifest["shared"][name] = {"version": version, "hash": "sha256:" + digest}
            else:
                manifest["consumers"][name] = {"version": version, "wheel_sha256": digest, "commit": sha}
        ops = next(wheels.glob("predictor_ops-*.whl"))
        manifest["shared"]["predictor-ops"] = {
            "version": tomllib.loads((source / "pyproject.toml").read_text())["project"]["version"],
            "hash": "sha256:" + hashlib.sha256(ops.read_bytes()).hexdigest(),
        }
        environment = root / "environment"
        run("uv", "venv", str(environment), "--python", "3.13", "--seed")
        python = environment / "bin/python"
        run(
            str(python),
            "-m",
            "pip",
            "install",
            "https://github.com/leonardosovienski/core-predictor/releases/download/v3.2.1/predictor_core-3.2.1-py3-none-any.whl",
            *(str(wheel) for wheel in wheels.glob("*.whl")),
        )
        check = root / "check_real_plugin_integration.py"
        shutil.copyfile(root / "ecosystem-predictor/scripts/check_real_plugin_integration.py", check)
        manifest_path = root / "manifest.json"
        manifest_path.write_text(json.dumps(manifest))
        env = os.environ.copy()
        env.update(CRIPTO_ROOT=str(root / "crypto-fixture"), COMPATIBILITY_RECEIPT=str(destination))
        run(str(python), str(check), "--manifest", str(manifest_path), cwd=root, env=env)
        receipt = json.loads(destination.read_text())
        receipt["source_revisions"] = REVISIONS
        receipt["ops_source"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
        destination.write_text(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
