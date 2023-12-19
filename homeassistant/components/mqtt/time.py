"""Configure time in a device through MQTT topic."""

from __future__ import annotations

from collections.abc import Callable
from datetime import time
import logging

import voluptuous as vol

from homeassistant.components.time import (
    ATTR_ENABLE_SECOND,
    DOMAIN,
    ENTITY_ID_FORMAT,
    TimeEntity,
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

DEFAULT_NAME = "MQTT Time"
DEFAULT_PAYLOAD_RESET = "None"
DEFAULT_ENABLE_SECOND = False
CONF_ENABLE_SECOND = "enable_second"

MQTT_NUMBER_ATTRIBUTES_BLOCKED = frozenset(
    {
        ATTR_ENABLE_SECOND,
    }
)


_PLATFORM_SCHEMA_BASE = MQTT_RW_SCHEMA.extend(
    {
        vol.Optional(CONF_COMMAND_TEMPLATE): cv.template,
        vol.Optional(CONF_NAME): vol.Any(cv.string, None),
        vol.Optional(CONF_PAYLOAD_RESET, default=DEFAULT_PAYLOAD_RESET): cv.string,
        vol.Optional(CONF_VALUE_TEMPLATE): cv.template,
        vol.Optional(CONF_ENABLE_SECOND, default=DEFAULT_ENABLE_SECOND): vol.Coerce(
            bool
        ),
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
    """Set up MQTT time through YAML and through MQTT discovery."""
    async_setup_entity_entry_helper(
        hass,
        config_entry,
        MqttTime,
        DOMAIN,
        async_add_entities,
        DISCOVERY_SCHEMA,
        PLATFORM_SCHEMA_MODERN,
    )


class MqttTime(MqttEntity, TimeEntity):
    """representation of an MQTT time."""

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
        self._attr_enable_second_value = config[CONF_ENABLE_SECOND]

    @callback
    def _message_received(self, msg: ReceiveMessage) -> None:
        """Handle new MQTT messages."""
        time_value: time | None
        payload = str(self._value_template(msg.payload))
        if not payload.strip():
            _LOGGER.debug("Ignoring empty state update from '%s'", msg.topic)
            return
        try:
            if payload == self._config[CONF_PAYLOAD_RESET]:
                time_value = None
            else:
                time_value = dt_util.parse_time(payload)
        except ValueError:
            _LOGGER.warning("Payload '%s' is not a Time", msg.payload)
            return

        self._attr_native_value = time_value

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

    async def async_set_native_value(self, value: time) -> None:
        """Update the current value."""

        payload = self._command_template(value)

        if self._attr_assumed_state:
            self._attr_native_value = value
            self.async_write_ha_state()
        await self.async_publish_with_config(self._config[CONF_COMMAND_TOPIC], payload)
