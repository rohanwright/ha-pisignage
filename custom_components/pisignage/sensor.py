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
        if self._player_data.get("connectionCount", 0) < 1:
            return "Disconnected"
        if self._player_data.get("playlistOn"):
            return "Playing"
        return "Idle"

    @property
    def extra_state_attributes(self) -> dict:
        """Return the state attributes."""
        attrs = {}
        
        if version := self._player_data.get("version"):
            attrs[ATTR_VERSION] = version
            
        if ip := self._player_data.get("ip"):
            attrs[ATTR_IP] = ip
            
        if last_seen := self._player_data.get("lastReported"):
            try:
                last_seen_dt = datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
                attrs[ATTR_LAST_SEEN] = last_seen_dt
            except (ValueError, AttributeError):
                attrs[ATTR_LAST_SEEN] = last_seen
            
        return attrs


class PiSignageStorageSensor(PiSignageBaseSensor):
    """Representation of a PiSignage storage sensor."""

    def __init__(self, coordinator, player):
        """Initialize the storage sensor."""
        super().__init__(coordinator, player, "storage")

    @property
    def device_class(self) -> str:
        """Return the device class of the sensor."""
        return SensorDeviceClass.DATA_SIZE

    @property
    def state(self) -> float:
        """Return the state of the sensor."""
        try:
            # Convert from GB to MB for consistent unit presentation
            free_space_gb = float(self._player_data.get("diskSpaceAvailable", "0G").replace("G", ""))
            return free_space_gb * 1024  # Convert GB to MB
        except (ValueError, TypeError):
            return None

    @property
    def native_unit_of_measurement(self) -> str:
        """Return the unit of measurement."""
        return UnitOfInformation.MEGABYTES

    @property
    def extra_state_attributes(self) -> dict:
        """Return the state attributes."""
        attrs = {}
        storage_data = self._player_data
        
        if free := storage_data.get("diskSpaceAvailable"):
            attrs[ATTR_FREE_SPACE] = free
            
        if used := storage_data.get("diskSpaceUsed"):
            attrs["used_space"] = used
            
        return attrs