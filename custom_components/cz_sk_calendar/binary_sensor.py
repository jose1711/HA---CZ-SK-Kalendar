"""Binary sensor platform for CZ/SK School & Work Calendar."""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import COUNTRY_CZ
from .entity import CZSKEntity, get_configured_country
from .core import (
    get_holiday_name,
    get_special_day_name,
    get_vacation_name,
    is_holiday,
    is_school_day,
    is_vacation,
    is_workday,
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the CZ/SK Calendar binary sensors."""
    country = get_configured_country(config_entry)

    sensors = [
        CZSKBinarySensor(
            config_entry,
            "binary_workday",
            "Pracovní den" if country == COUNTRY_CZ else "Pracovný deň",
            "mdi:briefcase",
            "mdi:briefcase-off",
            lambda e: is_workday(e.today, e._country),
        ),
        CZSKBinarySensor(
            config_entry,
            "binary_school_day",
            "Školní den" if country == COUNTRY_CZ else "Školský deň",
            "mdi:school",
            "mdi:school-outline",
            lambda e: is_school_day(e.today, e._country, e._region),
        ),
        CZSKBinarySensor(
            config_entry,
            "binary_holiday",
            "Svátek" if country == COUNTRY_CZ else "Sviatok",
            "mdi:party-popper",
            "mdi:calendar-blank",
            lambda e: is_holiday(e.today, e._country),
        ),
        CZSKBinarySensor(
            config_entry,
            "binary_vacation",
            "Prázdniny",
            "mdi:beach",
            "mdi:calendar-blank",
            lambda e: is_vacation(e.today, e._country, e._region),
        ),
        CZSKBinarySensor(
            config_entry,
            "binary_weekend",
            "Víkend",
            "mdi:weather-sunny",
            "mdi:briefcase",
            lambda e: e.today.weekday() >= 5,
        ),
        CZSKBinarySensor(
            config_entry,
            "binary_special_day",
            "Významný den" if country == COUNTRY_CZ else "Významný deň",
            "mdi:star",
            "mdi:star-outline",
            lambda e: get_special_day_name(e.today, e._country) is not None,
        ),
    ]

    async_add_entities(sensors, True)


class CZSKBinarySensor(CZSKEntity, BinarySensorEntity):
    """Binary sensor for CZ/SK Calendar."""

    def __init__(
        self,
        config_entry: ConfigEntry,
        entity_type: str,
        name: str,
        icon_on: str,
        icon_off: str,
        value_fn,
        device_class: BinarySensorDeviceClass | None = None,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(config_entry, entity_type, name, icon_on)
        self._icon_on = icon_on
        self._icon_off = icon_off
        self._value_fn = value_fn
        self._attr_device_class = device_class

    @property
    def is_on(self) -> bool:
        """Return true if the binary sensor is on."""
        return self._value_fn(self)

    @property
    def icon(self) -> str:
        """Return the icon based on state."""
        return self._icon_on if self.is_on else self._icon_off

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        attrs = super().extra_state_attributes.copy()
        today = self.today
        tomorrow = today + timedelta(days=1)

        # Add tomorrow's value for relevant sensors
        if "workday" in self._entity_type:
            attrs["tomorrow"] = is_workday(tomorrow, self._country)
            if is_holiday(today, self._country):
                attrs["holiday_name"] = get_holiday_name(today, self._country)

        elif "school_day" in self._entity_type:
            attrs["tomorrow"] = is_school_day(tomorrow, self._country, self._region)
            if not self.is_on:
                if today.weekday() >= 5:
                    attrs["reason"] = "weekend"
                elif is_holiday(today, self._country):
                    attrs["reason"] = "holiday"
                    attrs["holiday_name"] = get_holiday_name(today, self._country)
                elif is_vacation(today, self._country, self._region):
                    attrs["reason"] = "vacation"
                    attrs["vacation_name"] = get_vacation_name(today, self._country, self._region)

        elif "holiday" in self._entity_type:
            name = get_holiday_name(today, self._country)
            if name:
                attrs["name"] = name

        elif "vacation" in self._entity_type:
            name = get_vacation_name(today, self._country, self._region)
            if name:
                attrs["name"] = name

        elif "weekend" in self._entity_type:
            attrs["day_of_week"] = today.strftime("%A")
            attrs["day_number"] = today.weekday()

        elif "special_day" in self._entity_type:
            name = get_special_day_name(today, self._country)
            if name:
                attrs["name"] = name

        return attrs
