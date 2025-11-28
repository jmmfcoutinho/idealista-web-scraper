"""Configuration settings and loaders for the Idealista scraper."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator


class DatabaseConfig(BaseModel):
    """Database connection configuration.

    Attributes:
        url: Database connection URL. Defaults to SQLite.
    """

    url: str = Field(default="sqlite:///./data/idealista.db")


class ScrapingConfig(BaseModel):
    """Configuration for scraping behavior.

    Attributes:
        delay_seconds: Delay between requests in seconds.
        max_retries: Maximum retry attempts for failed requests.
        use_brightdata: Whether to use Bright Data Scraping Browser for scraping.
        max_pages: Maximum pages to scrape per search. None for unlimited.
    """

    delay_seconds: float = Field(default=2.0, ge=0)
    max_retries: int = Field(default=3, ge=0)
    use_brightdata: bool = Field(default=True)
    max_pages: int | None = Field(default=None, ge=1)


class FilterConfig(BaseModel):
    """Filters for listing searches.

    Attributes:
        min_price: Minimum price filter.
        max_price: Maximum price filter.
        min_size: Minimum size in square meters.
        max_size: Maximum size in square meters.
        typology: Typology filter (e.g., "t0", "t1", "t2", "t3").
    """

    min_price: int | None = Field(default=None, ge=0)
    max_price: int | None = Field(default=None, ge=0)
    min_size: int | None = Field(default=None, ge=0)
    max_size: int | None = Field(default=None, ge=0)
    typology: str | None = Field(default=None)

    @field_validator("typology")
    @classmethod
    def validate_typology(cls, v: str | None) -> str | None:
        """Validate typology format."""
        if v is not None:
            v = v.lower()
            valid_typologies = {"t0", "t1", "t2", "t3", "t4", "t5", "t5+"}
            if v not in valid_typologies:
                msg = f"typology must be one of {valid_typologies}"
                raise ValueError(msg)
        return v


class RunConfig(BaseModel):
    """Main configuration for a scraper run.

    Attributes:
        operation: The operation type to scrape.
        geographic_level: The geographic granularity for scraping.
        locations: List of location slugs to scrape.
        property_types: List of property types to scrape.
        scraping: Scraping behavior configuration.
        filters: Search filter configuration.
        database: Database connection configuration.
    """

    operation: Literal["comprar", "arrendar", "both"] = Field(default="both")
    geographic_level: Literal["concelho", "distrito"] = Field(default="concelho")
    locations: list[str] = Field(default_factory=list)
    property_types: list[str] = Field(default_factory=lambda: ["casas"])
    scraping: ScrapingConfig = Field(default_factory=ScrapingConfig)
    filters: FilterConfig = Field(default_factory=FilterConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)

    @field_validator("property_types")
    @classmethod
    def validate_property_types(cls, v: list[str]) -> list[str]:
        """Validate property types."""
        valid_types = {"casas", "apartamentos", "quartos", "garagens", "terrenos"}
        for pt in v:
            if pt.lower() not in valid_types:
                msg = f"property_type '{pt}' must be one of {valid_types}"
                raise ValueError(msg)
        return [pt.lower() for pt in v]


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep merge two dictionaries, with override taking precedence.

    Args:
        base: The base dictionary.
        override: The dictionary with values to override.

    Returns:
        A new dictionary with merged values.
    """
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _load_yaml_config(config_path: Path) -> dict[str, Any]:
    """Load configuration from a YAML file.

    Args:
        config_path: Path to the YAML configuration file.

    Returns:
        Dictionary with configuration values.

    Raises:
        FileNotFoundError: If the configuration file does not exist.
    """
    if not config_path.exists():
        msg = f"Configuration file not found: {config_path}"
        raise FileNotFoundError(msg)

    with config_path.open() as f:
        data = yaml.safe_load(f)
        return data if data else {}


def _get_env_overrides() -> dict[str, Any]:
    """Get configuration overrides from environment variables.

    Returns:
        Dictionary with environment-based overrides.
    """
    overrides: dict[str, Any] = {}

    # Database URL
    if database_url := os.getenv("DATABASE_URL"):
        overrides.setdefault("database", {})["url"] = database_url

    # Log level (not part of config but useful to capture)
    # ZYTE_API_KEY is read directly where needed, not stored in config

    return overrides


def _flatten_cli_overrides(cli_overrides: dict[str, Any]) -> dict[str, Any]:
    """Convert flat CLI overrides to nested structure.

    Args:
        cli_overrides: Flat dictionary with dotted keys or nested structure.

    Returns:
        Nested dictionary matching config structure.
    """
    result: dict[str, Any] = {}

    # Map of flat keys to nested paths
    key_mapping: dict[str, list[str]] = {
        "operation": ["operation"],
        "geographic_level": ["geographic_level"],
        "locations": ["locations"],
        "property_types": ["property_types"],
        "delay_seconds": ["scraping", "delay_seconds"],
        "max_retries": ["scraping", "max_retries"],
        "use_brightdata": ["scraping", "use_brightdata"],
        "max_pages": ["scraping", "max_pages"],
        "min_price": ["filters", "min_price"],
        "max_price": ["filters", "max_price"],
        "min_size": ["filters", "min_size"],
        "max_size": ["filters", "max_size"],
        "typology": ["filters", "typology"],
        "database_url": ["database", "url"],
    }

    for key, value in cli_overrides.items():
        if value is None:
            continue

        if key in key_mapping:
            path = key_mapping[key]
            current = result
            for part in path[:-1]:
                current = current.setdefault(part, {})
            current[path[-1]] = value
        elif isinstance(value, dict):
            # Already nested structure
            result = _deep_merge(result, {key: value})

    return result


def load_config(
    config_path: Path | None = None,
    cli_overrides: dict[str, Any] | None = None,
) -> RunConfig:
    """Load configuration from YAML, environment variables, and CLI overrides.

    Configuration precedence (highest to lowest):
    1. CLI overrides
    2. Environment variables
    3. YAML config file
    4. Default values

    Args:
        config_path: Optional path to a YAML configuration file.
        cli_overrides: Optional dictionary of CLI-provided overrides.

    Returns:
        A validated RunConfig instance.
    """
    # Load .env file if present
    load_dotenv()

    # Start with empty config (will use defaults)
    config_data: dict[str, Any] = {}

    # Load YAML config if path provided
    if config_path is not None:
        yaml_config = _load_yaml_config(config_path)
        # Handle nested 'run' key in YAML
        if "run" in yaml_config:
            run_config = yaml_config.pop("run")
            config_data = _deep_merge(config_data, run_config)
        config_data = _deep_merge(config_data, yaml_config)

    # Apply environment overrides
    env_overrides = _get_env_overrides()
    config_data = _deep_merge(config_data, env_overrides)

    # Apply CLI overrides
    if cli_overrides:
        nested_cli = _flatten_cli_overrides(cli_overrides)
        config_data = _deep_merge(config_data, nested_cli)

    return RunConfig.model_validate(config_data)


def get_brightdata_credentials() -> dict[str, str]:
    """Get Bright Data Scraping Browser credentials from environment variables.

    Returns:
        Dictionary with 'user' and 'password' keys.

    Raises:
        ValueError: If required environment variables are not set.
    """
    load_dotenv()

    user = os.getenv("BRIGHTDATA_BROWSER_USER")
    password = os.getenv("BRIGHTDATA_BROWSER_PASS")

    if not user or not password:
        msg = (
            "BRIGHTDATA_BROWSER_USER and BRIGHTDATA_BROWSER_PASS "
            "environment variables are required"
        )
        raise ValueError(msg)

    return {"user": user, "password": password}


def get_zyte_api_key() -> str:
    """Get the Zyte API key from environment variables.

    Deprecated: Use get_brightdata_credentials() instead.

    Returns:
        The Zyte API key.

    Raises:
        ValueError: If ZYTE_API_KEY is not set.
    """
    load_dotenv()
    api_key = os.getenv("ZYTE_API_KEY")
    if not api_key:
        msg = "ZYTE_API_KEY environment variable is required"
        raise ValueError(msg)
    return api_key
