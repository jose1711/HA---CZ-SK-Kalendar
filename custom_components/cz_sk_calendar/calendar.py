"""Calendar platform for CZ/SK School & Work Calendar."""
from __future__ import annotations

from datetime import datetime, timedelta
import logging

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import (
    CONF_CUSTOM_BIRTHDAYS,
    CONF_CUSTOM_HOLIDAYS,
    CONF_CUSTOM_EVENTS,
    COUNTRY_CZ,
    DOMAIN,
    CZ_REGIONS,
    SK_REGIONS,
)
from .core import (
    get_all_holidays,
    get_all_vacations,
    get_holiday_name,
    get_nameday,
    get_school_year,
    get_vacation_name,
)
from .entity import get_configured_country, get_configured_region
from .sensor import _parse_custom_list, _get_custom_event_name, _get_next_custom_event

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the CZ/SK Calendar entities."""
    country = get_configured_country(config_entry)
    region = get_configured_region(config_entry)

    calendars = [
        CZSKHolidayCalendar(config_entry, country, region),
        CZSKVacationCalendar(config_entry, country, region),
        CZSKCombinedCalendar(config_entry, country, region),
        CZSKCustomEventsCalendar(config_entry, country, region),
        CZSKNamedayCalendar(config_entry, country, region),
    ]

    async_add_entities(calendars, True)


class CZSKBaseCalendar(CalendarEntity):
    """Base class for CZ/SK Calendar entities."""

    # Kept in sync with CZSKEntity: with has_entity_name enabled Home Assistant
    # prefixes the object id with the device name, which would produce ids like
    # calendar.cz_sk_calendar_ceska_republika_praha_1_5_svatky.
    _attr_has_entity_name = False

    def __init__(
        self,
        config_entry: ConfigEntry,
        country: str,
        region: str,
        calendar_type: str,
        name: str,
    ) -> None:
        """Initialize the calendar."""
        self._config_entry = config_entry
        self._country = country
        self._region = region
        self._calendar_type = calendar_type

        self._region_name = (
            CZ_REGIONS.get(region, region)
            if country == COUNTRY_CZ
            else SK_REGIONS.get(region, region)
        )

        self._attr_unique_id = f"{config_entry.entry_id}_{calendar_type}"
        self._attr_name = name
        self._event: CalendarEvent | None = None

    @property
    def suggested_object_id(self) -> str:
        """Return a stable, language-independent object id.

        See ``CZSKEntity.suggested_object_id`` - without this the id would be
        built from the localized name and the device name, producing ids like
        ``calendar.cz_sk_calendar_ceska_republika_praha_1_5_svatky``.
        """
        return self._calendar_type

    @property
    def device_info(self):
        """Return device info."""
        return {
            "identifiers": {(DOMAIN, self._config_entry.entry_id)},
            "name": f"CZ/SK Calendar ({self._config_entry.title})",
            "manufacturer": "CZ/SK Calendar",
            "model": f"{self._country} Calendar",
        }


class CZSKHolidayCalendar(CZSKBaseCalendar):
    """Calendar for holidays."""

    def __init__(
        self, config_entry: ConfigEntry, country: str, region: str
    ) -> None:
        """Initialize the holiday calendar."""
        name = "Svátky" if country == COUNTRY_CZ else "Sviatky"
        super().__init__(config_entry, country, region, "holidays", name)

    @property
    def event(self) -> CalendarEvent | None:
        """Return the current or next upcoming event."""
        today = dt_util.now().date()
        holiday_name = get_holiday_name(today, self._country)

        if holiday_name:
            return CalendarEvent(
                start=today,
                end=today + timedelta(days=1),
                summary=holiday_name,
            )

        # Find next holiday
        holidays = get_all_holidays(today.year, self._country)
        holidays.update(get_all_holidays(today.year + 1, self._country))

        for holiday_date in sorted(holidays.keys()):
            if holiday_date > today:
                return CalendarEvent(
                    start=holiday_date,
                    end=holiday_date + timedelta(days=1),
                    summary=holidays[holiday_date],
                )

        return None

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Return calendar events within a datetime range."""
        events = []

        start = start_date.date() if isinstance(start_date, datetime) else start_date
        end = end_date.date() if isinstance(end_date, datetime) else end_date

        # Get holidays for all years in range
        years = set()
        current = start
        while current <= end:
            years.add(current.year)
            current += timedelta(days=365)
        years.add(end.year)

        all_holidays = {}
        for year in years:
            all_holidays.update(get_all_holidays(year, self._country))

        for holiday_date, name in sorted(all_holidays.items()):
            if start <= holiday_date <= end:
                events.append(
                    CalendarEvent(
                        start=holiday_date,
                        end=holiday_date + timedelta(days=1),
                        summary=name,
                    )
                )

        return events


class CZSKVacationCalendar(CZSKBaseCalendar):
    """Calendar for school vacations."""

    def __init__(
        self, config_entry: ConfigEntry, country: str, region: str
    ) -> None:
        """Initialize the vacation calendar."""
        name = "Školní prázdniny" if country == COUNTRY_CZ else "Školské prázdniny"
        super().__init__(config_entry, country, region, "vacations", name)

    @property
    def event(self) -> CalendarEvent | None:
        """Return the current or next upcoming event."""
        today = dt_util.now().date()
        vacation_name = get_vacation_name(today, self._country, self._region)

        if vacation_name:
            # Find the end of current vacation
            current = today
            while get_vacation_name(current, self._country, self._region) == vacation_name:
                current += timedelta(days=1)
            # Find the start of current vacation
            start = today
            while get_vacation_name(start - timedelta(days=1), self._country, self._region) == vacation_name:
                start -= timedelta(days=1)

            return CalendarEvent(
                start=start,
                end=current,
                summary=vacation_name,
            )

        # Find next vacation
        school_year = get_school_year(today)
        vacations = get_all_vacations(school_year, self._country, self._region)
        vacations.extend(get_all_vacations(school_year + 1, self._country, self._region))

        for start_date, end_date, name in sorted(vacations, key=lambda x: x[0]):
            if start_date > today:
                return CalendarEvent(
                    start=start_date,
                    end=end_date + timedelta(days=1),
                    summary=name,
                )

        return None

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Return calendar events within a datetime range."""
        events = []

        start = start_date.date() if isinstance(start_date, datetime) else start_date
        end = end_date.date() if isinstance(end_date, datetime) else end_date

        # Get school years in range
        start_school_year = get_school_year(start)
        end_school_year = get_school_year(end)

        all_vacations = []
        for year in range(start_school_year - 1, end_school_year + 2):
            all_vacations.extend(get_all_vacations(year, self._country, self._region))

        # Remove duplicates and filter by date range
        seen = set()
        for start_date_v, end_date_v, name in sorted(all_vacations, key=lambda x: x[0]):
            key = (start_date_v, end_date_v, name)
            if key in seen:
                continue
            seen.add(key)

            # Check if vacation overlaps with requested range
            if end_date_v >= start and start_date_v <= end:
                events.append(
                    CalendarEvent(
                        start=start_date_v,
                        end=end_date_v + timedelta(days=1),
                        summary=name,
                    )
                )

        return events


class CZSKCombinedCalendar(CZSKBaseCalendar):
    """Combined calendar for holidays and vacations."""

    def __init__(
        self, config_entry: ConfigEntry, country: str, region: str
    ) -> None:
        """Initialize the combined calendar."""
        name = "Svátky a prázdniny" if country == COUNTRY_CZ else "Sviatky a prázdniny"
        super().__init__(config_entry, country, region, "combined", name)

    @property
    def event(self) -> CalendarEvent | None:
        """Return the current or next upcoming event."""
        today = dt_util.now().date()

        # Check for holiday first
        holiday_name = get_holiday_name(today, self._country)
        if holiday_name:
            return CalendarEvent(
                start=today,
                end=today + timedelta(days=1),
                summary=f"🎉 {holiday_name}",
            )

        # Check for vacation
        vacation_name = get_vacation_name(today, self._country, self._region)
        if vacation_name:
            current = today
            while get_vacation_name(current, self._country, self._region) == vacation_name:
                current += timedelta(days=1)
            start = today
            while get_vacation_name(start - timedelta(days=1), self._country, self._region) == vacation_name:
                start -= timedelta(days=1)

            return CalendarEvent(
                start=start,
                end=current,
                summary=f"🏖️ {vacation_name}",
            )

        # Find next event
        # Get next holiday
        holidays = get_all_holidays(today.year, self._country)
        holidays.update(get_all_holidays(today.year + 1, self._country))

        next_holiday_date = None
        next_holiday_name = None
        for holiday_date in sorted(holidays.keys()):
            if holiday_date > today:
                next_holiday_date = holiday_date
                next_holiday_name = holidays[holiday_date]
                break

        # Get next vacation
        school_year = get_school_year(today)
        vacations = get_all_vacations(school_year, self._country, self._region)
        vacations.extend(get_all_vacations(school_year + 1, self._country, self._region))

        next_vacation = None
        for start_date, end_date, name in sorted(vacations, key=lambda x: x[0]):
            if start_date > today:
                next_vacation = (start_date, end_date, name)
                break

        # Return the earlier event
        if next_holiday_date and next_vacation:
            if next_holiday_date <= next_vacation[0]:
                return CalendarEvent(
                    start=next_holiday_date,
                    end=next_holiday_date + timedelta(days=1),
                    summary=f"🎉 {next_holiday_name}",
                )
            else:
                return CalendarEvent(
                    start=next_vacation[0],
                    end=next_vacation[1] + timedelta(days=1),
                    summary=f"🏖️ {next_vacation[2]}",
                )
        elif next_holiday_date:
            return CalendarEvent(
                start=next_holiday_date,
                end=next_holiday_date + timedelta(days=1),
                summary=f"🎉 {next_holiday_name}",
            )
        elif next_vacation:
            return CalendarEvent(
                start=next_vacation[0],
                end=next_vacation[1] + timedelta(days=1),
                summary=f"🏖️ {next_vacation[2]}",
            )

        return None

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Return calendar events within a datetime range."""
        events = []

        start = start_date.date() if isinstance(start_date, datetime) else start_date
        end = end_date.date() if isinstance(end_date, datetime) else end_date

        # Get holidays
        years = set()
        current = start
        while current <= end:
            years.add(current.year)
            current += timedelta(days=365)
        years.add(end.year)

        for year in years:
            holidays = get_all_holidays(year, self._country)
            for holiday_date, name in holidays.items():
                if start <= holiday_date <= end:
                    events.append(
                        CalendarEvent(
                            start=holiday_date,
                            end=holiday_date + timedelta(days=1),
                            summary=f"🎉 {name}",
                        )
                    )

        # Get vacations
        start_school_year = get_school_year(start)
        end_school_year = get_school_year(end)

        seen = set()
        for year in range(start_school_year - 1, end_school_year + 2):
            vacations = get_all_vacations(year, self._country, self._region)
            for start_date_v, end_date_v, name in vacations:
                key = (start_date_v, end_date_v, name)
                if key in seen:
                    continue
                seen.add(key)

                if end_date_v >= start and start_date_v <= end:
                    events.append(
                        CalendarEvent(
                            start=start_date_v,
                            end=end_date_v + timedelta(days=1),
                            summary=f"🏖️ {name}",
                        )
                    )

        # Sort by start date
        events.sort(key=lambda x: x.start)
        return events


class CZSKCustomEventsCalendar(CZSKBaseCalendar):
    """Calendar for custom events (birthdays & family holidays)."""

    def __init__(
        self, config_entry: ConfigEntry, country: str, region: str
    ) -> None:
        """Initialize the custom events calendar."""
        name = "Vlastní události" if country == COUNTRY_CZ else "Vlastné udalosti"
        super().__init__(config_entry, country, region, "custom_events", name)
        self._config_entry = config_entry

    def _get_all_custom_events(self) -> list[dict]:
        """Parse and return all custom events from config."""
        options = self._config_entry.options
        raw_birthdays = options.get(CONF_CUSTOM_BIRTHDAYS, "")
        raw_holidays = options.get(CONF_CUSTOM_HOLIDAYS, "")
        legacy_events = options.get(CONF_CUSTOM_EVENTS, "")

        events = _parse_custom_list(raw_birthdays)
        holidays = _parse_custom_list(raw_holidays)
        if legacy_events and not holidays:
            holidays = _parse_custom_list(legacy_events)

        # Tag events with type for emoji display
        for e in events:
            e["type"] = "birthday"
        for e in holidays:
            e["type"] = "holiday"

        return events + holidays

    @property
    def event(self) -> CalendarEvent | None:
        """Return the current or next upcoming event."""
        today = dt_util.now().date()
        all_events = self._get_all_custom_events()

        if not all_events:
            return None

        # Check today
        name = _get_custom_event_name(today, all_events)
        if name:
            return CalendarEvent(
                start=today,
                end=today + timedelta(days=1),
                summary=name,
            )

        # Find next custom event
        next_date, next_name = _get_next_custom_event(today + timedelta(days=1), all_events)
        if next_date and next_name:
            return CalendarEvent(
                start=next_date,
                end=next_date + timedelta(days=1),
                summary=next_name,
            )

        return None

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Return calendar events within a datetime range."""
        events = []
        all_custom = self._get_all_custom_events()

        if not all_custom:
            return events

        start = start_date.date() if isinstance(start_date, datetime) else start_date
        end = end_date.date() if isinstance(end_date, datetime) else end_date

        current = start
        while current <= end:
            name = _get_custom_event_name(current, all_custom)
            if name:
                events.append(
                    CalendarEvent(
                        start=current,
                        end=current + timedelta(days=1),
                        summary=name,
                    )
                )
            current += timedelta(days=1)

        return events


class CZSKNamedayCalendar(CZSKBaseCalendar):
    """Calendar for name days (jmeniny / meniny)."""

    def __init__(
        self, config_entry: ConfigEntry, country: str, region: str
    ) -> None:
        """Initialize the nameday calendar."""
        name = "Jmeniny" if country == COUNTRY_CZ else "Meniny"
        super().__init__(config_entry, country, region, "namedays", name)

    @property
    def event(self) -> CalendarEvent | None:
        """Return today's nameday, or the next day that carries one."""
        today = dt_util.now().date()

        for offset in range(366):
            current = today + timedelta(days=offset)
            nameday = get_nameday(current, self._country)
            if nameday:
                return CalendarEvent(
                    start=current,
                    end=current + timedelta(days=1),
                    summary=nameday,
                )

        return None

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Return calendar events within a datetime range."""
        events = []

        start = start_date.date() if isinstance(start_date, datetime) else start_date
        end = end_date.date() if isinstance(end_date, datetime) else end_date

        current = start
        while current <= end:
            nameday = get_nameday(current, self._country)
            if nameday:
                events.append(
                    CalendarEvent(
                        start=current,
                        end=current + timedelta(days=1),
                        summary=nameday,
                    )
                )
            current += timedelta(days=1)

        return events
