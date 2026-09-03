from typing import Literal

from pydantic import BaseModel, Field


Category = Literal[
    "music",
    "anime",
    "technology",
    "family",
    "food",
    "community",
    "sports",
    "film",
    "arts",
    "education",
    "health",
    "outdoors",
    "nightlife",
]


SeasonalTheme = Literal[
    "winter",
    "spring",
    "summer",
    "fall",
    "holiday",
    "back_to_school",
    "halloween",
    "thanksgiving",
    "christmas",
    "new_year",
    "none",
]


class EventAnalysis(BaseModel):
    clean_title: str = Field(
        min_length=1,
        max_length=200,
    )

    primary_category: Category

    secondary_categories: list[Category] = Field(
        max_length=5,
    )

    family_friendly: bool
    food_related: bool
    free_event: bool

    seasonal_event: bool
    seasonal_theme: SeasonalTheme

    seasonal_confidence_score: int = Field(
        ge=0,
        le=100,
    )

    keywords: list[str] = Field(
        max_length=12,
    )

    interest_score: int = Field(
        ge=0,
        le=100,
    )

    confidence_score: int = Field(
        ge=0,
        le=100,
    )

    rationale: str = Field(
        min_length=1,
        max_length=300,
    )
