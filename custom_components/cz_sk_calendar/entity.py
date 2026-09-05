"""Base entity for CZ/SK Calendar integration."""
from __future__ import annotations

from datetime import date
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util import dt as dt_util

from .const import (
    CONF_COUNTRY,
    CONF_REGION,
    CZ_REGIONS,
    DOMAIN,
    SK_REGIONS,
    COUNTRY_CZ,
)


def get_configured_country(config_entry: ConfigEntry) -> str:
    """Return the configured country for a config entry.

    The country is chosen once during setup and cannot be changed later,
    so it always lives in ``entry.data``.
    """
    return config_entry.data[CONF_COUNTRY]


def get_configured_region(config_entry: ConfigEntry) -> str:
    """Return the currently configured region for a config entry.

    The region can be changed from the options flow, which stores it in
    ``entry.options``. Fall back to the value picked during initial setup
    for entries that were never reconfigured.
    """
    return config_entry.options.get(
        CONF_REGION, config_entry.data[CONF_REGION]
    )


class CZSKEntity(Entity):
    """Base class for all CZ/SK Calendar entities.

    Provides common functionality:
    - Device info
    - Country/region configuration
    - Midnight update scheduling
    - Common attributes
    """

    _attr_has_entity_name = False

    def __init__(
        self,
        config_entry: ConfigEntry,
        entity_type: str,
        name: str,
        icon: str,
    ) -> None:
        """Initialize the entity.

        Args:
            config_entry: The config entry
            entity_type: Unique type identifier (e.g., "workday", "school_day")
            name: Human-readable name
            icon: MDI icon name
        """
        self._config_entry = config_entry
        self._country = get_configured_country(config_entry)
        self._region = get_configured_region(config_entry)
        self._entity_type = entity_type

        self._region_name = (
            CZ_REGIONS.get(self._region, self._region)
            if self._country == COUNTRY_CZ
            else SK_REGIONS.get(self._region, self._region)
        )

        self._attr_unique_id = f"{config_entry.entry_id}_{entity_type}"
        self._attr_name = name
        self._attr_icon = icon

    @property
    def suggested_object_id(self) -> str:
        """Return a stable, language-independent object id.

        Display names are localized (CZ/SK), so deriving the entity id from
        the name would give Czech and Slovak installations different ids.
        Basing it on the entity type keeps ``sensor.workday`` the same
        everywhere and matches the entity table in the README. Only new
        entities are affected; already registered ones keep their id.
        """
        return self._entity_type.removeprefix("binary_")

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device info."""
        return {
            "identifiers": {(DOMAIN, self._config_entry.entry_id)},
            "name": f"CZ/SK Calendar ({self._config_entry.title})",
            "manufacturer": "CZ/SK Calendar",
            "model": f"{self._country} Calendar",
        }

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return common attributes."""
        return {
            "country": self._country,
            "region": self._region,
            "region_name": self._region_name,
        }

    async def async_added_to_hass(self) -> None:
        """Register midnight update callback when entity is added."""
        self.async_on_remove(
            async_track_time_change(
                self.hass,
                self._async_update_at_midnight,
                hour=0,
                minute=0,
                second=0,
            )
        )

    @callback
    def _async_update_at_midnight(self, now=None) -> None:
        """Update the entity at midnight."""
        self.async_schedule_update_ha_state(True)

    def _get_localized_name(self, cz_name: str, sk_name: str) -> str:
        """Get localized name based on country.

        Args:
            cz_name: Czech name
            sk_name: Slovak name

        Returns:
            Localized name
        """
        return cz_name if self._country == COUNTRY_CZ else sk_name

    @property
    def today(self) -> date:
        """Get today's date in Home Assistant's configured timezone."""
        return dt_util.now().date()
