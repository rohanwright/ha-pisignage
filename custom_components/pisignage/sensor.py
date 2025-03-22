"""Support for PiSignage sensors."""
import logging
from datetime import datetime

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.const import PERCENTAGE, STATE_UNKNOWN
from homeassistant.const import UnitOfInformation

from .const import (
    DOMAIN,
    CONF_PLAYERS,
    ATTR_VERSION,
    ATTR_IP,
    ATTR_LAST_SEEN,
    ATTR_FREE_SPACE,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the PiSignage sensors."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    
    players = coordinator.data.get(CONF_PLAYERS, [])
    entities = []
    
    for player in players:
        # Status sensor
        entities.append(PiSignageStatusSensor(coordinator, player))
        
        # Storage sensor
        entities.append(PiSignageStorageSensor(coordinator, player))
        
        # Additional sensors
        entities.append(PiSignageMyIpAddressSensor(coordinator, player))

    
    async_add_entities(entities, True)


class PiSignageBaseSensor(SensorEntity):
    """Base class for PiSignage sensors."""

    def __init__(self, coordinator, player, sensor_type):
        """Initialize the base sensor."""
        self.coordinator = coordinator
        self._player_id = player.get("_id")
        self._player_data = player
        self._sensor_type = sensor_type
        self._unique_id = f"pisignage_{self._player_id}_{sensor_type}"
        self._player_name = player.get("name", f"PiSignage Player {self._player_id}")
        self._name = f"{self._player_name} {sensor_type.capitalize()}"
        self._available = True

    @property
    def device_info(self):
        """Return device information for this entity."""
        return {
            "identifiers": {(DOMAIN, self._player_id)},
            "name": self._player_name,
            "manufacturer": "PiSignage",
            "model": "PiSignage Player",
        }

    @property
    def unique_id(self) -> str:
        """Return the unique ID of the sensor."""
        return self._unique_id

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return self._name

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self._available and self.coordinator.last_update_success

    async def async_update(self) -> None:
        """Update the sensor."""
        await self.coordinator.async_request_refresh()
        players = self.coordinator.data.get(CONF_PLAYERS, [])
        
        for player in players:
            if player.get("_id") == self._player_id:
                self._player_data = player
                self._available = True
                return
                
        self._available = False


class PiSignageStatusSensor(PiSignageBaseSensor):
    """Representation of a PiSignage status sensor."""

    def __init__(self, coordinator, player):
        """Initialize the status sensor."""
        super().__init__(coordinator, player, "status")

    @property
    def state(self) -> str:
        """Return the state of the sensor."""
        is_connected = self._player_data.get("isConnected", False)
        is_cec_supported = self._player_data.get("isCecSupported", False)
        cec_tv_status = self._player_data.get("cecTvStatus", False)
        playlist_on = self._player_data.get("playlistOn", False)

        if not is_connected:
            return "Offline"
        if not is_cec_supported:
            return "Playing" if playlist_on else "Not Playing"
        if not cec_tv_status:
            return "TV Powered Off"
        if playlist_on:
            return "Playing (No TV Control)"
        return "Not Playing (No TV Control)"

    @property
    def extra_state_attributes(self) -> dict:
        """Return the state attributes."""
        attrs = {}
        
        if version := self._player_data.get("version"):
            attrs[ATTR_VERSION] = version
            
        if ip := self._player_data.get("myIpAddress"):
            attrs[ATTR_IP] = ip
            
        if last_seen := self._player_data.get("lastReported"):
            try:
                last_seen_dt = datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
                attrs[ATTR_LAST_SEEN] = last_seen_dt
            except (ValueError, AttributeError):
                attrs[ATTR_LAST_SEEN] = last_seen

        # Add additional attributes with user-friendly names
        attrs["Is Connected"] = self._player_data.get("isConnected", False)
        attrs["CEC Supported"] = self._player_data.get("isCecSupported", False)
        attrs["CEC TV Status"] = self._player_data.get("cecTvStatus", False)
        attrs["Playlist Active"] = self._player_data.get("playlistOn", False)
        
        return attrs

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return f"{self._player_name} Status"


class PiSignageStorageSensor(PiSignageBaseSensor):
    """Representation of a PiSignage storage sensor."""

    def __init__(self, coordinator, player):
        """Initialize the storage sensor."""
        super().__init__(coordinator, player, "storage")

    @property
    def state(self) -> float:
        """Return the state of the sensor."""
        try:
            used_space_percentage = float(self._player_data.get("diskSpaceUsed", "0%").replace("%", ""))
            return used_space_percentage  # Return used space percentage
        except (ValueError, TypeError):
            return None

    @property
    def native_unit_of_measurement(self) -> str:
        """Return the unit of measurement."""
        return PERCENTAGE

    @property
    def extra_state_attributes(self) -> dict:
        """Return the state attributes."""
        attrs = {}
        storage_data = self._player_data
        
        if free := storage_data.get("diskSpaceAvailable"):
            attrs[ATTR_FREE_SPACE] = free
            
        return attrs

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return f"{self._player_name} Storage Usage"


class PiSignageMyIpAddressSensor(PiSignageBaseSensor):
    """Representation of a PiSignage myIpAddress sensor."""

    def __init__(self, coordinator, player):
        """Initialize the myIpAddress sensor."""
        super().__init__(coordinator, player, "myIpAddress")

    @property
    def state(self) -> str:
        """Return the state of the sensor."""
        return self._player_data.get("myIpAddress", STATE_UNKNOWN).strip()

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return f"{self._player_name} Player IP"