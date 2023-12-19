"""Component to allow setting duration as platforms."""

from __future__ import annotations

from datetime import timedelta
from functools import cached_property
import logging
from typing import Any, final

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity import Entity, EntityDescription
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.typing import ConfigType

from .const import (
    ATTR_DURATION,
    ATTR_ENABLE_DAY,
    ATTR_ENABLE_MILLISECOND,
    DEFAULT_ENABLE_DAY_VALUE,
    DEFAULT_ENABLE_MILLISECOND_VALUE,
    DOMAIN,
    SERVICE_SET_VALUE,
)

SCAN_INTERVAL = timedelta(seconds=30)

ENTITY_ID_FORMAT = DOMAIN + ".{}"

_LOGGER = logging.getLogger(__name__)

ENTITY_ID_FORMAT = DOMAIN + ".{}"
PLATFORM_SCHEMA = cv.PLATFORM_SCHEMA
PLATFORM_SCHEMA_BASE = cv.PLATFORM_SCHEMA_BASE
SCAN_INTERVAL = timedelta(seconds=30)


__all__ = [
    "ATTR_DURATION",
    "ATTR_ENABLE_DAY",
    "ATTR_ENABLE_MILLISECOND",
    "DEFAULT_ENABLE_DAY_VALUE",
    "DEFAULT_ENABLE_MILLISECOND_VALUE",
    "DOMAIN",
    "DurationEntity",
    "DurationEntityDescription",
]


async def _async_set_value(entity: DurationEntity, service_call: ServiceCall) -> None:
    """Service call wrapper to set a new duration."""
    return await entity.async_set_native_value(service_call.data[ATTR_DURATION])


async def async_set_value(entity: DurationEntity, service_call: ServiceCall) -> None:
    """Service call wrapper to set a new value."""
    value = service_call.data["value"]
    await entity.async_set_native_value(value)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up Duration entities."""
    component = hass.data[DOMAIN] = EntityComponent[DurationEntity](
        _LOGGER, DOMAIN, hass, SCAN_INTERVAL
    )
    await component.async_setup(config)

    component.async_register_entity_service(
        SERVICE_SET_VALUE,
        {
            vol.Required(ATTR_DURATION): cv.duration,
        },
        _async_set_value,
    )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a config entry."""
    component: EntityComponent[DurationEntity] = hass.data[DOMAIN]
    return await component.async_setup_entry(entry)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    component: EntityComponent[DurationEntity] = hass.data[DOMAIN]
    return await component.async_unload_entry(entry)


class DurationEntityDescription(EntityDescription, frozen_or_thawed=True):
    """A class that describes duration entities."""


CACHED_PROPERTIES_WITH_ATTR_ = {
    "native_value",
}


class DurationEntity(Entity, cached_properties=CACHED_PROPERTIES_WITH_ATTR_):
    """Representation of a Duration entity."""

    _entity_component_unrecorded_attributes = frozenset(
        {ATTR_ENABLE_DAY, ATTR_ENABLE_MILLISECOND}
    )

    entity_description: DurationEntityDescription
    _attr_enable_day_value: bool | None = None
    _attr_enable_millisecond_value: bool | None = None
    _attr_native_value: timedelta | None = None
    _attr_device_class: None = None
    _attr_state: None = None

    @cached_property
    @final
    def device_class(self) -> None:
        """Return entity device class."""
        return None

    @cached_property
    @final
    def state_attributes(self) -> None:
        """Return the state attributes."""
        return None

    @property
    @final
    def state(self) -> str | None:
        """Return the entity state."""
        if self.native_value is None:
            return None
        return str(self.native_value)

    @cached_property
    def native_value(self) -> timedelta | None:
        """Return the value reported by the duration."""
        return self._attr_native_value

    def set_native_value(self, value: timedelta) -> None:
        """Set new value."""
        raise NotImplementedError

    async def async_set_native_value(self, value: timedelta) -> None:
        """Set new value."""
        await self.hass.async_add_executor_job(self.set_native_value, value)

    def set_value(self, value: timedelta) -> None:
        """Change the duration."""
        raise NotImplementedError

    async def async_set_value(self, value: timedelta) -> None:
        """Change the duration."""
        await self.hass.async_add_executor_job(self.set_value, value)

    @property
    @final
    def enable_day_value(self) -> bool | None:
        """Return the enable day value."""
        if hasattr(self, "_attr_enable_day_value"):
            return self._attr_enable_day_value
        return DEFAULT_ENABLE_DAY_VALUE

    @property
    @final
    def enable_millisecond_value(self) -> bool | None:
        """Return the enable millisecond value."""
        if hasattr(self, "_attr_enable_millisecond_value"):
            return self._attr_enable_millisecond_value
        return DEFAULT_ENABLE_MILLISECOND_VALUE

    @property
    def capability_attributes(self) -> dict[str, Any]:
        """Return capability attributes."""
        return {
            ATTR_ENABLE_DAY: self.enable_day_value,
            ATTR_ENABLE_MILLISECOND: self.enable_millisecond_value,
        }
