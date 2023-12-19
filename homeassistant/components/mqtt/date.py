"""Configure date in a device through MQTT topic."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
import logging

import voluptuous as vol

from homeassistant.components.date import DOMAIN, ENTITY_ID_FORMAT, DateEntity
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

DEFAULT_NAME = "MQTT Date"
DEFAULT_PAYLOAD_RESET = "None"


_PLATFORM_SCHEMA_BASE = MQTT_RW_SCHEMA.extend(
    {
        vol.Optional(CONF_COMMAND_TEMPLATE): cv.template,
        vol.Optional(CONF_NAME): vol.Any(cv.string, None),
        vol.Optional(CONF_PAYLOAD_RESET, default=DEFAULT_PAYLOAD_RESET): cv.string,
        vol.Optional(CONF_VALUE_TEMPLATE): cv.template,
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
    """Set up MQTT date through YAML and through MQTT discovery."""
    async_setup_entity_entry_helper(
        hass,
        config_entry,
        MqttDate,
        DOMAIN,
        async_add_entities,
        DISCOVERY_SCHEMA,
        PLATFORM_SCHEMA_MODERN,
    )


class MqttDate(MqttEntity, DateEntity):
    """representation of an MQTT date."""

    _default_name = DEFAULT_NAME
    _entity_id_format = ENTITY_ID_FORMAT

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

    @callback
    def _message_received(self, msg: ReceiveMessage) -> None:
        """Handle new MQTT messages."""
        date_value: date | None
        payload = str(self._value_template(msg.payload))
        if not payload.strip():
            _LOGGER.debug("Ignoring empty state update from '%s'", msg.topic)
            return
        try:
            if payload == self._config[CONF_PAYLOAD_RESET]:
                date_value = None
            else:
                date_value = dt_util.parse_date(payload)
        except ValueError:
            _LOGGER.warning("Payload '%s' is not a Date", msg.payload)
            return

        self._attr_native_value = date_value

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

    async def async_set_native_value(self, value: date) -> None:
        """Update the current value."""

        payload = self._command_template(value)

        if self._attr_assumed_state:
            self._attr_native_value = value
            self.async_write_ha_state()
        await self.async_publish_with_config(self._config[CONF_COMMAND_TOPIC], payload)
