"""Support for PiSignage sensors."""
import logging
from datetime import datetime

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.const import PERCENTAGE, STATE_UNKNOWN
from homeassistant.const import UnitOfInformation

from .const import (
    DOMAIN,
    CONF_PLAYERS,
    CONF_IGNORE_CEC,
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
        entities.append(PiSignageStatusSensor(coordinator, player, entry))
        
        # Storage sensor
        entities.append(PiSignageStorageSensor(coordinator, player))
        
        # Additional sensors
        entities.append(PiSignageMyIpAddressSensor(coordinator, player))
        
        # Current playlist sensor
        entities.append(PiSignageCurrentPlaylistSensor(coordinator, player))
        
        # location sensor
        entities.append(PiSignagePlayerLocationSensor(coordinator, player))
    
    async_add_entities(entities, True)


class PiSignageBaseSensor(SensorEntity):
    """Base class for PiSignage sensors."""

    def __init__(self, coordinator, player, sensor_type):
        """Initialize the base sensor."""
        self.coordinator = coordinator
        self._player_id = player.get("_id")
        self._sensor_type = sensor_type
        self._unique_id = f"pisignage_{self._player_id}_{sensor_type}"
        self._player_name = player.get("name", f"PiSignage Player {self._player_id}")
        self._name = f"{self._player_name} {sensor_type.capitalize()}"
        
        # Register to coordinator updates
        self.coordinator = coordinator
        self._attr_should_poll = False
        self._attr_available = True

    async def async_added_to_hass(self):
        """When entity is added to hass."""
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )

    @property
    def _player_data(self):
        """Get the latest player data from the coordinator."""
        for player in self.coordinator.data.get(CONF_PLAYERS, []):
            if player.get("_id") == self._player_id:
                return player
        return {}

    @property
    def device_info(self):
        """Return device information for this entity."""
        return {
            "identifiers": {(DOMAIN, self._player_id)},
            "name": self._player_name,
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
        # Check if the player exists in coordinator data
        players = self.coordinator.data.get(CONF_PLAYERS, [])
        player_found = any(p.get("_id") == self._player_id for p in players)
        return player_found and self.coordinator.last_update_success
    
    # Remove async_update method - we're using coordinator


class PiSignageStatusSensor(PiSignageBaseSensor):
    """Representation of a PiSignage status sensor."""

    def __init__(self, coordinator, player, config_entry):
        """Initialize the status sensor."""
        super().__init__(coordinator, player, "status")
        # We don't need to store the config_entry explicitly anymore
        # The reference is used directly from the media_player.py implementation

    @property
    def state(self) -> str:
        """Return the state of the sensor."""
        player_data = self._player_data
        is_connected = player_data.get("isConnected", False)
        
        # Access the config_entry directly from the hass context to avoid deprecation warnings
        config_entry = self.hass.config_entries.async_get_entry(self.registry_entry.config_entry_id)
        ignore_cec = config_entry.options.get(CONF_IGNORE_CEC, {}).get(self._player_id, False)
        
        is_cec_supported = player_data.get("isCecSupported", False) and not ignore_cec
        cec_tv_status = player_data.get("cecTvStatus", False)
        playlist_on = player_data.get("playlistOn", False)

        if not is_connected:
            return "Offline"
        if not is_cec_supported:
            return "Playing (No CEC)" if playlist_on else "Not Playing (No CEC)"
        if not cec_tv_status:
            return "TV Powered Off"
        if playlist_on:
            return "Playing"
        return "Not Playing"

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


class PiSignageCurrentPlaylistSensor(PiSignageBaseSensor):
    """Representation of a PiSignage current playlist sensor."""

    def __init__(self, coordinator, player):
        """Initialize the current playlist sensor."""
        super().__init__(coordinator, player, "current_playlist")

    @property
    def state(self) -> str:
        """Return the state of the sensor."""
        playlist_on = self._player_data.get("playlistOn", False)
        current_playlist = self._player_data.get("currentPlaylist", "")
        
        if not playlist_on or not current_playlist:
            return "Not Playing"
        
        return current_playlist

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return f"{self._player_name} Current Playlist"


class PiSignagePlayerLocationSensor(PiSignageBaseSensor):
    """Representation of a PiSignage player location sensor."""

    def __init__(self, coordinator, player):
        """Initialize the player location sensor."""
        super().__init__(coordinator, player, "player_location")

    @property
    def state(self) -> str:
        """Return the state of the sensor."""
        return self._player_data.get("configLocation", STATE_UNKNOWN).strip()

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return f"{self._player_name} Location"