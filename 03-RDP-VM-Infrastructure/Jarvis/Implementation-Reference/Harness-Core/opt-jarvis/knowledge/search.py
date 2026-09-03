#!/usr/bin/env python3

import argparse
import json
import sys

sys.path.insert(0, "/opt/jarvis/knowledge")

from embed import JarvisEmbeddingService
from store import JarvisVectorStore


def main():
    parser = argparse.ArgumentParser(
        description="Jarvis semantic knowledge search"
    )

    parser.add_argument(
        "query"
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=5,
    )

    parser.add_argument(
        "--source",
        default=None,
    )

    parser.add_argument(
        "--domain",
        default=None,
    )

    args = parser.parse_args()

    try:
        embedding = JarvisEmbeddingService()

        query_result = embedding.embed(
            args.query
        )

        if query_result.get("status") != "OK":
            raise RuntimeError(
                "Query embedding failed"
            )

        store = JarvisVectorStore()

        result = store.search(
            query_result["vector"],
            limit=args.limit,
            source=args.source,
            domain=args.domain,
        )

        output = {
            "status": "OK",
            "schema": "jarvis_search_result_v1",
            "query": args.query,
            "embedding": {
                "capability":
                    query_result.get("capability"),
                "provider":
                    query_result.get("provider"),
                "node":
                    query_result.get("node"),
                "dimensions":
                    query_result.get("dimensions"),
            },
            "result_count":
                result["result_count"],
            "results":
                result["results"],
        }

        print(
            json.dumps(
                output,
                indent=2,
            )
        )

        return 0

    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "SEARCH_ERROR",
                    "error": str(exc),
                },
                indent=2,
            )
        )

        return 10


if __name__ == "__main__":
    sys.exit(main())
