"""Config flow for the Phomemo T02."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import callback

from .const import (
    CONF_CHUNK_DELAY_MS,
    CONF_CHUNK_SIZE,
    CONF_IDLE_DISCONNECT_S,
    DEFAULT_CHUNK_DELAY_MS,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_IDLE_DISCONNECT_S,
    DOMAIN,
    LOCAL_NAME,
)


def _is_t02(info: BluetoothServiceInfoBleak) -> bool:
    """The T02 does not advertise its service UUID, so match on the name."""
    return (info.name or "").upper().startswith(LOCAL_NAME)


class PhomemoConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle discovery and manual setup."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovered: dict[str, str] = {}
        self._address: str | None = None

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle a printer found by the Bluetooth integration."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()

        self._address = discovery_info.address
        self.context["title_placeholders"] = {"name": discovery_info.name or LOCAL_NAME}
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm adding a discovered printer."""
        assert self._address is not None
        if user_input is not None:
            return self.async_create_entry(
                title=f"Phomemo {LOCAL_NAME}", data={CONF_ADDRESS: self._address}
            )

        self._set_confirm_only()
        return self.async_show_form(
            step_id="confirm",
            description_placeholders={"address": self._address},
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick from nearby printers, or enter an address by hand."""
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=f"Phomemo {LOCAL_NAME}", data={CONF_ADDRESS: address}
            )

        current = self._async_current_ids()
        for info in async_discovered_service_info(self.hass, connectable=True):
            if info.address in current or not _is_t02(info):
                continue
            self._discovered[info.address] = f"{info.name} ({info.address})"

        if not self._discovered:
            return self.async_abort(reason="no_devices_found")

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_ADDRESS): vol.In(self._discovered)}),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> PhomemoOptionsFlow:
        """Return the options flow."""
        return PhomemoOptionsFlow()


class PhomemoOptionsFlow(OptionsFlow):
    """Tune the BLE transport.

    Defaults suit a local adapter (measured MTU 200). Throughput through an
    ESPHome proxy is lower, so raising the delay or lowering the chunk size is
    the fix if prints come out garbled or time out.
    """

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        options = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_CHUNK_SIZE,
                        default=options.get(CONF_CHUNK_SIZE, DEFAULT_CHUNK_SIZE),
                    ): vol.All(vol.Coerce(int), vol.Range(min=20, max=512)),
                    vol.Optional(
                        CONF_CHUNK_DELAY_MS,
                        default=options.get(CONF_CHUNK_DELAY_MS, DEFAULT_CHUNK_DELAY_MS),
                    ): vol.All(vol.Coerce(int), vol.Range(min=0, max=200)),
                    vol.Optional(
                        CONF_IDLE_DISCONNECT_S,
                        default=options.get(
                            CONF_IDLE_DISCONNECT_S, DEFAULT_IDLE_DISCONNECT_S
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=5, max=600)),
                }
            ),
        )
