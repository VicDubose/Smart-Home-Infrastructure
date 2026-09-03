#!/usr/bin/env python3

from pathlib import Path

import yaml


CONFIG_PATH = Path(
    "/opt/jarvis/knowledge/domains.yaml"
)


class DomainRouter:
    def __init__(self, config_path=CONFIG_PATH):
        self.config_path = Path(config_path)

        with self.config_path.open(
            "r",
            encoding="utf-8",
        ) as f:
            self.config = yaml.safe_load(f)

        self.allowed_domains = set(
            self.config.get(
                "domains",
                {}
            ).keys()
        )

    def resolve(
        self,
        source,
        source_ref,
    ):
        routing = (
            self.config
            .get("routing", {})
            .get(source)
        )

        if routing is None:
            return None

        rules = sorted(
            routing.get("rules", []),
            key=lambda rule: len(
                rule["prefix"]
            ),
            reverse=True,
        )

        for rule in rules:
            prefix = rule["prefix"]

            if source_ref.startswith(prefix):
                domain = rule["domain"]
                self._validate(domain)
                return domain

        domain = routing.get("default")

        if domain is not None:
            self._validate(domain)

        return domain

    def _validate(self, domain):
        if domain not in self.allowed_domains:
            raise RuntimeError(
                f"Unknown domain in routing: {domain}"
            )


if __name__ == "__main__":
    router = DomainRouter()

    print(
        router.resolve(
            "smart_home_infrastructure",
            "README.md",
        )
    )
