"""POST every case in the public sample pack and check response shape."""

import argparse
import json
import urllib.error
import urllib.request


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("sample_pack", help="Path to the public sample JSON pack")
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()
    with open(args.sample_pack, encoding="utf-8") as sample_file:
        pack = json.load(sample_file)
    for case in pack["cases"]:
        body = json.dumps(case["input"]).encode()
        request = urllib.request.Request(
            f"{args.base_url.rstrip('/')}/optimize-energy",
            data=body,
            headers={"content-type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                result = json.load(response)
        except urllib.error.HTTPError as exc:
            raise SystemExit(f"{case['id']}: HTTP {exc.code}: {exc.read().decode()}") from exc
        assert result["scenario_id"] == case["input"]["scenario_id"]
        assert len(result["directive_interpretation"]) == len(case["input"]["operator_notes"])
        assert len(result["hourly_plan"]) == 24
        print(f"{case['id']}: ok")


if __name__ == "__main__":
    main()