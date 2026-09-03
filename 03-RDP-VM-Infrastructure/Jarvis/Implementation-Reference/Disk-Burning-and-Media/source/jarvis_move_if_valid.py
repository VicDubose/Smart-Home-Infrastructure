#!/usr/bin/env python3

import argparse
import json
import shutil
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Move ripped files only if Jarvis validation passed.")
    parser.add_argument("--validation", required=True)
    parser.add_argument("--destination", required=True)
    args = parser.parse_args()

    validation_path = Path(args.validation)
    destination = Path(args.destination)

    if not validation_path.exists():
        print(f"ERROR: Validation file not found: {validation_path}")
        raise SystemExit(1)

    data = json.loads(validation_path.read_text())

    technical_result = data.get("technical_result")
    final_result = data.get("final_result", technical_result)
    ai_review = data.get("ai_review") or {}
    ai_result = ai_review.get("ai_result", "NOT_USED")

    print("===== JARVIS MOVE GATE =====")
    print(f"Technical result: {technical_result}")
    print(f"AI result: {ai_result}")
    print(f"Final result: {final_result}")
    print("")

    if final_result != "PASS":
        print("===== MOVE BLOCKED =====")
        print("Validation did not fully pass. Files were NOT moved.")
        raise SystemExit(1)

    destination.mkdir(parents=True, exist_ok=True)

    print("===== MOVE APPROVED =====")

    for item in data.get("checks", []):
        src = Path(item["file"])

        if item.get("status") != "PASS":
            print(f"Skipping non-pass item: {src}")
            continue

        if item.get("classification") != "LIKELY_EPISODE":
            print(f"Skipping non-episode item: {src}")
            continue

        if not src.exists():
            print(f"Missing source file, skipping: {src}")
            continue

        dest = destination / src.name

        if dest.exists():
            print(f"Duplicate detected, NOT overwriting: {dest}")
            continue

        print(f"Moving: {src} -> {dest}")
        shutil.move(str(src), str(dest))

    print("")
    print("===== FINAL JELLYFIN FOLDER =====")
    for file in sorted(destination.glob("*.mkv")):
        print(file.name)


if __name__ == "__main__":
    main()
