from pathlib import Path

import yaml


ROOT = Path("/mnt/appdata/ha-services/local-events")
SOURCE_CONFIG = ROOT / "config/sources.yaml"


def load_sources(enabled_only=True):
    with SOURCE_CONFIG.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    sources = data.get("sources", [])

    if enabled_only:
        sources = [
            source
            for source in sources
            if source.get("enabled", True)
        ]

    return sources


def get_source(source_id):
    for source in load_sources(enabled_only=False):
        if source["id"] == source_id:
            return source

    raise KeyError(f"Unknown source: {source_id}")


if __name__ == "__main__":
    for source in load_sources():
        print(
            f"{source['id']:20} "
            f"{source['collector']:18} "
            f"{source['name']}"
        )
