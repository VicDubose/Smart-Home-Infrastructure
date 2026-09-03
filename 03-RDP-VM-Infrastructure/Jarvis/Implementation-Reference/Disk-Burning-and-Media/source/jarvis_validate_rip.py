#!/usr/bin/env python3

import argparse
import json
import re
import statistics
import subprocess
import urllib.request
from pathlib import Path

DEFAULT_MIN_EPISODE_SECONDS = 35 * 60
DEFAULT_MAX_EPISODE_SECONDS = 58 * 60
MIN_EPISODE_SIZE_MB = 150
RELATIVE_RUNTIME_DRIFT_SECONDS = 5 * 60


def run_cmd(cmd, input_text=None):
    result = subprocess.run(
        cmd,
        input=input_text,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    return result.stdout.strip()


def get_duration_seconds(file_path):
    output = run_cmd([
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        str(file_path),
    ])

    try:
        data = json.loads(output)
        return float(data["format"]["duration"])
    except Exception:
        return None


def human_time(seconds):
    if seconds is None:
        return "UNKNOWN"
    return f"{int(seconds // 60)}m {int(seconds % 60)}s"


def ollama_review(model, result):
    prompt = f"""
You are Jarvis Media Validator.

Review the supplied DVD episode validation evidence.

Return JSON only with:
{{
  "ai_result": "PASS or REVIEW",
  "reason": "short explanation",
  "concerns": ["concern"]
}}

Rules:
- PASS only when every expected episode exists and technical validation passed.
- REVIEW any missing, unreadable, truncated, anomalous, or technically flagged file.
- Never invent episodes or approve a technical REVIEW.

Validation data:
{json.dumps(result, indent=2)}
"""

    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0
        }
    }).encode("utf-8")

    request = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            envelope = json.loads(response.read().decode("utf-8"))

        raw = envelope.get("response", "").strip()
        parsed = json.loads(raw)

        if parsed.get("ai_result") not in {"PASS", "REVIEW"}:
            raise ValueError("AI returned an unsupported result.")

        concerns = parsed.get("concerns")
        if not isinstance(concerns, list):
            parsed["concerns"] = []

        return parsed

    except Exception as exc:
        return {
            "ai_result": "REVIEW",
            "reason": f"Phi-3 Mini review failed safely: {exc}",
            "concerns": ["ai_api_or_json_failure"],
        }


def main():
    parser = argparse.ArgumentParser(description="Jarvis V4 post-rip validation with relative runtime anomaly detection.")
    parser.add_argument("--show", required=True)
    parser.add_argument("--season", required=True, type=int)
    parser.add_argument("--start", required=True, type=int)
    parser.add_argument("--end", required=True, type=int)
    parser.add_argument("--staging", default=str(Path.home() / "rips/staging"))
    parser.add_argument("--write-result", default=str(Path.home() / "rips/staging/validation_result.json"))
    parser.add_argument("--ai", default=None)
    parser.add_argument("--min-runtime", type=int, default=35, help="Minimum episode runtime in minutes. Default: 35")
    parser.add_argument("--max-runtime", type=int, default=58, help="Maximum episode runtime in minutes. Default: 58")
    args = parser.parse_args()

    short_episode_shows = {
        "danny phantom",
        "avatar the last airbender",
        "spongebob squarepants",
        "fairly oddparents",
        "the fairly oddparents",
        "the boondocks",
        "hogan's heroes",
        "hogans heroes",
        "batman beyond",
    }

    normalized_show = args.show.strip().lower()
    is_short_episode_show = normalized_show in short_episode_shows

    if is_short_episode_show and args.min_runtime == 35 and args.max_runtime == 58:
        args.min_runtime = 18
        args.max_runtime = 30

    min_episode_seconds = args.min_runtime * 60
    max_episode_seconds = args.max_runtime * 60
    min_episode_size_mb = 75 if is_short_episode_show else MIN_EPISODE_SIZE_MB

    staging = Path(args.staging)
    result_path = Path(args.write_result)

    checks = []

    print("===== JARVIS V4 RIP VALIDATION =====")
    print(f"Show: {args.show}")
    print(f"Season: {args.season:02d}")
    print(f"Expected episodes: S{args.season:02d}E{args.start:02d} - S{args.season:02d}E{args.end:02d}")
    print(f"Staging: {staging}")
    print(f"Runtime rules: {args.min_runtime}m - {args.max_runtime}m")
    print("")

    for ep in range(args.start, args.end + 1):
        file_name = f"{args.show} - S{args.season:02d}E{ep:02d}.mkv"
        file_path = staging / file_name

        item = {
            "episode": f"S{args.season:02d}E{ep:02d}",
            "file_name": file_name,
            "file": str(file_path),
            "exists": file_path.exists(),
            "size_mb": None,
            "duration_seconds": None,
            "duration_human": None,
            "status": "UNKNOWN",
            "classification": "UNKNOWN",
            "warnings": [],
            "rerip_recommended": False,
        }

        print(f"Checking {file_name}")

        if not file_path.exists():
            item["status"] = "FAIL"
            item["classification"] = "MISSING"
            item["warnings"].append("missing_file")
            item["rerip_recommended"] = True
            print("  ❌ Missing file")
            checks.append(item)
            continue

        size_mb = file_path.stat().st_size / (1024 ** 2)
        duration = get_duration_seconds(file_path)

        item["size_mb"] = round(size_mb, 2)
        item["duration_seconds"] = duration
        item["duration_human"] = human_time(duration)

        print(f"  Size: {size_mb:.2f} MB")
        print(f"  Runtime: {human_time(duration)}")

        if size_mb < min_episode_size_mb:
            item["warnings"].append("file_too_small_for_episode")
            item["rerip_recommended"] = True

        if duration is None:
            item["classification"] = "UNREADABLE_RUNTIME"
            item["warnings"].append("runtime_unreadable")
            item["rerip_recommended"] = True
        elif duration < min_episode_seconds:
            item["classification"] = "EXTRA_OR_PREVIEW_OR_TRUNCATED"
            item["warnings"].append("runtime_too_short_for_episode")
            item["rerip_recommended"] = True
        elif duration > max_episode_seconds:
            item["classification"] = "POSSIBLE_PLAY_ALL_OR_MULTI_EPISODE"
            item["warnings"].append("runtime_too_long_for_single_episode")
            item["rerip_recommended"] = True
        else:
            item["classification"] = "LIKELY_EPISODE"

        checks.append(item)
        print("")

    # Relative consistency check:
    # If the batch normally lands around 42 minutes and one file is much shorter,
    # flag it even if it technically passed the default min-runtime rule.
    good_durations = [
        item["duration_seconds"]
        for item in checks
        if item["duration_seconds"] is not None
        and min_episode_seconds <= item["duration_seconds"] <= max_episode_seconds
    ]

    batch_median = None
    if len(good_durations) >= 3:
        batch_median = statistics.median(good_durations)

        for item in checks:
            duration = item["duration_seconds"]
            if duration is None:
                continue

            if item["classification"] == "LIKELY_EPISODE":
                drift = batch_median - duration

                if drift > RELATIVE_RUNTIME_DRIFT_SECONDS:
                    item["warnings"].append("runtime_much_shorter_than_batch_median")
                    item["classification"] = "POSSIBLE_TRUNCATED_EPISODE"
                    item["rerip_recommended"] = True

    all_good = True

    print("===== CONSISTENCY REVIEW =====")
    if batch_median:
        print(f"Batch median runtime: {human_time(batch_median)}")
    else:
        print("Batch median runtime: not enough comparable files")
    print("")

    for item in checks:
        if item["warnings"]:
            item["status"] = "REVIEW"
            all_good = False
            print(f"⚠️ {item['episode']} REVIEW")
            print(f"   Runtime: {item['duration_human']}")
            print(f"   Classification: {item['classification']}")
            print(f"   Warnings: {', '.join(item['warnings'])}")
            if item["rerip_recommended"]:
                print("   Action: RERIP RECOMMENDED")
        else:
            item["status"] = "PASS"
            item["classification"] = "LIKELY_EPISODE"
            print(f"✅ {item['episode']} PASS - {item['duration_human']}")

    technical_result = "PASS" if all_good else "REVIEW"

    result = {
        "show": args.show,
        "season": args.season,
        "expected_start": args.start,
        "expected_end": args.end,
        "staging": str(staging),
        "technical_result": technical_result,
        "ai_model": args.ai,
        "ai_review": None,
        "final_result": technical_result,
        "rules": {
            "min_episode_seconds": min_episode_seconds,
            "max_episode_seconds": max_episode_seconds,
            "min_episode_size_mb": min_episode_size_mb,
            "relative_runtime_drift_seconds": RELATIVE_RUNTIME_DRIFT_SECONDS,
            "batch_median_runtime_seconds": batch_median,
        },
        "checks": checks,
        "rerip_recommended": any(item["rerip_recommended"] for item in checks),
        "rerip_candidates": [
            item for item in checks if item["rerip_recommended"]
        ],
    }

    print("")
    print("===== TECHNICAL RESULT =====")
    print(f"Technical validation: {technical_result}")

    if args.ai:
        print("")
        print(f"===== AI REVIEW USING {args.ai} =====")
        ai_review = ollama_review(args.ai, result)
        result["ai_review"] = ai_review

        ai_result = ai_review.get("ai_result", "REVIEW")
        result["final_result"] = "PASS" if technical_result == "PASS" and ai_result == "PASS" else "REVIEW"

        print(f"AI result: {ai_result}")
        print(f"Reason: {ai_review.get('reason')}")

        concerns = ai_review.get("concerns", [])
        if concerns:
            print("Concerns:")
            for concern in concerns:
                print(f"  - {concern}")
    else:
        result["final_result"] = technical_result

    result_path.write_text(json.dumps(result, indent=2))

    print("")
    print("===== FINAL RESULT =====")
    print(f"Final validation: {result['final_result']}")
    print(f"Result file: {result_path}")

    if result["final_result"] != "PASS":
        print("")
        print("MOVE BLOCKED: One or more checks require review.")
        if result["rerip_recommended"]:
            print("RERIP RECOMMENDED for:")
            for item in result["rerip_candidates"]:
                print(f"  - {item['episode']} ({item['duration_human']}): {', '.join(item['warnings'])}")


if __name__ == "__main__":
    main()
