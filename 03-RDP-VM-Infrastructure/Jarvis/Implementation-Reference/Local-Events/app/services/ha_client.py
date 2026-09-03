from pathlib import Path
import requests


DEFAULT_ENV = Path(
    "/srv/docker/stacks/al-power/.env"
)


class HomeAssistantError(RuntimeError):
    pass


def load_env(path=DEFAULT_ENV):
    values = {}

    for raw in Path(path).read_text().splitlines():
        raw = raw.strip()

        if (
            not raw
            or raw.startswith("#")
            or "=" not in raw
        ):
            continue

        key, value = raw.split("=", 1)

        values[key.strip()] = (
            value.strip()
            .strip('"')
            .strip("'")
        )

    return values


def connection():
    values = load_env()

    url = (
        values.get("HA_URL")
        or values.get("HASS_URL")
        or values.get("HOME_ASSISTANT_URL")
    )

    token = (
        values.get("HA_TOKEN")
        or values.get("HASS_TOKEN")
        or values.get("HOME_ASSISTANT_TOKEN")
        or values.get("HA_LONG_LIVED_TOKEN")
    )

    if not url:
        raise HomeAssistantError(
            "Existing HA environment has no HA URL."
        )

    if not token:
        raise HomeAssistantError(
            "Existing HA environment has no HA token."
        )

    return (
        url.rstrip("/"),
        token,
    )


def api_get(endpoint, timeout=15):
    base_url, token = connection()

    response = requests.get(
        base_url + endpoint,
        headers={
            "Authorization": (
                f"Bearer {token}"
            ),
            "Content-Type": "application/json",
        },
        timeout=timeout,
    )

    if response.status_code != 200:
        raise HomeAssistantError(
            f"Home Assistant returned "
            f"HTTP {response.status_code} "
            f"for {endpoint}"
        )

    return response.json()


def get_config():
    return api_get(
        "/api/config"
    )


def get_home_location():
    config = get_config()

    latitude = config.get(
        "latitude"
    )

    longitude = config.get(
        "longitude"
    )

    if (
        latitude is None
        or longitude is None
    ):
        raise HomeAssistantError(
            "Home Assistant config contains "
            "no home coordinates."
        )

    return {
        "latitude": float(latitude),
        "longitude": float(longitude),
        "location_name": config.get(
            "location_name",
            "Home",
        ),
    }


if __name__ == "__main__":
    config = get_config()
    home = get_home_location()

    print(
        "===== LOCAL EVENTS -> HOME ASSISTANT ====="
    )
    print("Authentication: PASS")
    print(
        "Location:",
        home["location_name"],
    )
    print("Coordinates available: YES")
    print(
        "HA version:",
        config.get("version", "unknown"),
    )
    print()
    print(
        "No token or coordinates were displayed."
    )
