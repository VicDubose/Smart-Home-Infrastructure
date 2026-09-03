from pathlib import Path
import json

import requests
import yaml
from pydantic import ValidationError

from app.services.event_schema import EventAnalysis


ROOT = Path(
    "/mnt/appdata/ha-services/local-events"
)

CONFIG_PATH = (
    ROOT / "config/local-events.yaml"
)

PROMPT_PATH = Path(
    "/mnt/appdata/ai/workers/"
    "phi3-mini/prompts/event-classifier.txt"
)


class AIValidationError(RuntimeError):
    def __init__(
        self,
        message,
        raw_output=None,
    ):
        super().__init__(message)

        self.raw_output = raw_output


def load_config():
    with CONFIG_PATH.open(
        "r",
        encoding="utf-8",
    ) as handle:
        return yaml.safe_load(
            handle
        )


CONFIG = load_config()

OLLAMA_URL = (
    CONFIG["ai"]["base_url"].rstrip("/")
    + "/api/generate"
)

MODEL = CONFIG["ai"]["model"]

CONTEXT_SIZE = int(
    CONFIG["ai"].get(
        "context_size",
        4096,
    )
)

TEMPERATURE = float(
    CONFIG["ai"].get(
        "temperature",
        0.1,
    )
)

SYSTEM_PROMPT = (
    PROMPT_PATH.read_text(
        encoding="utf-8"
    )
)


def request_event_analysis(
    event: dict,
    keep_alive="10m",
):
    payload = {
        "model": MODEL,

        "system": SYSTEM_PROMPT,

        "prompt": (
            "Analyze this event and return "
            "only the required structured "
            "response:\n\n"
            + json.dumps(
                event,
                indent=2,
                ensure_ascii=False,
            )
        ),

        "stream": False,

        "format":
            EventAnalysis.model_json_schema(),

        "keep_alive": keep_alive,

        "options": {
            "temperature":
                TEMPERATURE,

            "num_ctx":
                CONTEXT_SIZE,
        },
    }

    response = requests.post(
        OLLAMA_URL,
        json=payload,
        timeout=180,
    )

    response.raise_for_status()

    result = response.json()

    raw_output = (
        result.get("response")
        or ""
    )

    try:
        analysis = (
            EventAnalysis.model_validate_json(
                raw_output
            )
        )

    except ValidationError as exc:
        raise AIValidationError(
            str(exc),
            raw_output=raw_output,
        ) from exc

    return (
        analysis,
        raw_output,
    )


def analyze_event(
    event: dict,
    keep_alive="10m",
) -> EventAnalysis:
    analysis, _ = (
        request_event_analysis(
            event,
            keep_alive=keep_alive,
        )
    )

    return analysis


def run_test():
    fake_event = {
        "title": (
            "MAGIC CITY ANIME + GAMING NIGHT!!! "
            "Presented by Example Promotions"
        ),

        "description": (
            "Cosplay contest, retro gaming tournament, "
            "anime vendors, ramen stand and local food "
            "trucks. All ages welcome. Free admission."
        ),

        "venue":
            "BJCC North Exhibition Hall",

        "city":
            "Birmingham",

        "state":
            "AL",

        "source":
            "TEST DATA",
    }

    print(
        "===== TEST EVENT ====="
    )

    print(
        json.dumps(
            fake_event,
            indent=2,
        )
    )

    print(
        "\n===== PHI-3 ANALYSIS ====="
    )

    result = analyze_event(
        fake_event,
        keep_alive=0,
    )

    print(
        json.dumps(
            result.model_dump(),
            indent=2,
        )
    )


if __name__ == "__main__":
    run_test()
