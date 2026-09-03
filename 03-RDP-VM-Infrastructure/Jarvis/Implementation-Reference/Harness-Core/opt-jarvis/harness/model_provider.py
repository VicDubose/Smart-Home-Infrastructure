#!/usr/bin/env python3

import argparse
import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path

import yaml


DEFAULT_CONFIG = Path(
    os.environ.get(
        "JARVIS_MODELS_CONFIG",
        "/opt/jarvis/config/models.yaml"
    )
)


class JarvisModelProvider:
    def __init__(self, config_path=DEFAULT_CONFIG):
        self.config_path = Path(config_path)
        self.config = self._load()

    def _load(self):
        if not self.config_path.is_file():
            raise RuntimeError(
                f"Model configuration missing: {self.config_path}"
            )

        with self.config_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            raise RuntimeError("Invalid models.yaml")

        if "providers" not in data:
            raise RuntimeError("models.yaml missing providers")

        if "capabilities" not in data:
            raise RuntimeError("models.yaml missing capabilities")

        return data

    def list_capabilities(self):
        result = {}

        for name, cap in self.config["capabilities"].items():
            result[name] = {
                "available": bool(cap.get("available", False)),
                "provider": cap.get("provider"),
                "purpose": cap.get("purpose"),
            }

        return result

    def resolve(self, capability):
        caps = self.config["capabilities"]

        if capability not in caps:
            return {
                "status": "UNKNOWN_CAPABILITY",
                "capability": capability,
            }

        cap = caps[capability]

        if not cap.get("available", False):
            return {
                "status": "CAPABILITY_UNAVAILABLE",
                "capability": capability,
                "purpose": cap.get("purpose"),
            }

        provider_name = cap.get("provider")
        model = cap.get("model")

        if not provider_name or not model:
            return {
                "status": "CAPABILITY_MISCONFIGURED",
                "capability": capability,
            }

        provider = self.config["providers"].get(provider_name)

        if not provider:
            return {
                "status": "PROVIDER_UNAVAILABLE",
                "capability": capability,
                "provider": provider_name,
            }

        return {
            "status": "OK",
            "capability": capability,
            "purpose": cap.get("purpose"),
            "provider": provider_name,
            "provider_type": provider.get("type"),
            "endpoint": provider.get("endpoint"),
            "node": provider.get("node"),
            "model": model,
        }

    def health(self, capability):
        resolved = self.resolve(capability)

        if resolved["status"] != "OK":
            return resolved

        if resolved["provider_type"] != "ollama":
            return {
                **resolved,
                "status": "HEALTHCHECK_UNSUPPORTED",
            }

        url = resolved["endpoint"].rstrip("/") + "/api/tags"

        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                data = json.load(response)
        except Exception as exc:
            return {
                **resolved,
                "status": "PROVIDER_OFFLINE",
                "error": str(exc),
            }

        requested = resolved["model"]

        installed = [
            m.get("name", "")
            for m in data.get("models", [])
        ]

        def normalized(name):
            return name if ":" in name else name + ":latest"

        found = normalized(requested) in {
            normalized(name) for name in installed
        }

        return {
            **resolved,
            "status": "HEALTHY" if found else "MODEL_NOT_INSTALLED",
            "model_installed": found,
        }


def emit(data):
    print(json.dumps(data, indent=2))


def main():
    parser = argparse.ArgumentParser(
        description="Jarvis model capability provider"
    )

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list")

    resolve = sub.add_parser("resolve")
    resolve.add_argument("capability")

    health = sub.add_parser("health")
    health.add_argument("capability")

    args = parser.parse_args()

    try:
        provider = JarvisModelProvider()

        if args.command == "list":
            emit(provider.list_capabilities())
            return 0

        if args.command == "resolve":
            result = provider.resolve(args.capability)
            emit(result)
            return 0 if result["status"] == "OK" else 2

        if args.command == "health":
            result = provider.health(args.capability)
            emit(result)
            return 0 if result["status"] == "HEALTHY" else 3

    except Exception as exc:
        emit({
            "status": "JARVIS_PROVIDER_ERROR",
            "error": str(exc),
        })
        return 10


if __name__ == "__main__":
    sys.exit(main())
