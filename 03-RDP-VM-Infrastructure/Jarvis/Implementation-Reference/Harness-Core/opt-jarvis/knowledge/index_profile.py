#!/usr/bin/env python3

import hashlib
import json
import sys
import urllib.request

sys.path.insert(
    0,
    "/opt/jarvis/harness",
)

from model_provider import JarvisModelProvider


PROFILE_SCHEMA = "jarvis_index_profile_v1"

CHUNKER_VERSION = "canonical-v1"
EMBEDDING_CONTRACT_VERSION = "jarvis-embedding-v1"

DEFAULT_CHUNK_SIZE = 1200
DEFAULT_OVERLAP = 200

EMBEDDING_CAPABILITY = "embeddings"


def canonical_json(data):
    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def sha256_text(text):
    return hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()


class JarvisIndexProfile:
    def __init__(self):
        self.provider = JarvisModelProvider()

    @staticmethod
    def _model_matches(
        inventory_name,
        requested_name,
    ):
        if inventory_name == requested_name:
            return True

        if (
            ":" not in requested_name
            and inventory_name
            == f"{requested_name}:latest"
        ):
            return True

        return False

    def _ollama_model_identity(
        self,
        route,
    ):
        endpoint = (
            route["endpoint"].rstrip("/")
            + "/api/tags"
        )

        with urllib.request.urlopen(
            endpoint,
            timeout=10,
        ) as response:
            data = json.load(response)

        matches = []

        for item in data.get(
            "models",
            [],
        ):
            name = (
                item.get("name")
                or item.get("model")
                or ""
            )

            if self._model_matches(
                name,
                route["model"],
            ):
                matches.append(item)

        if len(matches) != 1:
            raise RuntimeError(
                "Expected exactly one Ollama model "
                f"for {route['model']}; "
                f"found {len(matches)}"
            )

        item = matches[0]

        digest = item.get("digest")

        if not digest:
            raise RuntimeError(
                "Ollama model inventory missing digest"
            )

        details = item.get("details") or {}

        return {
            "requested_model":
                route["model"],
            "resolved_model":
                (
                    item.get("name")
                    or item.get("model")
                ),
            "digest":
                digest,
            "family":
                details.get("family"),
            "parameter_size":
                details.get("parameter_size"),
            "quantization":
                details.get(
                    "quantization_level"
                ),
        }

    def build(
        self,
        *,
        chunk_size=DEFAULT_CHUNK_SIZE,
        overlap=DEFAULT_OVERLAP,
    ):
        if chunk_size <= 0:
            raise ValueError(
                "chunk_size must be greater than zero"
            )

        if overlap < 0:
            raise ValueError(
                "overlap cannot be negative"
            )

        if overlap >= chunk_size:
            raise ValueError(
                "overlap must be smaller than chunk_size"
            )

        route = self.provider.resolve(
            EMBEDDING_CAPABILITY
        )

        if route.get("status") != "OK":
            raise RuntimeError(
                "Embedding capability unavailable: "
                f"{route.get('status')}"
            )

        if route.get(
            "provider_type"
        ) != "ollama":
            raise RuntimeError(
                "Unsupported embedding provider type: "
                f"{route.get('provider_type')}"
            )

        model = self._ollama_model_identity(
            route
        )

        #
        # Diagnostic profile:
        # includes routing information for observability.
        #
        profile = {
            "schema":
                PROFILE_SCHEMA,

            "chunker": {
                "version":
                    CHUNKER_VERSION,
                "chunk_size":
                    chunk_size,
                "overlap":
                    overlap,
            },

            "embedding": {
                "contract_version":
                    EMBEDDING_CONTRACT_VERSION,
                "capability":
                    EMBEDDING_CAPABILITY,
                "provider":
                    route["provider"],
                "provider_type":
                    route["provider_type"],
                "node":
                    route["node"],
                **model,
            },
        }

        #
        # Freshness material:
        #
        # Deliberately exclude provider and node.
        #
        # Moving the exact same embedding artifact
        # between SKYNET nodes must not require a
        # vector rebuild.
        #
        fingerprint_material = {
            "schema":
                PROFILE_SCHEMA,

            "chunker": {
                "version":
                    CHUNKER_VERSION,
                "chunk_size":
                    chunk_size,
                "overlap":
                    overlap,
            },

            "embedding": {
                "contract_version":
                    EMBEDDING_CONTRACT_VERSION,
                "provider_type":
                    route["provider_type"],
                "model":
                    model["resolved_model"],
                "digest":
                    model["digest"],
            },
        }

        fingerprint = sha256_text(
            canonical_json(
                fingerprint_material
            )
        )

        return {
            "profile":
                profile,
            "fingerprint_material":
                fingerprint_material,
            "fingerprint":
                fingerprint,
        }


def main():
    result = JarvisIndexProfile().build()

    print(
        json.dumps(
            result,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
