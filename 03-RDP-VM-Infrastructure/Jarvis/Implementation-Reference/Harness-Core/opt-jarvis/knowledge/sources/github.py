#!/usr/bin/env python3

import argparse
import fnmatch
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "/opt/jarvis/knowledge")

from normalize import normalize_document
from source_registry import SourceRegistry
from domain_router import DomainRouter


def emit(data):
    print(json.dumps(data, indent=2))


class GitHubSourceAdapter:
    def __init__(self):
        self.registry = SourceRegistry()
        self.domains = DomainRouter()

    def _git(self, repo, *args):
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        )

        if result.returncode != 0:
            raise RuntimeError(
                result.stderr.strip()
                or f"git command failed: {' '.join(args)}"
            )

        return result.stdout

    @staticmethod
    def _matches(path, patterns):
        for pattern in patterns:
            if fnmatch.fnmatch(path, pattern):
                return True

            # Let **/*.md also match a root-level README.md.
            if pattern.startswith("**/"):
                if fnmatch.fnmatch(path, pattern[3:]):
                    return True

        return False

    def _source_config(self, source_name):
        config = self.registry.config["sources"].get(source_name)

        if config is None:
            raise RuntimeError(
                f"Unknown source: {source_name}"
            )

        return config

    def _healthy_source(self, source_name):
        result = self.registry.get_source(source_name)

        if result.get("status") != "HEALTHY":
            raise RuntimeError(
                f"Source not healthy: "
                f"{source_name}: {result.get('status')}"
            )

        if result.get("type") != "github":
            raise RuntimeError(
                f"Source is not GitHub: {source_name}"
            )

        if not result.get("remote_matches", False):
            raise RuntimeError(
                f"Remote mismatch: {source_name}"
            )

        if not result.get("branch_matches", False):
            raise RuntimeError(
                f"Branch mismatch: {source_name}"
            )

        if result.get("dirty", False):
            raise RuntimeError(
                f"Source working tree is dirty: {source_name}"
            )

        return result

    def list_documents(self, source_name):
        source = self._healthy_source(source_name)
        config = self._source_config(source_name)

        repo = Path(source["local_path"])

        include = config.get("include", [])
        exclude = config.get("exclude", [])

        tracked = self._git(
            repo,
            "ls-files"
        ).splitlines()

        eligible = []

        for relative_path in tracked:
            relative_path = relative_path.strip()

            if not relative_path:
                continue

            if include and not self._matches(
                relative_path,
                include
            ):
                continue

            if exclude and self._matches(
                relative_path,
                exclude
            ):
                continue

            full_path = repo / relative_path

            if not full_path.is_file():
                continue

            eligible.append(relative_path)

        return {
            "status": "OK",
            "schema": "jarvis_source_document_list_v1",
            "source": source_name,
            "commit": source["commit"],
            "document_count": len(eligible),
            "documents": sorted(eligible),
        }

    @staticmethod
    def _title_for(path, text):
        suffix = Path(path).suffix.lower()

        if suffix == ".md":
            for line in text.splitlines():
                line = line.strip()

                if line.startswith("# "):
                    return line[2:].strip()

        return Path(path).name

    def get_document(self, source_name, relative_path):
        source = self._healthy_source(source_name)
        config = self._source_config(source_name)

        listing = self.list_documents(source_name)

        if relative_path not in listing["documents"]:
            raise RuntimeError(
                f"File is not eligible for ingestion: "
                f"{relative_path}"
            )

        repo = Path(source["local_path"])
        full_path = repo / relative_path

        raw = full_path.read_bytes()

        if b"\x00" in raw:
            raise RuntimeError(
                f"Binary content rejected: {relative_path}"
            )

        text = raw.decode(
            "utf-8",
            errors="replace"
        )

        blob = self._git(
            repo,
            "rev-parse",
            f"HEAD:{relative_path}"
        ).strip()

        repository = Path(repo).name

        return normalize_document(
            source=source_name,
            source_type="github",
            source_ref=relative_path,
            content=text,
            provenance={
                "repository": repository,
                "remote": source["remote"],
                "branch": source["branch"],
                "commit": source["commit"],
                "git_blob": blob,
                "path": relative_path,
            },
            authority=config.get("roles", {}),
            domain=self.domains.resolve(
                source_name,
                relative_path,
            ),
            title=self._title_for(
                relative_path,
                text
            ),
            metadata={
                "tracked_by_git": True,
            },
        )


def main():
    parser = argparse.ArgumentParser(
        description="Jarvis GitHub knowledge source adapter"
    )

    sub = parser.add_subparsers(
        dest="command",
        required=True
    )

    list_parser = sub.add_parser("list")
    list_parser.add_argument("source")

    doc_parser = sub.add_parser("document")
    doc_parser.add_argument("source")
    doc_parser.add_argument("path")

    args = parser.parse_args()

    try:
        adapter = GitHubSourceAdapter()

        if args.command == "list":
            emit(
                adapter.list_documents(
                    args.source
                )
            )
            return 0

        if args.command == "document":
            emit(
                adapter.get_document(
                    args.source,
                    args.path
                )
            )
            return 0

    except Exception as exc:
        emit({
            "status": "GITHUB_ADAPTER_ERROR",
            "error": str(exc),
        })
        return 10


if __name__ == "__main__":
    sys.exit(main())
