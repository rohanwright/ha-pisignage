"""The PiSignage integration."""
import asyncio
import logging
from datetime import timedelta

import requests
from requests.exceptions import ConnectionError, HTTPError, Timeout

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.helpers import device_registry as dr

from .const import (
    DOMAIN,
    CONF_API_SERVER,
    CONF_API_HOST,
    CONF_API_PORT,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_PLAYERS,
    CONF_SERVER_TYPE,
    CONF_USE_SSL,
    CONF_IGNORE_CEC,
    SERVER_TYPE_HOSTED,
    SERVER_TYPE_OPEN_SOURCE,
    DEFAULT_PORT_SERVER,
    MEDIA_PLAYER,
    SENSOR,
    SCAN_INTERVAL_SECONDS,
)

_LOGGER = logging.getLogger(__name__)

# Define platforms after importing constants
PLATFORMS = [MEDIA_PLAYER, SENSOR]


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate an old config entry to new format."""
    _LOGGER.debug("Migrating PiSignage config entry from version %s", entry.version)

    if entry.version == 1:
        # Migration from version 1 to 2: Add CONF_IGNORE_CEC options structure
        _LOGGER.info("Migrating PiSignage config entry from version 1 to 2")
        
        # Initialize the ignore_cec options dictionary if it doesn't exist
        options = dict(entry.options)
        if CONF_IGNORE_CEC not in options:
            options[CONF_IGNORE_CEC] = {}
            
        # Update to new version
        hass.config_entries.async_update_entry(
            entry, 
            options=options,
            version=2
        )
        _LOGGER.info("Successfully migrated PiSignage config from version 1 to 2")

    return True


async def async_setup_domain(hass, config):
    """Set up PiSignage from configuration.yaml."""
    _LOGGER.debug("Setting up PiSignage domain from configuration.yaml is not supported")
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up PiSignage from a config entry."""
    _LOGGER.info("Setting up PiSignage integration from config entry: %s", entry.title)
    
    server_type = entry.data.get(CONF_SERVER_TYPE, SERVER_TYPE_OPEN_SOURCE)
    api_host = entry.data[CONF_API_HOST]
    use_ssl = entry.data.get(CONF_USE_SSL, server_type == SERVER_TYPE_HOSTED)
    protocol = "https" if use_ssl else "http"
    
    # Configure API endpoint based on server type
    if server_type == SERVER_TYPE_HOSTED:
        # For hosted servers, format is: https://username.pisignage.com/api
        api_server = f"https://{api_host}.pisignage.com/api"
        _LOGGER.info("Connecting to hosted PiSignage server: %s", api_server)
    else:
        # For open source servers
        api_port = entry.data.get(CONF_API_PORT, DEFAULT_PORT_SERVER)
        api_server = f"{protocol}://{api_host}:{api_port}/api"
        _LOGGER.info("Connecting to PiSignage open source server at %s:%s", api_host, api_port)
    
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]

    # Create API client
    api = PiSignageAPI(api_server, username, password)
    
    # Verify authentication
    try:
        _LOGGER.debug("Authenticating with PiSignage server")
        token = await hass.async_add_executor_job(api.authenticate)
        if not token:
            _LOGGER.error("Authentication to PiSignage server failed")
            raise ConfigEntryNotReady("Authentication to PiSignage failed")
        _LOGGER.debug("Successfully authenticated with PiSignage server")
    except (ConnectionError, HTTPError, Timeout) as ex:
        _LOGGER.error("Error connecting to PiSignage server: %s", ex)
        raise ConfigEntryNotReady(f"Error connecting to PiSignage: {ex}")

    # Create update coordinator
    coordinator = PiSignageDataUpdateCoordinator(hass, api)
    
    # Fetch initial data
    _LOGGER.debug("Performing initial data refresh")
    await coordinator.async_config_entry_first_refresh()
    
    # Create devices for each player
    players = coordinator.data.get(CONF_PLAYERS, [])
    device_registry = dr.async_get(hass)
    for player in players:
        player_id = player.get("_id")
        player_name = player.get("name", f"Player {player_id}")
        sw_version = player.get("version", "Unknown")
        config_location = player.get("configLocation", "Unknown")
        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, player_id)},
            name=player_name,
            manufacturer="PiSignage",
            model=f"PiSignage Player: {config_location}",
            sw_version=sw_version,
        )
    
    # Store the API and coordinator references
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
    }

    # Set up platforms
    _LOGGER.debug("Setting up PiSignage platforms")
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _LOGGER.info("PiSignage setup completed successfully")

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading PiSignage integration: %s", entry.title)
    
    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    # Clean up
    if unload_ok:
        _LOGGER.debug("Successfully unloaded PiSignage platforms")
        hass.data[DOMAIN].pop(entry.entry_id)
    else:
        _LOGGER.warning("Failed to fully unload PiSignage integration")

    return unload_ok


class PiSignageAPI:
    """API client for PiSignage."""

    def __init__(self, api_server, username, password):
        """Initialize the API client."""
        self.api_server = api_server
        self.username = username
        self.password = password
        self.token = None
        self.session = requests.Session()
        _LOGGER.debug("Initialized PiSignage API client for %s", api_server)

    def authenticate(self):
        """Authenticate with the PiSignage server."""
        _LOGGER.debug("Attempting to authenticate with PiSignage server: %s", self.api_server)
        try:
            # Format authentication payload according to API docs
            auth_payload = {
                "email": self.username,
                "password": self.password,
                "getToken": True  # Boolean true, not string
            }
            
            _LOGGER.debug("Sending authentication request with payload: %s", 
                         {**auth_payload, "password": "***REDACTED***"})
            
            response = self.session.post(
                f"{self.api_server}/session",
                json=auth_payload,
                timeout=10,
            )
            
            _LOGGER.debug("Got response status code: %s", response.status_code)
            
            # Check for non-200 status code
            response.raise_for_status()
            
            # Parse response
            data = response.json()
            _LOGGER.debug("Authentication response: %s", 
                         {k: v for k, v in data.items() if k != "data"})
            
            # Check for various success indicators
            if data.get("token"):
                self.token = data.get("token")
                _LOGGER.debug("Authentication successful, token received")
                return self.token
            elif data.get("success") is False:
                _LOGGER.error("Authentication failed: %s", data.get("stat_message", "Unknown error"))
            else:
                _LOGGER.error("Authentication failed: Unexpected response format")
                
            return None
        except requests.exceptions.JSONDecodeError as ex:
            _LOGGER.error("Failed to decode JSON response from server: %s", str(ex))
            _LOGGER.debug("Response content: %s", response.text if 'response' in locals() else "No response")
            raise
        except requests.exceptions.RequestException as ex:
            _LOGGER.error("Error during authentication: %s", ex)
            raise

    def get_players(self):
        """Get list of players."""
        _LOGGER.debug("Fetching players list from PiSignage server")
        if not self.token:
            _LOGGER.debug("No auth token, re-authenticating")
            self.authenticate()

        try:
            response = self.session.get(
                f"{self.api_server}/players",
                params={"token": self.token},
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            
            # Log the raw response for debugging
            # _LOGGER.debug("Raw players response: %s", data)
            
            if data.get("success"):
                players = data.get("data", [])
                _LOGGER.debug("Retrieved %d players from server", len(players))
                return players
            elif isinstance(data, list):
                # Direct array of players without the success wrapper
                _LOGGER.debug("Retrieved %d players from server (direct format)", len(data))
                return data
            else:
                _LOGGER.error("Failed to get players: %s", data.get("stat_message", "Unknown response format"))
                _LOGGER.debug("Unexpected players response format: %s", data)
            return []
        except requests.exceptions.RequestException as ex:
            _LOGGER.error("Error fetching players: %s", ex)
            raise

    def get_player(self, player_id):
        """Get player details."""
        _LOGGER.debug("Fetching details for player: %s", player_id)
        if not self.token:
            _LOGGER.debug("No auth token, re-authenticating")
            self.authenticate()

        try:
            response = self.session.get(
                f"{self.api_server}/players/{player_id}",
                params={"token": self.token},
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            
            # Log the raw response for debugging
            # _LOGGER.debug("Raw player details response for %s: %s", player_id, data)
            
            if data.get("success"):
                _LOGGER.debug("Successfully retrieved details for player: %s", player_id)
                return data.get("data", {})
            elif isinstance(data, dict) and "_id" in data:
                # Direct player data without success wrapper
                _LOGGER.debug("Successfully retrieved details for player: %s (direct format)", player_id)
                return data
            else:
                _LOGGER.error("Failed to get player details: %s", data.get("stat_message", "Unknown error"))
                _LOGGER.debug("Unexpected player details response format: %s", data)
            return {}
        except requests.exceptions.RequestException as ex:
            _LOGGER.error("Error fetching player details: %s", ex)
            raise

    def tv_off(self, player_id):
        """Turn TV off."""
        _LOGGER.debug("Turning off TV for player: %s", player_id)
        if not self.token:
            _LOGGER.debug("No auth token, re-authenticating")
            self.authenticate()

        try:
            response = self.session.post(
                f"{self.api_server}/pitv/{player_id}",
                json={"status": True, "token": self.token},
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            if data.get("success"):
                _LOGGER.info("Successfully turned off TV for player: %s", player_id)
            else:
                _LOGGER.error("Failed to turn off TV: %s", data.get("stat_message", "Unknown error"))
            return data
        except requests.exceptions.RequestException as ex:
            _LOGGER.error("Error turning off TV: %s", ex)
            raise

    def tv_on(self, player_id):
        """Turn TV on."""
        _LOGGER.debug("Turning on TV for player: %s", player_id)
        if not self.token:
            _LOGGER.debug("No auth token, re-authenticating")
            self.authenticate()

        try:
            response = self.session.post(
                f"{self.api_server}/pitv/{player_id}",
                json={"status": False, "token": self.token},
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            if data.get("success"):
                _LOGGER.info("Successfully turned on TV for player: %s", player_id)
            else:
                _LOGGER.error("Failed to turn on TV: %s", data.get("stat_message", "Unknown error"))
            return data
        except requests.exceptions.RequestException as ex:
            _LOGGER.error("Error turning on TV: %s", ex)
            raise

    def play_playlist(self, player_id, playlist):
        """Play a specific playlist."""
        _LOGGER.debug("Playing playlist '%s' on player: %s", playlist, player_id)
        if not self.token:
            _LOGGER.debug("No auth token, re-authenticating")
            self.authenticate()

        try:
            response = self.session.post(
                f"{self.api_server}/setplaylist/{player_id}/{playlist}",
                json={"token": self.token},
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            if data.get("success"):
                _LOGGER.info("Successfully started playlist '%s' on player: %s", playlist, player_id)
            else:
                _LOGGER.error("Failed to play playlist: %s", data.get("stat_message", "Unknown error"))
            return data
        except requests.exceptions.RequestException as ex:
            _LOGGER.error("Error playing playlist: %s", ex)
            raise

    def media_control(self, player_id, action):
        """Control media playback."""
        _LOGGER.debug("Sending media control '%s' to player: %s", action, player_id)
        if not self.token:
            _LOGGER.debug("No auth token, re-authenticating")
            self.authenticate()

        try:
            response = self.session.post(
                f"{self.api_server}/playlistmedia/{player_id}/{action}",
                json={"token": self.token},
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            if data.get("success"):
                _LOGGER.info("Successfully sent media control '%s' to player: %s", action, player_id)
            else:
                _LOGGER.error("Failed to control media: %s", data.get("stat_message", "Unknown error"))
            return data
        except requests.exceptions.RequestException as ex:
            _LOGGER.error("Error controlling media: %s", ex)
            raise

    def get_playlists(self):
        """Get list of playlists."""
        _LOGGER.debug("Fetching playlists from PiSignage server")
        if not self.token:
            _LOGGER.debug("No auth token, re-authenticating")
            self.authenticate()

        try:
            response = self.session.get(
                f"{self.api_server}/playlists",
                params={"token": self.token},
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            
            # Log the raw response structure for debugging
            if isinstance(data, dict):
                _LOGGER.debug("Playlists response has keys: %s", list(data.keys()))
            elif isinstance(data, list):
                _LOGGER.debug("Playlists response is a list of length: %d", len(data))
            else:
                _LOGGER.debug("Playlists response is type: %s", type(data))
            
            if data.get("success"):
                playlists = data.get("data", [])
                _LOGGER.debug("Retrieved %d playlists from server", len(playlists))
                return playlists
            elif isinstance(data, list):
                # Direct array of playlists without success wrapper
                _LOGGER.debug("Retrieved %d playlists from server (direct format)", len(data))
                return data
            else:
                _LOGGER.error("Failed to get playlists: %s", data.get("stat_message", "Unknown error"))
                _LOGGER.debug("Unexpected playlists response format: %s", data)
            return []
        except requests.exceptions.RequestException as ex:
            _LOGGER.error("Error fetching playlists: %s", ex)
            raise

    def update_group_playlist(self, group_id, playlist_name):
        """Update the default playlist for a group."""
        _LOGGER.debug("Updating group %s to use playlist %s", group_id, playlist_name)
        
        # Safety check to prevent setting TV_OFF playlist for groups so when we power on, the original playlist will ressume
        if playlist_name == "TV_OFF":
            _LOGGER.debug("Attempted to set TV_OFF playlist for group %s, Ignored change", group_id)
            return {"success": False, "stat_message": "Cannot set TV_OFF playlist for groups"}
        
        # Ensure authenticated
        if not self.token:
            self.authenticate()

        try:
            # Fetch required data
            group_response = self.session.get(
                f"{self.api_server}/groups/{group_id}",
                params={"token": self.token},
                timeout=10,
            )
            group_response.raise_for_status()
            group_data = group_response.json().get("data", {})
            
            playlists_response = self.session.get(
                f"{self.api_server}/playlists",
                params={"token": self.token},
                timeout=10,
            )
            playlists_response.raise_for_status()
            all_playlists = playlists_response.json().get("data", [])
            
            # Find target playlist
            target_playlist = next(
                (p for p in all_playlists if p.get("name") == playlist_name), None
            )
            if not target_playlist:
                _LOGGER.error("Playlist '%s' not found", playlist_name)
                return {"success": False, "stat_message": f"Playlist '{playlist_name}' not found"}
            
            # Update group's playlist list
            new_playlist_entry = {
                "name": target_playlist.get("name"),
                "settings": target_playlist.get("settings", {})
            }
            
            group_playlists = group_data.get("playlists", [])
            if group_playlists:
                group_playlists[0] = new_playlist_entry
            else:
                group_playlists = [new_playlist_entry]
            
            # Collect assets from all playlists used by this group
            playlist_names = {pl.get("name") for pl in group_playlists}
            asset_names = set()
            
            for playlist in all_playlists:
                if playlist.get("name") in playlist_names:
                    # Add asset filenames
                    asset_names.update(
                        asset["filename"] for asset in playlist.get("assets", [])
                        if "filename" in asset
                    )
                    
                    # Add playlist JSON file
                    asset_names.add(f"__{playlist.get('name')}.json")
                    
                    # Add template if present
                    if template := playlist.get("templateName"):
                        asset_names.add(template)
            
            # Prepare and send update
            update_data = {
                "playlists": group_playlists,
                "assets": list(asset_names),
                "deploy": True
            }
            
            deploy_response = self.session.post(
                f"{self.api_server}/groups/{group_id}",
                json=update_data,
                params={"token": self.token},
                timeout=10,
            )
            deploy_response.raise_for_status()
            result = deploy_response.json()
            
            if result.get("success"):
                _LOGGER.info("Successfully updated group %s to use playlist '%s'", 
                             group_id, playlist_name)
            else:
                _LOGGER.error("Failed to update group %s: %s", 
                              group_id, result.get("stat_message", "Unknown error"))
            
            return result
            
        except requests.exceptions.RequestException as ex:
            _LOGGER.error("Error updating playlist for group %s: %s", group_id, ex)
            raise


class PiSignageDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching PiSignage data."""

    def __init__(self, hass, api):
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS),
        )
        self.api = api
        self.playlists = []
        _LOGGER.debug("Initialized PiSignage data coordinator with %d second update interval", SCAN_INTERVAL_SECONDS)

    async def _async_update_data(self):
        """Fetch data from PiSignage."""
        try:
            _LOGGER.debug("Performing data update")
            # Get playlists first
            self.playlists = await self.hass.async_add_executor_job(self.api.get_playlists)
            
            # Get players
            raw_players_data = await self.hass.async_add_executor_job(self.api.get_players)
            
            # Check if we got the players data directly or need to process it
            if not raw_players_data:
                _LOGGER.warning("No player data received")
                return {
                    CONF_PLAYERS: [],
                    "playlists": self.playlists
                }
            
            # The API returns data in a nested structure
            # Extract actual player objects from the nested array
            player_objects = []
            
            if isinstance(raw_players_data, list):
                # Direct array of players
                player_objects = raw_players_data
            elif isinstance(raw_players_data, dict) and "objects" in raw_players_data:
                # Players are in the "objects" property
                player_objects = raw_players_data["objects"]
            elif isinstance(raw_players_data, dict) and "data" in raw_players_data:
                if isinstance(raw_players_data["data"], dict) and "objects" in raw_players_data["data"]:
                    # Nested structure: data.data.objects contains player array
                    player_objects = raw_players_data["data"]["objects"]
                elif isinstance(raw_players_data["data"], list):
                    # Structure: data.data is a player array
                    player_objects = raw_players_data["data"]
            
            _LOGGER.debug("Processing %d player objects", len(player_objects))
            
            # Process players to ensure consistent format
            processed_players = []
            for player in player_objects:
                if isinstance(player, dict) and "_id" in player:
                    processed_players.append(player)
                else:
                    _LOGGER.warning("Invalid player data format: %s", player)
            
            _LOGGER.debug("Data update completed successfully with %d players", len(processed_players))
            
            # Log more detailed information about the data structure we're returning
            _LOGGER.debug("Player data structure samples: %s", 
                        str({p.get("_id"): {k: v for k, v in p.items() if k in ["isConnected", "playlistOn", "currentPlaylist"]}
                             for p in processed_players[:2]}) if processed_players else "No players")
            
            return {
                CONF_PLAYERS: processed_players,
                "playlists": self.playlists
            }
        except (ConnectionError, HTTPError, Timeout) as ex:
            _LOGGER.error("Error while updating data: %s", ex)
            raise UpdateFailed(f"Error communicating with PiSignage: {ex}")
        except Exception as ex:
            _LOGGER.error("Unexpected error fetching pisignage data", exc_info=True)
            raise UpdateFailed(f"Unexpected error: {str(ex)}")