"""Benchmark exact cumulative mask intersection. Run from the repository root."""
from argparse import ArgumentParser
from importlib.metadata import version
import json
from pathlib import Path
import platform
from statistics import median
import sys
from tempfile import TemporaryDirectory
from time import perf_counter_ns

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from exposure import ExposureHistory


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=int, default=25)
    parser.add_argument("--sizes", type=int, nargs="+", default=[256, 1024, 2048])
    args = parser.parse_args()
    if args.trials < 1 or any(size < 2 or size > 2300 for size in args.sizes):
        parser.error("Specify positive trials and page widths from 2 through 2300.")
    results = []
    for size in args.sizes:
        manifest = {"pages": [[size, size]], "source_sha256": "a" * 64, "profile": "benchmark"}
        request = {"audience": "Reviewer"}
        half = size // 2
        first = [[0, 0, 0, half, size]]
        proposed = [[0, 0, 0, size, half]]
        samples = []
        with TemporaryDirectory() as directory:
            history = ExposureHistory(Path(directory) / "history.db", bytes(32))
            history.evaluate(manifest, request, first, record=True)
            for _ in range(args.trials):
                start = perf_counter_ns()
                report = history.evaluate(manifest, request, proposed)
                samples.append((perf_counter_ns() - start) / 1e6)
                assert report["pages"][0]["hidden_across_releases"] == half ** 2
        results.append({"width": size, "height": size, "trials": args.trials,
                        "median_ms": median(samples), "samples_ms": samples})
    print(json.dumps({"platform": platform.platform(), "python": platform.python_version(),
                      "numpy": version("numpy"), "cryptography": version("cryptography"),
                      "results": results}, indent=2))


if __name__ == "__main__":
    main()
