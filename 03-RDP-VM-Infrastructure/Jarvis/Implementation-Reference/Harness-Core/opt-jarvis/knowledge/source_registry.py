#!/usr/bin/env python3

import argparse
import json
import subprocess
import sys
from pathlib import Path

import yaml


SOURCES_CONFIG = Path("/opt/jarvis/knowledge/sources.yaml")


class SourceRegistry:
    def __init__(self, config_path=SOURCES_CONFIG):
        self.config_path = Path(config_path)
        self.config = self._load()

    def _load(self):
        if not self.config_path.is_file():
            raise RuntimeError(
                f"Source configuration missing: {self.config_path}"
            )

        with self.config_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            raise RuntimeError("Invalid sources.yaml")

        if "sources" not in data:
            raise RuntimeError("sources.yaml missing sources")

        return data

    def list_sources(self):
        result = {}

        for name, source in self.config["sources"].items():
            result[name] = {
                "type": source.get("type"),
                "enabled": bool(source.get("enabled", False)),
                "local_path": source.get("local_path"),
                "remote": source.get("remote"),
                "branch": source.get("branch"),
                "roles": source.get("roles", {}),
            }

        return result

    def get_source(self, name):
        source = self.config["sources"].get(name)

        if source is None:
            return {
                "status": "UNKNOWN_SOURCE",
                "source": name,
            }

        if not source.get("enabled", False):
            return {
                "status": "SOURCE_DISABLED",
                "source": name,
                "type": source.get("type"),
            }

        source_type = source.get("type")

        if source_type == "github":
            return self._inspect_github(name, source)

        return {
            "status": "SOURCE_TYPE_UNSUPPORTED",
            "source": name,
            "type": source_type,
        }

    def _git(self, repo, *args):
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
        )

        if result.returncode != 0:
            raise RuntimeError(
                result.stderr.strip()
                or f"git command failed: {' '.join(args)}"
            )

        return result.stdout.strip()

    def _inspect_github(self, name, source):
        local_path = source.get("local_path")

        if not local_path:
            return {
                "status": "SOURCE_MISCONFIGURED",
                "source": name,
                "error": "local_path missing",
            }

        repo = Path(local_path)

        if not repo.is_dir():
            return {
                "status": "SOURCE_NOT_FOUND",
                "source": name,
                "local_path": str(repo),
            }

        if not (repo / ".git").exists():
            return {
                "status": "NOT_GIT_REPOSITORY",
                "source": name,
                "local_path": str(repo),
            }

        try:
            branch = self._git(
                repo,
                "branch",
                "--show-current"
            )

            commit = self._git(
                repo,
                "rev-parse",
                "HEAD"
            )

            remote = self._git(
                repo,
                "remote",
                "get-url",
                "origin"
            )

            dirty = bool(
                self._git(
                    repo,
                    "status",
                    "--porcelain"
                )
            )

        except Exception as exc:
            return {
                "status": "SOURCE_INSPECTION_ERROR",
                "source": name,
                "error": str(exc),
            }

        expected_remote = source.get("remote")
        expected_branch = source.get("branch")

        return {
            "status": "HEALTHY",
            "schema": "jarvis_source_v1",
            "source": name,
            "type": "github",
            "local_path": str(repo),
            "remote": remote,
            "expected_remote": expected_remote,
            "remote_matches": (
                expected_remote is None
                or remote == expected_remote
            ),
            "branch": branch,
            "expected_branch": expected_branch,
            "branch_matches": (
                expected_branch is None
                or branch == expected_branch
            ),
            "commit": commit,
            "dirty": dirty,
            "roles": source.get("roles", {}),
            "include": source.get("include", []),
            "exclude": source.get("exclude", []),
        }


def emit(data):
    print(json.dumps(data, indent=2))


def main():
    parser = argparse.ArgumentParser(
        description="Jarvis knowledge source registry"
    )

    sub = parser.add_subparsers(
        dest="command",
        required=True
    )

    sub.add_parser("list")

    inspect_parser = sub.add_parser("inspect")
    inspect_parser.add_argument("source")

    args = parser.parse_args()

    try:
        registry = SourceRegistry()

        if args.command == "list":
            emit(registry.list_sources())
            return 0

        if args.command == "inspect":
            result = registry.get_source(args.source)
            emit(result)

            return 0 if result["status"] == "HEALTHY" else 2

    except Exception as exc:
        emit({
            "status": "SOURCE_REGISTRY_ERROR",
            "error": str(exc),
        })

        return 10


if __name__ == "__main__":
    sys.exit(main())
