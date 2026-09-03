#!/usr/bin/env python3
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


SYSTEM_RULES = """
You are Jarvis AI Review Agent.

You review media/server pipeline results and return STRICT JSON only.
Do not use markdown.
Do not include explanation outside JSON.

Allowed final_result values:
- PASS
- REVIEW
- BLOCK

Use PASS only when the technical result is clean and no obvious risk exists.
Use REVIEW when something may be okay but needs human confirmation.
Use BLOCK when files should not be moved or automation should stop.

Return exactly this JSON structure:
{
  "final_result": "PASS|REVIEW|BLOCK",
  "confidence": 0.0,
  "summary": "short human-readable summary",
  "concerns": [],
  "recommended_next_action": "short next action",
  "safe_to_move": true
}
"""


def run_ollama(model: str, prompt: str, timeout: int = 180) -> str:
    cmd = ["ollama", "run", model, prompt]
    result = subprocess.run(
        cmd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "ollama failed")
    return result.stdout.strip()



def sanitize_ai_text(text: str) -> str:
    # Remove ANSI escape sequences like \x1b[1D, \x1b[K, color codes, cursor controls
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)

    # Remove remaining control chars except normal whitespace
    text = "".join(
        ch for ch in text
        if ch in "\n\r\t" or ord(ch) >= 32
    )

    # Remove accidental line breaks inside obvious JSON string values caused by terminal edits
    text = text.replace("\r", "")
    return text


def extract_json(text: str) -> dict:
    text = sanitize_ai_text(text).strip()

    # Direct JSON
    try:
        return json.loads(text)
    except Exception:
        pass

    # Salvage JSON object if model added junk
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start:end + 1]
        return json.loads(candidate)

    raise ValueError("No valid JSON object found in AI response")


def normalize_review(data: dict) -> dict:
    result = str(data.get("final_result", "REVIEW")).upper().strip()
    if result not in {"PASS", "REVIEW", "BLOCK"}:
        result = "REVIEW"

    confidence = data.get("confidence", 0.0)
    try:
        confidence = float(confidence)
    except Exception:
        confidence = 0.0

    concerns = data.get("concerns", [])
    if not isinstance(concerns, list):
        concerns = [str(concerns)]

    safe_to_move = data.get("safe_to_move", result == "PASS")
    safe_to_move = bool(safe_to_move) and result == "PASS"

    return {
        "final_result": result,
        "confidence": max(0.0, min(1.0, confidence)),
        "summary": str(data.get("summary", "")).strip(),
        "concerns": concerns,
        "recommended_next_action": str(data.get("recommended_next_action", "")).strip(),
        "safe_to_move": safe_to_move,
    }


def fallback_review(payload: dict, error: str, raw_ai: str = "") -> dict:
    technical = str(payload.get("technical_result", "")).upper()
    final = str(payload.get("final_validation", "")).upper()

    if technical == "PASS" or final == "PASS":
        result = "REVIEW"
        safe = False
        summary = "Technical checks appear positive, but AI JSON review failed."
    else:
        result = "BLOCK"
        safe = False
        summary = "AI review failed and technical result was not clearly PASS."

    return {
        "final_result": result,
        "confidence": 0.25,
        "summary": summary,
        "concerns": ["ai_json_parse_failure", error],
        "recommended_next_action": "Human review recommended before moving files.",
        "safe_to_move": safe,
        "raw_ai_response": sanitize_ai_text(raw_ai)[:1000],
    }


def main():
    parser = argparse.ArgumentParser(description="Jarvis shared AI review agent")
    parser.add_argument("--input", required=True, help="JSON input/report file")
    parser.add_argument("--output", required=True, help="JSON output review file")
    parser.add_argument("--ai", default="llama3:8b", help="Ollama model")
    parser.add_argument("--context", default="media_validation", help="Review context label")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    payload = json.loads(input_path.read_text())

    prompt = (
        SYSTEM_RULES
        + "\n\nContext:\n"
        + args.context
        + "\n\nPipeline report JSON:\n"
        + json.dumps(payload, indent=2)
    )

    print("===== JARVIS AI REVIEW AGENT =====")
    print(f"Input: {input_path}")
    print(f"Output: {output_path}")
    print(f"Model: {args.ai}")
    print(f"Context: {args.context}")

    raw = ""
    try:
        raw = run_ollama(args.ai, prompt)
        review = normalize_review(extract_json(raw))
    except Exception as e:
        review = fallback_review(payload, str(e), raw)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(review, indent=2))

    print("")
    print("===== AI REVIEW RESULT =====")
    print(json.dumps(review, indent=2))

    if review["final_result"] == "BLOCK":
        sys.exit(2)
    if review["final_result"] == "REVIEW":
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
