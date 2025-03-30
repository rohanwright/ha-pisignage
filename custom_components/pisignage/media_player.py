"""Support for PiSignage media players."""
import logging
from typing import Any, Dict, List, Optional

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
)
from homeassistant.components.media_player.const import (
    MediaType,
)
from homeassistant.const import (
    STATE_IDLE,
    STATE_OFF,
    STATE_ON,
    STATE_PLAYING,
    STATE_UNKNOWN,
    STATE_PAUSED,
    STATE_STANDBY,
)

from .const import (
    DOMAIN,
    CONF_PLAYERS,
    CONF_IGNORE_CEC,
    ATTR_PLAYLISTS,
    ATTR_GROUP,
    ATTR_STATUS,
    ATTR_CURRENT_PLAYLIST,
    ATTR_CURRENT_FILE,
    ATTR_TV_STATUS,
)

_LOGGER = logging.getLogger(__name__)

SUPPORT_PISIGNAGE = (
    MediaPlayerEntityFeature.TURN_ON
    | MediaPlayerEntityFeature.TURN_OFF
    | MediaPlayerEntityFeature.PLAY
    | MediaPlayerEntityFeature.PAUSE
    | MediaPlayerEntityFeature.NEXT_TRACK
    | MediaPlayerEntityFeature.PREVIOUS_TRACK
    | MediaPlayerEntityFeature.PLAY_MEDIA
    | MediaPlayerEntityFeature.SELECT_SOURCE
)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the PiSignage media players."""
    _LOGGER.info("Setting up PiSignage media player entities")
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    api = hass.data[DOMAIN][entry.entry_id]["api"]
    
    players = coordinator.data.get(CONF_PLAYERS, [])
    entities = []
    
    for player in players:
        player_id = player.get("_id")
        player_name = player.get("name", f"Player {player_id}")
        entities.append(PiSignageMediaPlayer(coordinator, api, player, entry))
    
    async_add_entities(entities, True)
    _LOGGER.info("Added %d PiSignage media player entities", len(entities))


class PiSignageMediaPlayer(MediaPlayerEntity):
    """Representation of a PiSignage media player."""

    def __init__(self, coordinator, api, player, config_entry):
        """Initialize the PiSignage media player."""
        self.coordinator = coordinator
        self.api = api
        self._player_id = player.get("_id")
        self._name = player.get("name", f"PiSignage Player {self._player_id}")
        self._unique_id = f"pisignage_{self._player_id}"
        self._available = True
        # We don't store the config_entry directly anymore
        self._sources = []
        self._update_sources()
        # Register to coordinator
        coordinator.async_add_listener(self._update_sources)
        self._attr_should_poll = False
        _LOGGER.debug("Initialized PiSignage media player entity: %s", self._name)

    async def async_added_to_hass(self):
        """When entity is added to hass."""
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )

    @property
    def device_info(self):
        """Return device information for this entity."""
        return {
            "identifiers": {(DOMAIN, self._player_id)},
            "name": self._name,
        }

    def _update_sources(self):
        """Update the available playlists as sources."""
        self._sources = []
        if playlists := self.coordinator.playlists:
            self._sources = [playlist.get("name") for playlist in playlists if "name" in playlist]
            _LOGGER.debug("Updated playlists for %s, found %d playlists", self._name, len(self._sources))

    @property
    def unique_id(self) -> str:
        """Return the unique ID of the device."""
        return self._unique_id

    @property
    def name(self) -> str:
        """Return the name of the device."""
        return self._name

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        # Get player data from coordinator directly
        players = self.coordinator.data.get(CONF_PLAYERS, [])
        player_found = any(p.get("_id") == self._player_id for p in players)
        return player_found and self.coordinator.last_update_success

    @property
    def _player_data(self):
        """Get the latest player data from the coordinator."""
        for player in self.coordinator.data.get(CONF_PLAYERS, []):
            if player.get("_id") == self._player_id:
                return player
        return {}

    @property
    def state(self) -> str:
        """Return the state of the device."""
        player_data = self._player_data
        
        if not player_data.get("isConnected", False):
            return STATE_OFF

        # Get the config entry directly from the hass context
        config_entry = self.hass.config_entries.async_get_entry(self.registry_entry.config_entry_id)
        ignore_cec = config_entry.options.get(CONF_IGNORE_CEC, {}).get(self._player_id, False)
        
        is_cec_supported = player_data.get("isCecSupported", False) and not ignore_cec
        cec_tv_status = player_data.get("cecTvStatus", False)
        playlist_on = player_data.get("playlistOn", False)

        if not is_cec_supported:
            if playlist_on:
                return STATE_PLAYING
            return STATE_IDLE

        if not cec_tv_status:
            return STATE_STANDBY

        if playlist_on:
            return STATE_PLAYING

        return STATE_IDLE

    @property
    def media_content_type(self) -> str:
        """Return the content type of current playing media."""
        return MediaType.PLAYLIST

    @property
    def media_title(self) -> Optional[str]:
        """Return the title of current playing media."""
        return self._player_data.get("currentPlaylist", "Unknown")

    @property
    def source(self) -> Optional[str]:
        """Return the current playlist."""
        return self._player_data.get("currentPlaylist")

    @property
    def source_list(self) -> List[str]:
        """Return available playlists."""
        return self._sources

    @property
    def supported_features(self) -> int:
        """Flag of media commands that are supported."""
        return SUPPORT_PISIGNAGE

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the state attributes."""
        player_data = self._player_data
        attrs = {}
        
        if playlists := player_data.get("playlists"):
            attrs[ATTR_PLAYLISTS] = playlists
            
        if group := player_data.get("group"):
            attrs[ATTR_GROUP] = group
            
        if status := player_data.get("status"):
            attrs[ATTR_STATUS] = status
        
        status_data = player_data.get("statusData", {})
        
        if playlist := status_data.get("playlistPlaying"):
            attrs[ATTR_CURRENT_PLAYLIST] = playlist
            
        if current_file := status_data.get("currentPlay", {}).get("filename"):
            attrs[ATTR_CURRENT_FILE] = current_file
        
        if tv_status := player_data.get("tvStatus"):
            attrs[ATTR_TV_STATUS] = "On" if tv_status == "1" else "Off"
            
        return attrs

    # Remove the async_update method - coordinator handles updates

    async def async_turn_on(self) -> None:
        """Turn the device on."""
        _LOGGER.info("Turning on TV for player %s", self._name)
        await self.hass.async_add_executor_job(
            self.api.tv_on, self._player_id
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self) -> None:
        """Turn the device off."""
        _LOGGER.info("Turning off TV for player %s", self._name)
        await self.hass.async_add_executor_job(
            self.api.tv_off, self._player_id
        )
        await self.coordinator.async_request_refresh()

    async def async_media_play(self) -> None:
        """Send play command."""
        _LOGGER.info("Sending play command to player %s", self._name)
        await self.hass.async_add_executor_job(
            self.api.media_control, self._player_id, "play"
        )
        await self.coordinator.async_request_refresh()

    async def async_media_pause(self) -> None:
        """Send pause command."""
        _LOGGER.info("Sending pause command to player %s", self._name)
        await self.hass.async_add_executor_job(
            self.api.media_control, self._player_id, "pause"
        )
        await self.coordinator.async_request_refresh()

    async def async_media_next_track(self) -> None:
        """Send next track command."""
        _LOGGER.info("Sending next track command to player %s", self._name)
        await self.hass.async_add_executor_job(
            self.api.media_control, self._player_id, "forward"
        )
        await self.coordinator.async_request_refresh()

    async def async_media_previous_track(self) -> None:
        """Send previous track command."""
        _LOGGER.info("Sending previous track command to player %s", self._name)
        await self.hass.async_add_executor_job(
            self.api.media_control, self._player_id, "backward"
        )
        await self.coordinator.async_request_refresh()

    async def async_play_media(
        self, media_type: str, media_id: str, **kwargs: Any
    ) -> None:
        """Play a piece of media."""
        # In this case, media_id is the playlist name
        _LOGGER.info("Playing playlist '%s' on player %s", media_id, self._name)
        await self.hass.async_add_executor_job(
            self.api.play_playlist, self._player_id, media_id
        )
        await self.coordinator.async_request_refresh()

    async def async_select_source(self, source: str) -> None:
        """Select playlist to play."""
        _LOGGER.info("Selecting source '%s' on player %s", source, self._name)
        group_id = self._player_data.get("group", {}).get("_id")
        if not group_id:
            _LOGGER.error("No group assigned to player %s", self._name)
            return

        await self.hass.async_add_executor_job(
            self.api.update_group_playlist, group_id, source
        )
        await self.coordinator.async_request_refresh()