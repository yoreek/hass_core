"""The tests for time_date sensor platform."""

from freezegun.api import FrozenDateTimeFactory
import pytest

import homeassistant.components.time_date.sensor as time_date
from homeassistant.core import HomeAssistant
import homeassistant.util.dt as dt_util

from . import load_int


async def test_intervals(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    """Test timing intervals of sensors."""
    device = time_date.TimeDateSensor("time", "1234567890")
    now = dt_util.utc_from_timestamp(45.5)
    freezer.move_to(now)
    next_time = device.get_next_interval()
    assert next_time == dt_util.parse_datetime("1971-01-01 00:01:00+00:00")

    device = time_date.TimeDateSensor("date_time", "1234567890")
    now = dt_util.utc_from_timestamp(1495068899)
    freezer.move_to(now)
    next_time = device.get_next_interval()
    assert next_time == dt_util.utc_from_timestamp(1495068900)

    now = dt_util.utcnow()
    device = time_date.TimeDateSensor("time_date", "1234567890")
    next_time = device.get_next_interval()
    assert next_time > now


@pytest.mark.freeze_time(dt_util.utc_from_timestamp(1495068856))
async def test_states(hass: HomeAssistant) -> None:
    """Test states of sensors."""
    hass.config.set_time_zone("UTC")
    await load_int(hass)

    state = hass.states.get("sensor.time")
    assert state.state == "00:54"

    state = hass.states.get("sensor.date")
    assert state.state == "2017-05-18"

    state = hass.states.get("sensor.time_utc")
    assert state.state == "00:54"

    state = hass.states.get("sensor.date_time")
    assert state.state == "2017-05-18, 00:54"

    state = hass.states.get("sensor.date_time_utc")
    assert state.state == "2017-05-18, 00:54"

    state = hass.states.get("sensor.date_time_iso")
    assert state.state == "2017-05-18T00:54:00"


@pytest.mark.freeze_time(dt_util.utc_from_timestamp(1495068856))
async def test_states_non_default_timezone(hass: HomeAssistant) -> None:
    """Test states of sensors in a timezone other than UTC."""
    hass.config.set_time_zone("America/New_York")
    await load_int(hass)

    state = hass.states.get("sensor.time")
    assert state.state == "20:54"

    state = hass.states.get("sensor.date")
    assert state.state == "2017-05-17"

    state = hass.states.get("sensor.time_utc")
    assert state.state == "00:54"

    state = hass.states.get("sensor.date_time")
    assert state.state == "2017-05-17, 20:54"

    state = hass.states.get("sensor.date_time_utc")
    assert state.state == "2017-05-18, 00:54"

    state = hass.states.get("sensor.date_time_iso")
    assert state.state == "2017-05-17T20:54:00"


async def test_timezone_intervals(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Test date sensor behavior in a timezone besides UTC."""
    hass.config.set_time_zone("America/New_York")

    device = time_date.TimeDateSensor("date", "1234567890")
    now = dt_util.utc_from_timestamp(50000)
    freezer.move_to(now)
    next_time = device.get_next_interval()
    # start of local day in EST was 18000.0
    # so the second day was 18000 + 86400
    assert next_time.timestamp() == 104400

    hass.config.set_time_zone("America/Edmonton")
    now = dt_util.parse_datetime("2017-11-13 19:47:19-07:00")
    device = time_date.TimeDateSensor("date", "1234567890")
    freezer.move_to(now)
    next_time = device.get_next_interval()
    assert next_time.timestamp() == dt_util.as_timestamp("2017-11-14 00:00:00-07:00")

    # Entering DST
    hass.config.set_time_zone("Europe/Prague")

    now = dt_util.parse_datetime("2020-03-29 00:00+01:00")
    freezer.move_to(now)
    next_time = device.get_next_interval()
    assert next_time.timestamp() == dt_util.as_timestamp("2020-03-30 00:00+02:00")

    now = dt_util.parse_datetime("2020-03-29 03:00+02:00")
    freezer.move_to(now)
    next_time = device.get_next_interval()
    assert next_time.timestamp() == dt_util.as_timestamp("2020-03-30 00:00+02:00")

    # Leaving DST
    now = dt_util.parse_datetime("2020-10-25 00:00+02:00")
    freezer.move_to(now)
    next_time = device.get_next_interval()
    assert next_time.timestamp() == dt_util.as_timestamp("2020-10-26 00:00:00+01:00")

    now = dt_util.parse_datetime("2020-10-25 23:59+01:00")
    freezer.move_to(now)
    next_time = device.get_next_interval()
    assert next_time.timestamp() == dt_util.as_timestamp("2020-10-26 00:00:00+01:00")


async def test_timezone_intervals_empty_parameter(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Test get_interval() without parameters."""
    freezer.move_to(dt_util.parse_datetime("2017-11-14 02:47:19-00:00"))
    hass.config.set_time_zone("America/Edmonton")
    device = time_date.TimeDateSensor("date", "1234567890")
    next_time = device.get_next_interval()
    assert next_time.timestamp() == dt_util.as_timestamp("2017-11-14 00:00:00-07:00")


async def test_icons(hass: HomeAssistant) -> None:
    """Test attributes of sensors."""
    await load_int(hass)
    state = hass.states.get("sensor.time")
    assert state.attributes["icon"] == "mdi:clock"
    state = hass.states.get("sensor.date")
    assert state.attributes["icon"] == "mdi:calendar"
    state = hass.states.get("sensor.date_time")
    assert state.attributes["icon"] == "mdi:calendar-clock"
    state = hass.states.get("sensor.date_time_utc")
    assert state.attributes["icon"] == "mdi:calendar-clock"
    state = hass.states.get("sensor.date_time_iso")
    assert state.attributes["icon"] == "mdi:calendar-clock"
