"""Switcher integration Climate platform."""

from __future__ import annotations

from typing import Any, cast

from aioswitcher.api.remotes import SwitcherBreezeRemote
from aioswitcher.device import (
    DeviceCategory,
    DeviceState,
    SwitcherThermostat,
    ThermostatFanLevel,
    ThermostatMode,
    ThermostatSwing,
)

from homeassistant.components.climate import (
    FAN_AUTO,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    SWING_OFF,
    SWING_VERTICAL,
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SwitcherConfigEntry
from .const import SIGNAL_DEVICE_ADD
from .coordinator import SwitcherDataUpdateCoordinator
from .entity import SwitcherEntity
from .utils import get_breeze_remote_manager

API_CONTROL_BREEZE_DEVICE = "control_breeze_device"

DEVICE_MODE_TO_HA = {
    ThermostatMode.COOL: HVACMode.COOL,
    ThermostatMode.HEAT: HVACMode.HEAT,
    ThermostatMode.FAN: HVACMode.FAN_ONLY,
    ThermostatMode.DRY: HVACMode.DRY,
    ThermostatMode.AUTO: HVACMode.HEAT_COOL,
}

HA_TO_DEVICE_MODE = {value: key for key, value in DEVICE_MODE_TO_HA.items()}

DEVICE_FAN_TO_HA = {
    ThermostatFanLevel.LOW: FAN_LOW,
    ThermostatFanLevel.MEDIUM: FAN_MEDIUM,
    ThermostatFanLevel.HIGH: FAN_HIGH,
    ThermostatFanLevel.AUTO: FAN_AUTO,
}

HA_TO_DEVICE_FAN = {value: key for key, value in DEVICE_FAN_TO_HA.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: SwitcherConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Switcher climate from config entry."""

    async def async_add_climate(coordinator: SwitcherDataUpdateCoordinator) -> None:
        """Get remote and add climate from Switcher device."""
        data = cast(SwitcherThermostat, coordinator.data)
        if coordinator.data.device_type.category == DeviceCategory.THERMOSTAT:
            remote: SwitcherBreezeRemote = await hass.async_add_executor_job(
                get_breeze_remote_manager(hass).get_remote, data.remote_id
            )
            async_add_entities([SwitcherClimateEntity(coordinator, remote)])

    config_entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_DEVICE_ADD, async_add_climate)
    )


class SwitcherClimateEntity(SwitcherEntity, ClimateEntity):
    """Representation of a Switcher climate entity."""

    _attr_name = None

    def __init__(
        self, coordinator: SwitcherDataUpdateCoordinator, remote: SwitcherBreezeRemote
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._remote = remote

        self._attr_unique_id = f"{coordinator.device_id}-{coordinator.mac_address}"

        self._attr_min_temp = remote.min_temperature
        self._attr_max_temp = remote.max_temperature
        self._attr_target_temperature_step = 1
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS

        self._attr_hvac_modes = [HVACMode.OFF]
        for mode in remote.modes_features:
            self._attr_hvac_modes.append(DEVICE_MODE_TO_HA[mode])
            features = remote.modes_features[mode]

            if features["temperature_control"]:
                self._attr_supported_features |= ClimateEntityFeature.TARGET_TEMPERATURE

            if features["fan_levels"]:
                self._attr_supported_features |= ClimateEntityFeature.FAN_MODE

            if features["swing"] and not remote.separated_swing_command:
                self._attr_supported_features |= ClimateEntityFeature.SWING_MODE

        # There is always support for off + minimum one other mode so no need to check
        self._attr_supported_features |= (
            ClimateEntityFeature.TURN_OFF | ClimateEntityFeature.TURN_ON
        )
        self._update_data()

    def _update_data(self) -> None:
        """Update data from device."""
        data = cast(SwitcherThermostat, self.coordinator.data)
        features = self._remote.modes_features[data.mode]

        # Ignore empty update from device that was power cycled
        if data.target_temperature == 0 and self.target_temperature is not None:
            return

        self._attr_current_temperature = data.temperature
        self._attr_target_temperature = float(data.target_temperature)

        self._attr_hvac_mode = HVACMode.OFF
        if data.device_state == DeviceState.ON:
            self._attr_hvac_mode = DEVICE_MODE_TO_HA[data.mode]

        self._attr_fan_mode = None
        self._attr_fan_modes = []
        if features["fan_levels"]:
            self._attr_fan_modes = [DEVICE_FAN_TO_HA[x] for x in features["fan_levels"]]
            self._attr_fan_mode = DEVICE_FAN_TO_HA[data.fan_level]

        self._attr_swing_mode = None
        self._attr_swing_modes = []
        if features["swing"]:
            self._attr_swing_mode = SWING_OFF
            self._attr_swing_modes = [SWING_VERTICAL, SWING_OFF]
            if data.swing == ThermostatSwing.ON:
                self._attr_swing_mode = SWING_VERTICAL

    async def _async_control_breeze_device(self, **kwargs: Any) -> None:
        """Call Switcher Control Breeze API."""
        await self._async_call_api(API_CONTROL_BREEZE_DEVICE, self._remote, **kwargs)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        data = cast(SwitcherThermostat, self.coordinator.data)
        if not self._remote.modes_features[data.mode]["temperature_control"]:
            raise HomeAssistantError(
                "Current mode doesn't support setting Target Temperature"
            )

        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None:
            raise ValueError("No target temperature provided")

        await self._async_control_breeze_device(target_temp=int(temperature))

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set new target fan mode."""
        data = cast(SwitcherThermostat, self.coordinator.data)
        if not self._remote.modes_features[data.mode]["fan_levels"]:
            raise HomeAssistantError("Current mode doesn't support setting Fan Mode")

        await self._async_control_breeze_device(fan_level=HA_TO_DEVICE_FAN[fan_mode])

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new target operation mode."""
        if hvac_mode == hvac_mode.OFF:
            await self._async_control_breeze_device(state=DeviceState.OFF)
        else:
            await self._async_control_breeze_device(
                state=DeviceState.ON, mode=HA_TO_DEVICE_MODE[hvac_mode]
            )

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """Set new target swing operation."""
        data = cast(SwitcherThermostat, self.coordinator.data)
        if not self._remote.modes_features[data.mode]["swing"]:
            raise HomeAssistantError("Current mode doesn't support setting Swing Mode")

        if swing_mode == SWING_VERTICAL:
            await self._async_control_breeze_device(swing=ThermostatSwing.ON)
        else:
            await self._async_control_breeze_device(swing=ThermostatSwing.OFF)
