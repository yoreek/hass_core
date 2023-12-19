"""Configure duration in a device through MQTT topic."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
import logging

import voluptuous as vol

from homeassistant.components.duration import (
    ATTR_ENABLE_DAY,
    ATTR_ENABLE_MILLISECOND,
    DOMAIN,
    ENTITY_ID_FORMAT,
    DurationEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_DEVICE_CLASS,
    CONF_NAME,
    CONF_OPTIMISTIC,
    CONF_VALUE_TEMPLATE,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.service_info.mqtt import ReceivePayloadType
from homeassistant.helpers.typing import ConfigType, VolSchemaType
from homeassistant.util import dt as dt_util

from . import subscription
from .config import MQTT_RW_SCHEMA
from .const import (
    CONF_COMMAND_TEMPLATE,
    CONF_COMMAND_TOPIC,
    CONF_PAYLOAD_RESET,
    CONF_STATE_TOPIC,
)
from .mixins import MqttEntity, async_setup_entity_entry_helper
from .models import (
    MqttCommandTemplate,
    MqttValueTemplate,
    PublishPayloadType,
    ReceiveMessage,
)
from .schemas import MQTT_ENTITY_COMMON_SCHEMA

_LOGGER = logging.getLogger(__name__)

DEFAULT_NAME = "MQTT Duration"
DEFAULT_PAYLOAD_RESET = "None"
DEFAULT_ENABLE_DAY = False
DEFAULT_ENABLE_MILLISECOND = False
CONF_ENABLE_DAY = "enable_day"
CONF_ENABLE_MILLISECOND = "enable_millisecond"

MQTT_NUMBER_ATTRIBUTES_BLOCKED = frozenset(
    {
        ATTR_ENABLE_DAY,
        ATTR_ENABLE_MILLISECOND,
    }
)


_PLATFORM_SCHEMA_BASE = MQTT_RW_SCHEMA.extend(
    {
        vol.Optional(CONF_COMMAND_TEMPLATE): cv.template,
        vol.Optional(CONF_NAME): vol.Any(cv.string, None),
        vol.Optional(CONF_PAYLOAD_RESET, default=DEFAULT_PAYLOAD_RESET): cv.string,
        vol.Optional(CONF_VALUE_TEMPLATE): cv.template,
        vol.Optional(CONF_ENABLE_DAY, default=DEFAULT_ENABLE_DAY): vol.Coerce(bool),
        vol.Optional(
            CONF_ENABLE_MILLISECOND, default=DEFAULT_ENABLE_MILLISECOND
        ): vol.Coerce(bool),
    },
).extend(MQTT_ENTITY_COMMON_SCHEMA.schema)

PLATFORM_SCHEMA_MODERN = vol.All(
    _PLATFORM_SCHEMA_BASE,
)

DISCOVERY_SCHEMA = vol.All(
    _PLATFORM_SCHEMA_BASE.extend({}, extra=vol.REMOVE_EXTRA),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up MQTT datetime through YAML and through MQTT discovery."""
    async_setup_entity_entry_helper(
        hass,
        config_entry,
        MqttDatetime,
        DOMAIN,
        async_add_entities,
        DISCOVERY_SCHEMA,
        PLATFORM_SCHEMA_MODERN,
    )


class MqttDatetime(MqttEntity, DurationEntity):
    """representation of an MQTT duration."""

    _default_name = DEFAULT_NAME
    _entity_id_format = ENTITY_ID_FORMAT
    _attributes_extra_blocked = MQTT_NUMBER_ATTRIBUTES_BLOCKED

    _optimistic: bool
    _command_template: Callable[[PublishPayloadType], PublishPayloadType]
    _value_template: Callable[[ReceivePayloadType], ReceivePayloadType]

    @staticmethod
    def config_schema() -> VolSchemaType:
        """Return the config schema."""
        return DISCOVERY_SCHEMA

    def _setup_from_config(self, config: ConfigType) -> None:
        """(Re)Setup the entity."""
        self._config = config
        self._attr_assumed_state = config[CONF_OPTIMISTIC]

        self._command_template = MqttCommandTemplate(
            config.get(CONF_COMMAND_TEMPLATE), entity=self
        ).async_render
        self._value_template = MqttValueTemplate(
            config.get(CONF_VALUE_TEMPLATE),
            entity=self,
        ).async_render_with_possible_json_value

        self._attr_device_class = config.get(CONF_DEVICE_CLASS)
        self._attr_enable_day_value = config[CONF_ENABLE_DAY]
        self._attr_enable_millisecond_value = config[CONF_ENABLE_MILLISECOND]

    @callback
    def _message_received(self, msg: ReceiveMessage) -> None:
        """Handle new MQTT messages."""
        duration_value: timedelta | None
        payload = str(self._value_template(msg.payload))
        if not payload.strip():
            _LOGGER.debug("Ignoring empty state update from '%s'", msg.topic)
            return
        try:
            if payload == self._config[CONF_PAYLOAD_RESET]:
                duration_value = None
            else:
                duration_value = dt_util.parse_duration(payload)
        except ValueError:
            _LOGGER.warning("Payload '%s' is not a Duration", msg.payload)
            return

        self._attr_native_value = duration_value

    @callback
    def _prepare_subscribe_topics(self) -> None:
        """(Re)Subscribe to topics."""
        if not self.add_subscription(
            CONF_STATE_TOPIC, self._message_received, {"_attr_native_value"}
        ):
            # Force into optimistic mode.
            self._attr_assumed_state = True
            return

    async def _subscribe_topics(self) -> None:
        """(Re)Subscribe to topics."""
        subscription.async_subscribe_topics_internal(self.hass, self._sub_state)

    async def async_set_native_value(self, value: timedelta) -> None:
        """Update the current value."""

        payload = self._command_template(value)

        if self._attr_assumed_state:
            self._attr_native_value = value
            self.async_write_ha_state()
        await self.async_publish_with_config(self._config[CONF_COMMAND_TOPIC], payload)
