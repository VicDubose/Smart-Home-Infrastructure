#!/usr/bin/env python3

import argparse
import json
import sys

sys.path.insert(0, "/opt/jarvis/knowledge")

from sources.github import GitHubSourceAdapter
from document_chunker import chunk_document
from embed import JarvisEmbeddingService
from index_profile import JarvisIndexProfile
from store import JarvisVectorStore


def emit(data):
    print(
        json.dumps(
            data,
            indent=2,
        )
    )


class JarvisKnowledgeIndexer:
    def __init__(self):
        self.github = GitHubSourceAdapter()
        self.embedding = JarvisEmbeddingService()
        self.index_profile = JarvisIndexProfile()
        self.store = JarvisVectorStore()

    def index_github_document(
        self,
        source,
        path,
        *,
        chunk_size=1200,
        overlap=200,
    ):
        #
        # 1. Authoritative source → normalized document
        #
        document = self.github.get_document(
            source,
            path,
        )

        index_profile = self.index_profile.build(
            chunk_size=chunk_size,
            overlap=overlap,
        )

        document = dict(document)

        document_metadata = dict(
            document.get("metadata") or {}
        )

        document_metadata["index_profile"] = {
            "schema":
                index_profile["profile"]["schema"],
            "fingerprint":
                index_profile["fingerprint"],
            "fingerprint_material":
                index_profile[
                    "fingerprint_material"
                ],
            "profile":
                index_profile["profile"],
        }

        document["metadata"] = document_metadata

        #
        # 2. Normalized document → provenance-rich chunks
        #
        chunk_set = chunk_document(
            document,
            chunk_size=chunk_size,
            overlap=overlap,
        )

        chunks = chunk_set["chunks"]

        if not chunks:
            raise RuntimeError(
                "Document produced zero chunks"
            )

        #
        # 3. Generate every embedding BEFORE changing
        #    persistent storage.
        #
        embeddings = []

        dimensions = None
        provider = None
        node = None
        capability = None
        model = None

        enriched_chunks = []

        for number, original_chunk in enumerate(
            chunks,
            1,
        ):
            result = self.embedding.embed(
                original_chunk["text"]
            )

            if result.get("status") != "OK":
                raise RuntimeError(
                    f"Embedding failed for chunk "
                    f"{original_chunk['chunk_id']}: "
                    f"{result.get('status')}"
                )

            vector = result.get("vector")

            if not isinstance(vector, list):
                raise RuntimeError(
                    "Embedding response missing vector"
                )

            if not vector:
                raise RuntimeError(
                    "Embedding vector is empty"
                )

            reported_dimensions = result.get(
                "dimensions"
            )

            if reported_dimensions != len(vector):
                raise RuntimeError(
                    "Embedding dimension metadata mismatch"
                )

            if dimensions is None:
                dimensions = len(vector)

            elif len(vector) != dimensions:
                raise RuntimeError(
                    "Embedding dimensions changed "
                    "within one document"
                )

            provider = result.get("provider")
            node = result.get("node")
            capability = result.get("capability")
            model = result.get("model")

            expected_model = (
                index_profile["profile"]
                ["embedding"]["requested_model"]
            )

            if model != expected_model:
                raise RuntimeError(
                    "Embedding model changed during "
                    "index operation: "
                    f"expected {expected_model}, "
                    f"got {model}"
                )

            chunk = dict(original_chunk)

            metadata = dict(
                chunk.get("metadata") or {}
            )

            metadata["embedding"] = {
                "capability": capability,
                "provider": provider,
                "node": node,
                "model": model,
                "dimensions": len(vector),
                "index_profile_fingerprint":
                    index_profile["fingerprint"],
            }

            chunk["metadata"] = metadata

            enriched_chunks.append(chunk)
            embeddings.append(vector)

            print(
                f"Embedded "
                f"{number}/{len(chunks)} "
                f"{original_chunk['chunk_id']}",
                file=sys.stderr,
            )

        #
        # 4. Replace this document's derived index only
        #    after every embedding succeeded.
        #
        self.store.replace_document_chunks(
            document,
            enriched_chunks,
            embeddings,
        )

        return {
            "status": "INDEXED",
            "schema": "jarvis_index_result_v1",
            "document_id": document["document_id"],
            "source": document["source"],
            "source_ref": document["source_ref"],
            "content_hash": document["content_hash"],
            "commit": document["provenance"].get(
                "commit"
            ),
            "git_blob": document["provenance"].get(
                "git_blob"
            ),
            "chunks_indexed": len(chunks),
            "embedding_capability": capability,
            "embedding_provider": provider,
            "embedding_node": node,
            "embedding_model": model,
            "embedding_dimensions": dimensions,
            "index_profile_fingerprint":
                index_profile["fingerprint"],
            "database": str(
                self.store.db_path
            ),
        }


def main():
    parser = argparse.ArgumentParser(
        description="Jarvis knowledge indexer"
    )

    sub = parser.add_subparsers(
        dest="command",
        required=True,
    )

    document_parser = sub.add_parser(
        "github-document"
    )

    document_parser.add_argument(
        "source"
    )

    document_parser.add_argument(
        "path"
    )

    document_parser.add_argument(
        "--chunk-size",
        type=int,
        default=1200,
    )

    document_parser.add_argument(
        "--overlap",
        type=int,
        default=200,
    )

    args = parser.parse_args()

    try:
        indexer = JarvisKnowledgeIndexer()

        if args.command == "github-document":
            result = indexer.index_github_document(
                args.source,
                args.path,
                chunk_size=args.chunk_size,
                overlap=args.overlap,
            )

            emit(result)
            return 0

    except Exception as exc:
        emit({
            "status": "INDEX_ERROR",
            "error": str(exc),
        })

        return 10


if __name__ == "__main__":
    sys.exit(main())
