"""Tests for the time_date component."""

from homeassistant.components.time_date.const import DOMAIN
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_DISPLAY_OPTIONS
from homeassistant.core import HomeAssistant

from tests.common import MockConfigEntry


async def load_int(hass: HomeAssistant) -> MockConfigEntry:
    """Set up the Time & Date integration in Home Assistant."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        source=SOURCE_USER,
        data={},
        options={
            CONF_DISPLAY_OPTIONS: [
                "time",
                "date",
                "date_time",
                "date_time_utc",
                "date_time_iso",
                "time_date",
                "beat",
                "time_utc",
            ]
        },
        entry_id="1234567890",
    )

    config_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    return config_entry
