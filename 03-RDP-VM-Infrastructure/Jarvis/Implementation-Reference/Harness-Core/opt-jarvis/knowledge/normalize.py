#!/usr/bin/env python3

import hashlib
import json
import re
from pathlib import Path


SCHEMA = "normalized_document_v1"


EXTENSION_TYPES = {
    ".md": "markdown",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".txt": "text",
    ".py": "python",
    ".sh": "shell",
}


def normalize_text(text):
    if not isinstance(text, str):
        raise TypeError("content must be text")

    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")

    # Preserve line structure while removing trailing whitespace.
    text = "\n".join(
        line.rstrip()
        for line in text.split("\n")
    )

    text = re.sub(r"\n{4,}", "\n\n\n", text)

    return text.strip()


def content_hash(text):
    return hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()


def document_id(source, source_ref):
    value = f"{source}:{source_ref}".encode("utf-8")

    return hashlib.sha256(value).hexdigest()[:32]


def detect_document_type(path):
    suffix = Path(path).suffix.lower()

    return EXTENSION_TYPES.get(
        suffix,
        "text"
    )


def normalize_document(
    *,
    source,
    source_type,
    source_ref,
    content,
    provenance,
    authority=None,
    domain=None,
    title=None,
    document_type=None,
    metadata=None,
):
    if not source:
        raise ValueError("source is required")

    if not source_type:
        raise ValueError("source_type is required")

    if not source_ref:
        raise ValueError("source_ref is required")

    if not isinstance(provenance, dict):
        raise ValueError("provenance must be an object")

    normalized = normalize_text(content)

    if not normalized:
        raise ValueError("document content is empty")

    if document_type is None:
        document_type = detect_document_type(source_ref)

    return {
        "schema": SCHEMA,
        "document_id": document_id(
            source,
            source_ref
        ),
        "source": source,
        "source_type": source_type,
        "source_ref": source_ref,
        "domain": domain,
        "document_type": document_type,
        "title": title,
        "content_hash": content_hash(normalized),
        "content": normalized,
        "provenance": provenance,
        "authority": authority or {},
        "metadata": metadata or {},
    }
