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
        _LOGGER.info("Adding PiSignage media player: %s (ID: %s)", player_name, player_id)
        entities.append(PiSignageMediaPlayer(coordinator, api, player))
    
    async_add_entities(entities, True)
    _LOGGER.debug("Added %d PiSignage media player entities", len(entities))


class PiSignageMediaPlayer(MediaPlayerEntity):
    """Representation of a PiSignage media player."""

    def __init__(self, coordinator, api, player):
        """Initialize the PiSignage media player."""
        self.coordinator = coordinator
        self.api = api
        self._player_id = player.get("_id")
        self._name = player.get("name", f"PiSignage Player {self._player_id}")
        self._unique_id = f"pisignage_{self._player_id}"
        self._player_data = player
        self._available = True
        self._sources = []
        self._update_sources()
        _LOGGER.debug("Initialized PiSignage media player entity: %s", self._name)

    @property
    def device_info(self):
        """Return device information for this entity."""
        return {
            "identifiers": {(DOMAIN, self._player_id)},
            "name": self._name,
            "manufacturer": "PiSignage",
            "model": "PiSignage Player",
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
        return self._available and self.coordinator.last_update_success

    @property
    def state(self) -> str:
        """Return the state of the device."""
        if self._player_data.get("connectionCount", 0) < 1:
            _LOGGER.debug("Player %s is off and disconnected from the server", self._name)
            return STATE_OFF
        if self._player_data.get("playlistOn")&self._player_data.get("tvStatus"):
            _LOGGER.debug("Player %s is playing", self._name)
            return STATE_PLAYING
        if not self._player_data.get("tvStatus"):
            _LOGGER.debug("Player %s is on", self._name)
            return STATE_STANDBY
        _LOGGER.debug("Player %s is idle", self._name)
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
        attrs = {}
        
        if playlists := self._player_data.get("playlists"):
            attrs[ATTR_PLAYLISTS] = playlists
            
        if group := self._player_data.get("group"):
            attrs[ATTR_GROUP] = group
            
        if status := self._player_data.get("status"):
            attrs[ATTR_STATUS] = status
        
        status_data = self._player_data.get("statusData", {})
        
        if playlist := status_data.get("playlistPlaying"):
            attrs[ATTR_CURRENT_PLAYLIST] = playlist
            
        if current_file := status_data.get("currentPlay", {}).get("filename"):
            attrs[ATTR_CURRENT_FILE] = current_file
        
        if tv_status := self._player_data.get("tvStatus"):
            attrs[ATTR_TV_STATUS] = "On" if tv_status == "1" else "Off"
            
        return attrs

    async def async_update(self) -> None:
        """Update the player data."""
        _LOGGER.debug("Updating player data for %s", self._name)
        await self.coordinator.async_request_refresh()
        players = self.coordinator.data.get(CONF_PLAYERS, [])
        
        for player in players:
            if player.get("_id") == self._player_id:
                _LOGGER.debug("Found updated data for player %s", self._name)
                self._player_data = player
                self._available = True
                self._update_sources()
                return
        
        _LOGGER.warning("Player %s not found in updated data", self._name)
        self._available = False

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