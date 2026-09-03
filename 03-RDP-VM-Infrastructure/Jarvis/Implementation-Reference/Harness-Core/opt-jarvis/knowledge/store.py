#!/usr/bin/env python3

import argparse
import json
import math
import sqlite3
import sys
from pathlib import Path


DEFAULT_DB = Path(
    "/var/lib/jarvis/vector/jarvis_vectors.db"
)


class JarvisVectorStore:
    def __init__(self, db_path=DEFAULT_DB):
        self.db_path = Path(db_path)

        self.db_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.conn = sqlite3.connect(
            self.db_path
        )

        self.conn.row_factory = sqlite3.Row

        self._initialize()

    def _initialize(self):
        self.conn.executescript(
            """
            PRAGMA journal_mode=WAL;
            PRAGMA foreign_keys=ON;

            CREATE TABLE IF NOT EXISTS documents (
                document_id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_ref TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                title TEXT,
                document_type TEXT,
                domain TEXT,
                provenance_json TEXT NOT NULL,
                authority_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                indexed_at TEXT NOT NULL
                    DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS chunks (
                chunk_id TEXT PRIMARY KEY,

                document_id TEXT NOT NULL
                    REFERENCES documents(document_id)
                    ON DELETE CASCADE,

                chunk_hash TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,

                start_char INTEGER NOT NULL,
                end_char INTEGER NOT NULL,

                text TEXT NOT NULL,

                embedding_json TEXT NOT NULL,
                embedding_dimensions INTEGER NOT NULL,

                source TEXT NOT NULL,
                source_ref TEXT NOT NULL,
                domain TEXT,

                provenance_json TEXT NOT NULL,
                authority_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL,

                indexed_at TEXT NOT NULL
                    DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS
                idx_chunks_document
            ON chunks(document_id);

            CREATE INDEX IF NOT EXISTS
                idx_chunks_source
            ON chunks(source);

            CREATE INDEX IF NOT EXISTS
                idx_documents_source
            ON documents(source);
            """
        )

        self.conn.commit()

    @staticmethod
    def _json(data):
        return json.dumps(
            data or {},
            separators=(",", ":"),
            sort_keys=True,
        )

    @staticmethod
    def _cosine(a, b):
        if len(a) != len(b):
            raise ValueError(
                "Embedding dimension mismatch"
            )

        dot = sum(
            x * y
            for x, y in zip(a, b)
        )

        norm_a = math.sqrt(
            sum(x * x for x in a)
        )

        norm_b = math.sqrt(
            sum(x * x for x in b)
        )

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return dot / (norm_a * norm_b)

    def _upsert_document_no_commit(
        self,
        document,
    ):
        self.conn.execute(
            """
            INSERT INTO documents (
                document_id,
                source,
                source_type,
                source_ref,
                content_hash,
                title,
                document_type,
                domain,
                provenance_json,
                authority_json,
                metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

            ON CONFLICT(document_id)
            DO UPDATE SET
                source=excluded.source,
                source_type=excluded.source_type,
                source_ref=excluded.source_ref,
                content_hash=excluded.content_hash,
                title=excluded.title,
                document_type=excluded.document_type,
                domain=excluded.domain,
                provenance_json=excluded.provenance_json,
                authority_json=excluded.authority_json,
                metadata_json=excluded.metadata_json,
                indexed_at=CURRENT_TIMESTAMP
            """,
            (
                document["document_id"],
                document["source"],
                document["source_type"],
                document["source_ref"],
                document["content_hash"],
                document.get("title"),
                document.get("document_type"),
                document.get("domain"),
                self._json(
                    document.get("provenance")
                ),
                self._json(
                    document.get("authority")
                ),
                self._json(
                    document.get("metadata")
                ),
            ),
        )

    def upsert_document(
        self,
        document,
    ):
        if self.conn.in_transaction:
            raise RuntimeError(
                "Cannot call committing upsert_document "
                "inside an active transaction"
            )

        try:
            self._upsert_document_no_commit(
                document
            )

            self.conn.commit()

        except Exception:
            self.conn.rollback()
            raise

    def replace_document_chunks(
        self,
        document,
        chunks,
        embeddings,
    ):
        if len(chunks) != len(embeddings):
            raise ValueError(
                "chunks and embeddings count mismatch"
            )

        if not chunks:
            raise ValueError(
                "Document replacement requires chunks"
            )

        document_id = document["document_id"]

        #
        # Validate everything we can BEFORE opening
        # the persistent transaction.
        #
        for chunk, embedding in zip(
            chunks,
            embeddings,
        ):
            if (
                chunk.get("document_id")
                != document_id
            ):
                raise ValueError(
                    "Chunk document_id mismatch: "
                    f"{chunk.get('chunk_id')}"
                )

            if not embedding:
                raise ValueError(
                    f"Empty embedding: "
                    f"{chunk['chunk_id']}"
                )

        if self.conn.in_transaction:
            raise RuntimeError(
                "Cannot start document replacement "
                "inside an active transaction"
            )

        try:
            #
            # Parent document + all derived chunks
            # are now one atomic unit.
            #
            self.conn.execute("BEGIN")

            self._upsert_document_no_commit(
                document
            )

            self.conn.execute(
                """
                DELETE FROM chunks
                WHERE document_id = ?
                """,
                (
                    document_id,
                ),
            )

            for chunk, embedding in zip(
                chunks,
                embeddings,
            ):
                self.conn.execute(
                    """
                    INSERT INTO chunks (
                        chunk_id,
                        document_id,
                        chunk_hash,
                        chunk_index,
                        start_char,
                        end_char,
                        text,
                        embedding_json,
                        embedding_dimensions,
                        source,
                        source_ref,
                        domain,
                        provenance_json,
                        authority_json,
                        metadata_json
                    )
                    VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?
                    )
                    """,
                    (
                        chunk["chunk_id"],
                        chunk["document_id"],
                        chunk["chunk_hash"],
                        chunk["index"],
                        chunk["start_char"],
                        chunk["end_char"],
                        chunk["text"],
                        json.dumps(embedding),
                        len(embedding),
                        chunk["source"],
                        chunk["source_ref"],
                        chunk.get("domain"),
                        self._json(
                            chunk.get("provenance")
                        ),
                        self._json(
                            chunk.get("authority")
                        ),
                        self._json(
                            chunk.get("metadata")
                        ),
                    ),
                )

            self.conn.commit()

        except Exception:
            self.conn.rollback()
            raise

    def update_document_domain(
        self,
        document_id,
        domain,
    ):
        row = self.conn.execute(
            """
            SELECT document_id
            FROM documents
            WHERE document_id = ?
            """,
            (document_id,),
        ).fetchone()

        if row is None:
            raise ValueError(
                f"Unknown document_id: {document_id}"
            )

        try:
            self.conn.execute("BEGIN")

            self.conn.execute(
                """
                UPDATE documents
                SET
                    domain = ?,
                    indexed_at = CURRENT_TIMESTAMP
                WHERE document_id = ?
                """,
                (
                    domain,
                    document_id,
                ),
            )

            self.conn.execute(
                """
                UPDATE chunks
                SET
                    domain = ?,
                    indexed_at = CURRENT_TIMESTAMP
                WHERE document_id = ?
                """,
                (
                    domain,
                    document_id,
                ),
            )

            self.conn.commit()

        except Exception:
            self.conn.rollback()
            raise

    def delete_document(self, document_id):
        self.conn.execute(
            """
            DELETE FROM documents
            WHERE document_id = ?
            """,
            (document_id,),
        )

        self.conn.commit()

    def stats(self):
        documents = self.conn.execute(
            "SELECT COUNT(*) FROM documents"
        ).fetchone()[0]

        chunks = self.conn.execute(
            "SELECT COUNT(*) FROM chunks"
        ).fetchone()[0]

        return {
            "status": "OK",
            "database": str(self.db_path),
            "documents": documents,
            "chunks": chunks,
        }

    def search(
        self,
        query_embedding,
        *,
        limit=5,
        source=None,
        domain=None,
    ):
        sql = """
            SELECT *
            FROM chunks
            WHERE 1=1
        """

        params = []

        if source:
            sql += " AND source = ?"
            params.append(source)

        if domain:
            sql += " AND domain = ?"
            params.append(domain)

        rows = self.conn.execute(
            sql,
            params,
        ).fetchall()

        results = []

        for row in rows:
            embedding = json.loads(
                row["embedding_json"]
            )

            score = self._cosine(
                query_embedding,
                embedding,
            )

            results.append({
                "chunk_id": row["chunk_id"],
                "document_id":
                    row["document_id"],
                "source": row["source"],
                "source_ref":
                    row["source_ref"],
                "domain": row["domain"],
                "score": score,
                "text": row["text"],
                "provenance": json.loads(
                    row["provenance_json"]
                ),
                "authority": json.loads(
                    row["authority_json"]
                ),
            })

        results.sort(
            key=lambda item: item["score"],
            reverse=True,
        )

        return {
            "status": "OK",
            "result_count": min(
                limit,
                len(results),
            ),
            "results": results[:limit],
        }


def emit(data):
    print(
        json.dumps(
            data,
            indent=2,
        )
    )


def main():
    parser = argparse.ArgumentParser(
        description="Jarvis persistent vector store"
    )

    sub = parser.add_subparsers(
        dest="command",
        required=True,
    )

    sub.add_parser("stats")

    args = parser.parse_args()

    try:
        store = JarvisVectorStore()

        if args.command == "stats":
            emit(store.stats())
            return 0

    except Exception as exc:
        emit({
            "status": "VECTOR_STORE_ERROR",
            "error": str(exc),
        })

        return 10


if __name__ == "__main__":
    sys.exit(main())
