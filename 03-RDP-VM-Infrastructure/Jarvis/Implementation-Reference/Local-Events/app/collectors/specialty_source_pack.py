"""
Specialty Birmingham-area source pack.

These sources complement the broad discovery feeds with
sports, promotions, motorsports, science, and museum events.

Registry metadata remains authoritative in config/sources.yaml.
"""


SPECIALTY_SOURCES = [
    {
        "name": "Krispy Kreme Offers",
        "url": "https://www.krispykreme.com/offers",
        "city": "Birmingham",
        "state": "AL",
    },
    {
        "name": "UAB Football",
        "url": "https://uabsports.com/sports/football/schedule",
        "city": "Birmingham",
        "state": "AL",
    },
    {
        "name": "Hueytown High Football",
        "url": (
            "https://www.maxpreps.com/al/hueytown/"
            "hueytown-golden-gophers/football/schedule/"
        ),
        "city": "Hueytown",
        "state": "AL",
    },
    {
        "name": "Birmingham Barons Promotions",
        "url": "https://www.milb.com/birmingham/tickets/promotions",
        "city": "Birmingham",
        "state": "AL",
    },
    {
        "name": "Birmingham Legion FC Match Themes",
        "url": "https://www.bhmlegion.com/2026-match-themes/",
        "city": "Birmingham",
        "state": "AL",
    },
    {
        "name": "Barber Motorsports Park",
        "url": "https://barberracingevents.com/2026-events/",
        "city": "Birmingham",
        "state": "AL",
    },
    {
        "name": "McWane Science Center",
        "url": "https://mcwane.org/upcoming-events/",
        "city": "Birmingham",
        "state": "AL",
    },
    {
        "name": "Birmingham Museum of Art",
        "url": "https://www.artsbma.org/events/",
        "city": "Birmingham",
        "state": "AL",
    },
]


SPECIALTY_NAMES = {
    source["name"]
    for source in SPECIALTY_SOURCES
}
