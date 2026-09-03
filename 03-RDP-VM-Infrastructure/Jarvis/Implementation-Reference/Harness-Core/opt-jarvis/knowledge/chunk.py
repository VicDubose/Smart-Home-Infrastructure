#!/usr/bin/env python3

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


DEFAULT_CHUNK_SIZE = 1200
DEFAULT_OVERLAP = 200


def normalize_text(text):
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def make_chunk_id(source, index, text):
    material = f"{source}:{index}:{text}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()[:24]


def chunk_text(
    text,
    source,
    domain="general",
    document_type="text",
    chunk_size=DEFAULT_CHUNK_SIZE,
    overlap=DEFAULT_OVERLAP,
):
    if not isinstance(text, str):
        raise TypeError("text must be a string")

    if not text:
        return []

    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero")

    if overlap < 0:
        raise ValueError("overlap cannot be negative")

    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    chunks = []
    start = 0
    index = 0
    length = len(text)

    while start < length:
        target_end = min(start + chunk_size, length)
        end = target_end

        if target_end < length:
            search_start = max(start, target_end - 250)
            window = text[search_start:target_end]

            paragraph_break = window.rfind("\n\n")

            if paragraph_break != -1:
                candidate = search_start + paragraph_break
                if candidate > start:
                    end = candidate
            else:
                sentence_matches = list(
                    re.finditer(r"[.!?]\s+", window)
                )

                if sentence_matches:
                    candidate = (
                        search_start
                        + sentence_matches[-1].end()
                    )

                    if candidate > start:
                        end = candidate

        chunk = text[start:end]

        if chunk.strip():
            chunks.append({
                "schema": "jarvis_chunk_v1",
                "chunk_id": make_chunk_id(
                    source,
                    index,
                    chunk,
                ),
                "index": index,
                "source": source,
                "domain": domain,
                "document_type": document_type,
                "start_char": start,
                "end_char": end,
                "text": chunk,
            })

            index += 1

        if end >= length:
            break

        next_start = end - overlap

        if next_start <= start:
            next_start = end

        start = next_start

    return chunks


def main():
    parser = argparse.ArgumentParser(
        description="Jarvis deterministic document chunker"
    )

    parser.add_argument(
        "file",
        help="UTF-8 text/markdown file to chunk"
    )

    parser.add_argument(
        "--domain",
        default="general",
        help="Knowledge domain"
    )

    parser.add_argument(
        "--type",
        default="text",
        dest="document_type",
        help="Document type"
    )

    parser.add_argument(
        "--chunk-size",
        type=int,
        default=DEFAULT_CHUNK_SIZE
    )

    parser.add_argument(
        "--overlap",
        type=int,
        default=DEFAULT_OVERLAP
    )

    args = parser.parse_args()

    path = Path(args.file)

    if not path.is_file():
        print(json.dumps({
            "status": "CHUNK_ERROR",
            "error": f"File not found: {path}"
        }, indent=2))

        return 1

    try:
        text = path.read_text(encoding="utf-8")

        chunks = chunk_text(
            text=text,
            source=str(path),
            domain=args.domain,
            document_type=args.document_type,
            chunk_size=args.chunk_size,
            overlap=args.overlap,
        )

        print(json.dumps({
            "status": "OK",
            "schema": "jarvis_chunk_set_v1",
            "source": str(path),
            "chunk_count": len(chunks),
            "chunks": chunks,
        }, indent=2))

        return 0

    except Exception as exc:
        print(json.dumps({
            "status": "CHUNK_ERROR",
            "error": str(exc)
        }, indent=2))

        return 1


if __name__ == "__main__":
    sys.exit(main())
