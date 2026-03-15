"""Support for PiSignage media players."""
import asyncio
import logging
import time
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

# Safety timeout for optimistic state (seconds)
# Optimistic state persists until the server confirms the expected state,
# or this timeout expires (whichever comes first)
OPTIMISTIC_TIMEOUT = 120

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
    _LOGGER.debug("Setting up PiSignage media player entities")
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    api = hass.data[DOMAIN][entry.entry_id]["api"]
    
    players = coordinator.data.get(CONF_PLAYERS, [])
    entities = []
    
    for player in players:
        player_id = player.get("_id")
        player_name = player.get("name", f"Player {player_id}")
        entities.append(PiSignageMediaPlayer(coordinator, api, player, entry))
    
    async_add_entities(entities, True)
    _LOGGER.debug("Added %d PiSignage media player entities", len(entities))


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
        self._sources = []
        self._update_sources()
        coordinator.async_add_listener(self._update_sources)
        self._attr_should_poll = False
        
        # Optimistic state tracking
        self._optimistic_state = None
        self._optimistic_source = None
        self._optimistic_set_time = None
        
        _LOGGER.debug("Initialized PiSignage media player entity: %s", self._name)

    async def async_added_to_hass(self):
        """When entity is added to hass."""
        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )

    def _handle_coordinator_update(self):
        """Handle updated data from the coordinator."""
        if self._optimistic_state is not None:
            real_state = self._compute_state_from_data()
            elapsed = time.monotonic() - self._optimistic_set_time if self._optimistic_set_time else float('inf')

            if real_state == self._optimistic_state:
                # Server confirmed our expected state
                _LOGGER.debug(
                    "Optimistic state confirmed by server for %s", self._name
                )
                self._clear_optimistic_state()
            elif elapsed > OPTIMISTIC_TIMEOUT:
                # Safety timeout expired — revert to server state
                _LOGGER.debug(
                    "Optimistic state timeout for %s (%.0fs elapsed), reverting to server state",
                    self._name, elapsed,
                )
                self._clear_optimistic_state()
            else:
                # Server hasn't caught up yet — keep optimistic state
                _LOGGER.debug(
                    "Keeping optimistic state for %s (server: %s, optimistic: %s, %.0fs elapsed)",
                    self._name, real_state, self._optimistic_state, elapsed,
                )

        # Handle optimistic source independently
        if self._optimistic_source is not None:
            real_source = self._player_data.get("currentPlaylist")
            elapsed = time.monotonic() - self._optimistic_set_time if self._optimistic_set_time else float('inf')
            if real_source == self._optimistic_source or elapsed > OPTIMISTIC_TIMEOUT:
                self._optimistic_source = None

        self.async_write_ha_state()

    def _clear_optimistic_state(self):
        """Clear all optimistic state tracking."""
        self._optimistic_state = None
        self._optimistic_source = None
        self._optimistic_set_time = None

    def _compute_state_from_data(self):
        """Compute state from coordinator data (without optimistic override)."""
        player_data = self._player_data

        config_entry = self.hass.config_entries.async_get_entry(
            self.registry_entry.config_entry_id
        )
        ignore_cec = config_entry.options.get(CONF_IGNORE_CEC, {}).get(
            self._player_id, False
        )

        playlist_on = player_data.get("playlistOn", False)

        if ignore_cec:
            # CEC is unreliable for this player (e.g. splitter/converter),
            # so skip tvStatus and use only playlistOn
            return STATE_PLAYING if playlist_on else STATE_IDLE

        # tvStatus reflects the commanded TV state and updates immediately:
        #   true  = TV output is active (on)
        #   false = TV output is off/blanked
        tv_status = player_data.get("tvStatus", True)

        if not tv_status:
            # TV has been commanded off
            return STATE_STANDBY
        if playlist_on:
            return STATE_PLAYING
        return STATE_IDLE

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
            # Filter out the TV_OFF playlist from the source list
            self._sources = [
                playlist.get("name") 
                for playlist in playlists 
                if "name" in playlist and playlist.get("name") != "TV_OFF"
            ]
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
        players = self.coordinator.data.get(CONF_PLAYERS, [])
        player_data = next(
            (p for p in players if p.get("_id") == self._player_id), None
        )
        if player_data is None:
            return False
        # Player must be connected to the PiSignage server to be available
        return player_data.get("isConnected", False) and self.coordinator.last_update_success

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
        # Return optimistic state if set (before server confirms)
        if self._optimistic_state is not None:
            return self._optimistic_state
        return self._compute_state_from_data()

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
        if self._optimistic_source is not None:
            return self._optimistic_source
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
            attrs[ATTR_TV_STATUS] = "On" if tv_status else "Off"
            
        return attrs

    def _set_optimistic_state(self, state, source=None):
        """Set optimistic state and record the time it was set."""
        self._optimistic_state = state
        self._optimistic_set_time = time.monotonic()
        if source is not None:
            self._optimistic_source = source
        self.async_write_ha_state()

    async def async_turn_on(self) -> None:
        """Turn the device on."""
        _LOGGER.debug("Turning on TV for player %s", self._name)
        await self.api.tv_on(self._player_id)
        self._set_optimistic_state(STATE_IDLE)

    async def async_turn_off(self) -> None:
        """Turn the device off."""
        _LOGGER.debug("Turning off TV for player %s", self._name)
        await self.api.tv_off(self._player_id)
        self._set_optimistic_state(STATE_STANDBY)

    async def async_media_play(self) -> None:
        """Send play command."""
        _LOGGER.debug("Sending play command to player %s", self._name)
        await self.api.media_control(self._player_id, "play")
        self._set_optimistic_state(STATE_PLAYING)

    async def async_media_pause(self) -> None:
        """Send pause command."""
        _LOGGER.debug("Sending pause command to player %s", self._name)
        await self.api.media_control(self._player_id, "pause")
        self._set_optimistic_state(STATE_PAUSED)

    async def async_media_next_track(self) -> None:
        """Send next track command."""
        _LOGGER.debug("Sending next track command to player %s", self._name)
        await self.api.media_control(self._player_id, "forward")
        self._set_optimistic_state(STATE_PLAYING)

    async def async_media_previous_track(self) -> None:
        """Send previous track command."""
        _LOGGER.debug("Sending previous track command to player %s", self._name)
        await self.api.media_control(self._player_id, "backward")
        self._set_optimistic_state(STATE_PLAYING)

    async def async_play_media(
        self, media_type: str, media_id: str, **kwargs: Any
    ) -> None:
        """Play a piece of media."""
        _LOGGER.debug("Playing playlist '%s' on player %s", media_id, self._name)
        await self.api.play_playlist(self._player_id, media_id)
        self._set_optimistic_state(STATE_PLAYING, source=media_id)

    async def async_select_source(self, source: str) -> None:
        """Select playlist to play."""
        _LOGGER.debug("Selecting source '%s' on player %s", source, self._name)
        group_id = self._player_data.get("group", {}).get("_id")
        if not group_id:
            _LOGGER.error("No group assigned to player %s", self._name)
            return

        await self.api.update_group_playlist(group_id, source)
        self._set_optimistic_state(STATE_PLAYING, source=source)