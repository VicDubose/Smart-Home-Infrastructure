#!/usr/bin/env python3

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, "/opt/jarvis/knowledge")

from chunk import chunk_text


INPUT_SCHEMA = "normalized_document_v1"
OUTPUT_SCHEMA = "jarvis_knowledge_chunk_set_v1"
CHUNK_SCHEMA = "jarvis_knowledge_chunk_v1"


def sha256_text(text):
    return hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()


def validate_document(document):
    if not isinstance(document, dict):
        raise ValueError(
            "Normalized document must be an object"
        )

    if document.get("schema") != INPUT_SCHEMA:
        raise ValueError(
            f"Expected {INPUT_SCHEMA}, "
            f"got {document.get('schema')}"
        )

    required = [
        "document_id",
        "source",
        "source_type",
        "source_ref",
        "content",
        "content_hash",
        "document_type",
        "provenance",
    ]

    missing = [
        field
        for field in required
        if field not in document
    ]

    if missing:
        raise ValueError(
            f"Document missing fields: {missing}"
        )


def chunk_document(
    document,
    *,
    chunk_size=1200,
    overlap=200,
):
    validate_document(document)

    domain = document.get("domain") or "general"

    base_chunks = chunk_text(
        document["content"],
        source=document["document_id"],
        domain=domain,
        document_type=document["document_type"],
        chunk_size=chunk_size,
        overlap=overlap,
    )

    chunks = []

    for base in base_chunks:
        text = base["text"]

        start_char = base["start_char"]
        end_char = base["end_char"]

        canonical_slice = document["content"][
            start_char:end_char
        ]

        if text != canonical_slice:
            raise RuntimeError(
                "Chunk coordinate invariant failed: "
                f"chunk {base['index']} does not match "
                "canonical document content"
            )

        chunk = {
            "schema": CHUNK_SCHEMA,

            "chunk_id": base["chunk_id"],
            "chunk_hash": sha256_text(text),

            "document_id": document["document_id"],
            "parent_content_hash": document["content_hash"],

            "source": document["source"],
            "source_type": document["source_type"],
            "source_ref": document["source_ref"],

            "domain": document.get("domain"),
            "document_type": document["document_type"],
            "title": document.get("title"),

            "index": base["index"],
            "start_char": base["start_char"],
            "end_char": base["end_char"],
            "text": text,

            "authority": document.get(
                "authority",
                {}
            ),

            "provenance": document["provenance"],

            "metadata": {
                **document.get("metadata", {}),
                "parent_schema": INPUT_SCHEMA,
            },
        }

        chunks.append(chunk)

    return {
        "status": "OK",
        "schema": OUTPUT_SCHEMA,
        "document_id": document["document_id"],
        "source": document["source"],
        "source_ref": document["source_ref"],
        "parent_content_hash": document["content_hash"],
        "chunk_count": len(chunks),
        "chunks": chunks,
    }


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Convert a normalized Jarvis document "
            "into provenance-rich chunks"
        )
    )

    parser.add_argument(
        "document",
        help=(
            "Path to normalized_document_v1 JSON"
        ),
    )

    parser.add_argument(
        "--chunk-size",
        type=int,
        default=1200,
    )

    parser.add_argument(
        "--overlap",
        type=int,
        default=200,
    )

    args = parser.parse_args()

    try:
        path = Path(args.document)

        with path.open(
            "r",
            encoding="utf-8"
        ) as f:
            document = json.load(f)

        result = chunk_document(
            document,
            chunk_size=args.chunk_size,
            overlap=args.overlap,
        )

        print(
            json.dumps(
                result,
                indent=2
            )
        )

        return 0

    except Exception as exc:
        print(
            json.dumps(
                {
                    "status":
                        "DOCUMENT_CHUNK_ERROR",
                    "error": str(exc),
                },
                indent=2,
            )
        )

        return 10


if __name__ == "__main__":
    sys.exit(main())
