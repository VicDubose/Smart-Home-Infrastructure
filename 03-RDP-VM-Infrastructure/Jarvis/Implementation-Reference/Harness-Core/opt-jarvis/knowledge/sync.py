#!/usr/bin/env python3

import argparse
import json
import sys

sys.path.insert(0, "/opt/jarvis/knowledge")

from sources.github import GitHubSourceAdapter
from indexer import JarvisKnowledgeIndexer
from index_profile import JarvisIndexProfile
from store import JarvisVectorStore


def emit(data):
    print(
        json.dumps(
            data,
            indent=2,
        )
    )


class JarvisKnowledgeSync:
    def __init__(self):
        self.github = GitHubSourceAdapter()
        self.indexer = JarvisKnowledgeIndexer()
        self.index_profile = JarvisIndexProfile()
        self.store = JarvisVectorStore()

    def current_document_state(
        self,
        document_id,
    ):
        row = self.store.conn.execute(
            """
            SELECT
                content_hash,
                domain,
                metadata_json
            FROM documents
            WHERE document_id = ?
            """,
            (document_id,),
        ).fetchone()

        if row is None:
            return None

        try:
            metadata = json.loads(
                row["metadata_json"]
            )
        except (
            TypeError,
            json.JSONDecodeError,
        ):
            metadata = {}

        profile = (
            metadata.get("index_profile")
            or {}
        )

        return {
            "content_hash":
                row["content_hash"],
            "domain":
                row["domain"],
            "index_profile_fingerprint":
                profile.get("fingerprint"),
        }

    def plan_github_source(
        self,
        source,
    ):
        listing = self.github.list_documents(
            source
        )

        desired_profile = (
            self.index_profile.build()
        )

        desired_fingerprint = (
            desired_profile["fingerprint"]
        )

        plan = []

        counts = {
            "NEW": 0,
            "CHANGED": 0,
            "REINDEX_REQUIRED": 0,
            "METADATA_CHANGED": 0,
            "UNCHANGED": 0,
            "SKIPPED": 0,
        }

        for path in listing["documents"]:
            try:
                document = self.github.get_document(
                    source,
                    path,
                )

            except Exception as exc:
                counts["SKIPPED"] += 1

                plan.append({
                    "action": "SKIPPED",
                    "source_ref": path,
                    "reason": str(exc),
                })

                continue

            existing = (
                self.current_document_state(
                    document["document_id"]
                )
            )

            if existing is None:
                action = "NEW"

            elif (
                existing["content_hash"]
                != document["content_hash"]
            ):
                action = "CHANGED"

            elif (
                existing[
                    "index_profile_fingerprint"
                ]
                != desired_fingerprint
            ):
                action = "REINDEX_REQUIRED"

            elif (
                existing["domain"]
                != document.get("domain")
            ):
                action = "METADATA_CHANGED"

            else:
                action = "UNCHANGED"

            counts[action] += 1

            plan.append({
                "action": action,
                "document_id":
                    document["document_id"],
                "source_ref":
                    document["source_ref"],
                "content_hash":
                    document["content_hash"],
                "existing_hash":
                    (
                        existing["content_hash"]
                        if existing
                        else None
                    ),
                "domain":
                    document.get("domain"),
                "existing_domain":
                    (
                        existing["domain"]
                        if existing
                        else None
                    ),
                "existing_index_profile_fingerprint":
                    (
                        existing[
                            "index_profile_fingerprint"
                        ]
                        if existing
                        else None
                    ),
                "expected_index_profile_fingerprint":
                    desired_fingerprint,
                "git_blob":
                    document["provenance"].get(
                        "git_blob"
                    ),
            })

        ingestible = (
            counts["NEW"]
            + counts["CHANGED"]
            + counts["REINDEX_REQUIRED"]
            + counts["METADATA_CHANGED"]
            + counts["UNCHANGED"]
        )

        return {
            "status": "OK",
            "schema": "jarvis_sync_plan_v3",
            "source": source,
            "commit": listing["commit"],
            "path_eligible_documents":
                listing["document_count"],
            "ingestible_documents":
                ingestible,
            "counts": counts,
            "plan": plan,
        }

    def execute_github_source(
        self,
        source,
        *,
        limit=None,
        metadata_only=False,
    ):
        plan = self.plan_github_source(
            source
        )

        if metadata_only:
            allowed_actions = (
                "METADATA_CHANGED",
            )
        else:
            allowed_actions = (
                "NEW",
                "CHANGED",
                "METADATA_CHANGED",
            )

        work = [
            item
            for item in plan["plan"]
            if item["action"]
            in allowed_actions
        ]

        if limit is not None:
            work = work[:limit]

        completed = []
        failed = []

        for number, item in enumerate(
            work,
            1,
        ):
            path = item["source_ref"]
            action = item["action"]

            print(
                f"[{number:02}/{len(work):02}] "
                f"{action} {path}",
                file=sys.stderr,
            )

            try:
                if action == "METADATA_CHANGED":
                    self.store.update_document_domain(
                        item["document_id"],
                        item["domain"],
                    )

                    completed.append({
                        "source_ref": path,
                        "action": action,
                        "document_id":
                            item["document_id"],
                        "domain":
                            item["domain"],
                        "embedding_work":
                            False,
                    })

                else:
                    result = (
                        self.indexer
                        .index_github_document(
                            source,
                            path,
                        )
                    )

                    completed.append({
                        "source_ref": path,
                        "action": action,
                        "document_id":
                            result[
                                "document_id"
                            ],
                        "chunks_indexed":
                            result[
                                "chunks_indexed"
                            ],
                        "embedding_dimensions":
                            result[
                                "embedding_dimensions"
                            ],
                        "embedding_work":
                            True,
                    })

            except Exception as exc:
                failed.append({
                    "source_ref": path,
                    "action": action,
                    "error": str(exc),
                })

                break

        return {
            "status":
                "SYNC_COMPLETE"
                if not failed
                else "SYNC_PARTIAL",
            "schema":
                "jarvis_sync_result_v2",
            "source": source,
            "source_commit":
                plan["commit"],
            "metadata_only":
                metadata_only,
            "requested_documents":
                len(work),
            "completed_documents":
                len(completed),
            "failed_documents":
                len(failed),
            "completed": completed,
            "failed": failed,
            "note": (
                "No source files modified. "
                "No stale documents deleted."
            ),
        }


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Jarvis incremental knowledge sync"
        )
    )

    parser.add_argument(
        "source"
    )

    parser.add_argument(
        "--execute",
        action="store_true",
    )

    parser.add_argument(
        "--metadata-only",
        action="store_true",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
    )

    args = parser.parse_args()

    if (
        args.metadata_only
        and not args.execute
    ):
        parser.error(
            "--metadata-only requires --execute"
        )

    try:
        sync = JarvisKnowledgeSync()

        if args.execute:
            result = sync.execute_github_source(
                args.source,
                limit=args.limit,
                metadata_only=
                    args.metadata_only,
            )

        else:
            result = sync.plan_github_source(
                args.source
            )

        emit(result)

        return (
            0
            if result["status"]
            in (
                "OK",
                "SYNC_COMPLETE",
            )
            else 2
        )

    except Exception as exc:
        emit({
            "status": "SYNC_ERROR",
            "error": str(exc),
        })

        return 10


if __name__ == "__main__":
    sys.exit(main())
