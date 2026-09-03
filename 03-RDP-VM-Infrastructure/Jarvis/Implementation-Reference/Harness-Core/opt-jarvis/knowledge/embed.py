#!/usr/bin/env python3

import argparse
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, "/opt/jarvis/harness")

from model_provider import JarvisModelProvider


CAPABILITY = "embeddings"


class JarvisEmbeddingService:
    def __init__(self):
        self.provider = JarvisModelProvider()

    def embed(self, text):
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Embedding input must be non-empty text")

        route = self.provider.resolve(CAPABILITY)

        if route["status"] != "OK":
            raise RuntimeError(
                f"Embedding capability unavailable: {route['status']}"
            )

        if route["provider_type"] != "ollama":
            raise RuntimeError(
                f"Unsupported embedding provider: "
                f"{route['provider_type']}"
            )

        endpoint = route["endpoint"].rstrip("/") + "/api/embed"

        payload = json.dumps({
            "model": route["model"],
            "input": text
        }).encode("utf-8")

        request = urllib.request.Request(
            endpoint,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=60
            ) as response:
                result = json.load(response)

        except Exception as exc:
            raise RuntimeError(
                f"Embedding provider request failed: {exc}"
            ) from exc

        vectors = result.get("embeddings", [])

        if not vectors:
            raise RuntimeError(
                "Embedding provider returned no vectors"
            )

        vector = vectors[0]

        return {
            "status": "OK",
            "capability": CAPABILITY,
            "provider": route["provider"],
            "node": route["node"],
            "model": route["model"],
            "dimensions": len(vector),
            "vector": vector,
        }


def main():
    parser = argparse.ArgumentParser(
        description="Jarvis knowledge embedding service"
    )

    parser.add_argument(
        "text",
        help="Text to convert into an embedding"
    )

    parser.add_argument(
        "--metadata-only",
        action="store_true",
        help="Do not print the full embedding vector"
    )

    args = parser.parse_args()

    try:
        service = JarvisEmbeddingService()
        result = service.embed(args.text)

        if args.metadata_only:
            result.pop("vector", None)

        print(json.dumps(result, indent=2))
        return 0

    except Exception as exc:
        print(json.dumps({
            "status": "EMBEDDING_ERROR",
            "error": str(exc)
        }, indent=2))

        return 1


if __name__ == "__main__":
    sys.exit(main())
