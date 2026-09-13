"""Download and exercise the actual published wheel; never rebuild it."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path


def main():
    url = sys.argv[1]
    if not url.endswith(".whl"):
        url += "/predictor_ops-" + url.rsplit("/", 1)[1].removeprefix("v") + "-py3-none-any.whl"
    with tempfile.TemporaryDirectory(prefix="ops-published-") as directory:
        root = Path(directory)
        wheel = root / url.rsplit("/", 1)[1]
        urllib.request.urlretrieve(url, wheel)
        digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
        env = root / "environment"
        subprocess.run(["uv", "venv", str(env), "--python", sys.executable], check=True)
        python = env / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        subprocess.run(["uv", "pip", "install", "--python", str(python), str(wheel)], check=True)
        script = root / "validate_installed.py"
        shutil.copyfile(Path(__file__).with_name("validate_installed.py"), script)
        subprocess.run([str(python), str(script)], cwd=root, check=True, timeout=120)
        print(json.dumps({"published_url": url, "sha256": digest, "python": sys.version, "status": "VALIDADO"}))


if __name__ == "__main__":
    main()
