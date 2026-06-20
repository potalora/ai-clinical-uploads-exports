"""Generate synthetic FHIR R4 fixtures with Synthea (WS-E).

Synthea output is **synthetic** — safe as a shareable test corpus (no real PHI,
so it does not fall under the "never commit user fixtures" rule). The generated
bundles are large, so the output dir is gitignored; regenerate on demand.

Usage::

    python backend/scripts/generate_synthea_fixtures.py [-p N] [-s SEED]

Requires Java (``brew install openjdk``) and the Synthea jar at
``backend/tools/synthea-with-dependencies.jar`` (download
``synthea-with-dependencies.jar`` from the Synthea releases page). The jar and
output are gitignored.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
JAR = BACKEND / "tools" / "synthea-with-dependencies.jar"
OUT = BACKEND / "tests" / "fixtures" / "synthea"

# Homebrew installs OpenJDK keg-only; check the standard symlink path too.
_JAVA_CANDIDATES = ("java", "/opt/homebrew/opt/openjdk/bin/java")


def _java() -> str:
    for cand in _JAVA_CANDIDATES:
        if shutil.which(cand) or Path(cand).exists():
            return cand
    sys.exit("Java not found. Install with: brew install openjdk")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Synthea FHIR R4 fixtures.")
    parser.add_argument("-p", "--population", type=int, default=3, help="number of living patients")
    parser.add_argument("-s", "--seed", type=int, default=20260620, help="RNG seed (reproducible)")
    args = parser.parse_args()

    if not JAR.exists():
        sys.exit(
            f"Synthea jar missing: {JAR}\n"
            "Download synthea-with-dependencies.jar from the Synthea releases page "
            "into backend/tools/."
        )

    OUT.mkdir(parents=True, exist_ok=True)
    cmd = [
        _java(),
        "-jar",
        str(JAR),
        "-p",
        str(args.population),
        "-s",
        str(args.seed),
        f"--exporter.baseDirectory={OUT}/",
        "--exporter.fhir.export=true",
        "--exporter.hospital.fhir.export=false",
        "--exporter.practitioner.fhir.export=false",
    ]
    print("Running:", " ".join(cmd))
    result = subprocess.run(cmd, check=False)
    if result.returncode == 0:
        print(f"\nFHIR bundles written under: {OUT / 'fhir'}")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
