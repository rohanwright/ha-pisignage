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
    api = PiSignageAPI(api_server, username, password, server_type)
    
    # Verify authentication
    try:
        _LOGGER.debug("Authenticating with PiSignage server")
        auth_success = await hass.async_add_executor_job(api.authenticate)
        if not auth_success:
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

    def __init__(self, api_server, username, password, server_type):
        """Initialize the API client."""
        self.api_server = api_server
        self.username = username
        self.password = password
        self.server_type = server_type
        self.token = None
        self.session = requests.Session()
        
        # For open source servers, configure basic auth directly
        if server_type == SERVER_TYPE_OPEN_SOURCE:
            self.session.auth = (username, password)
        
        _LOGGER.debug("Initialized PiSignage API client for %s (type: %s)", api_server, server_type)

    def authenticate(self):
        """Authenticate with the PiSignage server."""
        _LOGGER.debug("Attempting to authenticate with PiSignage server: %s", self.api_server)
        
        # For open source server, we use basic authentication - no token needed
        if self.server_type == SERVER_TYPE_OPEN_SOURCE:
            try:
                # Just perform a simple GET request to verify credentials
                response = self.session.get(f"{self.api_server}/players", timeout=10)
                response.raise_for_status()
                _LOGGER.debug("Open source server authentication successful")
                return True
            except requests.exceptions.RequestException as ex:
                _LOGGER.error("Open source server authentication failed: %s", ex)
                return False
        
        # For hosted service, use token-based authentication
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
                return True
            elif data.get("success") is False:
                _LOGGER.error("Authentication failed: %s", data.get("stat_message", "Unknown error"))
            else:
                _LOGGER.error("Authentication failed: Unexpected response format")
                
            return False
        except requests.exceptions.JSONDecodeError as ex:
            _LOGGER.error("Failed to decode JSON response from server: %s", str(ex))
            _LOGGER.debug("Response content: %s", response.text if 'response' in locals() else "No response")
            raise
        except requests.exceptions.RequestException as ex:
            _LOGGER.error("Error during authentication: %s", ex)
            raise

    def _handle_request(self, method, endpoint, **kwargs):
        """Handle API request with token expiration check and retry logic."""
        # Only handle tokens for hosted service
        if self.server_type == SERVER_TYPE_HOSTED:
            # Ensure we have a token
            if not self.token:
                _LOGGER.debug("No auth token, authenticating first")
                if not self.authenticate():
                    _LOGGER.error("Authentication failed")
                    raise ConnectionError("Authentication failed")
                
            # For GET requests, add token as query parameter
            if method == "get" and "params" in kwargs:
                kwargs["params"]["token"] = self.token
            elif method == "get":
                kwargs["params"] = {"token": self.token}
            
            # For POST requests, add token to JSON body
            if method == "post":
                if "json" in kwargs:
                    # Add token to existing JSON payload
                    kwargs["json"]["token"] = self.token
                elif "data" not in kwargs:
                    # No payload but need token - use empty JSON object
                    kwargs["json"] = {"token": self.token}
        elif self.server_type == SERVER_TYPE_OPEN_SOURCE and method == "post" and "json" not in kwargs and "data" not in kwargs:
            # For open source POST requests with no body specified, don't add an empty one
            pass
        
        # Execute request
        try:
            if method == "get":
                response = self.session.get(f"{self.api_server}/{endpoint}", **kwargs)
            else:  # post
                response = self.session.post(f"{self.api_server}/{endpoint}", **kwargs)
                
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.HTTPError as ex:
            # Check if this might be an expired token (401/403)
            if self.server_type == SERVER_TYPE_HOSTED and ex.response.status_code in (401, 403):
                _LOGGER.warning("Request failed with 401/403, token might be expired. Reauthenticating...")
                
                # Try to authenticate again
                if self.authenticate():
                    _LOGGER.debug("Reauthentication successful, retrying request")
                    
                    # Update token in request and retry
                    if method == "get" and "params" in kwargs:
                        kwargs["params"]["token"] = self.token
                    elif method == "get":
                        kwargs["params"] = {"token": self.token}
                        
                    if method == "post" and "json" in kwargs:
                        kwargs["json"]["token"] = self.token
                    elif method == "post" and "data" not in kwargs:
                        kwargs["json"] = {"token": self.token}
                    
                    # Execute request again
                    if method == "get":
                        retry_response = self.session.get(f"{self.api_server}/{endpoint}", **kwargs)
                    else:  # post
                        retry_response = self.session.post(f"{self.api_server}/{endpoint}", **kwargs)
                        
                    retry_response.raise_for_status()
                    return retry_response.json()
                else:
                    _LOGGER.error("Reauthentication failed")
                    raise ConnectionError("Reauthentication failed")
            else:
                # Not a token issue, re-raise
                raise
                
    def get_players(self):
        """Get list of players."""
        _LOGGER.debug("Fetching players list from PiSignage server")
        
        try:
            data = self._handle_request("get", "players", timeout=10)
            
            # Process the response
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
        
        try:
            data = self._handle_request("get", f"players/{player_id}", timeout=10)
            
            # Process the response
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
        
        try:
            # Prepare payload without token (will be added by _handle_request for hosted service)
            payload = {"status": True}
            
            data = self._handle_request("post", f"pitv/{player_id}", json=payload, timeout=10)
            
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
        
        try:
            # Prepare payload without token (will be added by _handle_request for hosted service)
            payload = {"status": False}
            
            data = self._handle_request("post", f"pitv/{player_id}", json=payload, timeout=10)
            
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
        
        try:
            data = self._handle_request("post", f"setplaylist/{player_id}/{playlist}", timeout=10)
            
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
        
        try:
            data = self._handle_request("post", f"playlistmedia/{player_id}/{action}", timeout=10)
        
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
        
        try:
            data = self._handle_request("get", "playlists", timeout=10)
            
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

        try:
            # Fetch required data
            group_data = self._handle_request("get", f"groups/{group_id}", timeout=10)
            playlists_data = self._handle_request("get", "playlists", timeout=10)
            
            # Handle different response structures
            if isinstance(group_data, dict) and group_data.get("success") and "data" in group_data:
                group_data = group_data.get("data", {})
            
            # Handle different response structures for playlists
            if isinstance(playlists_data, dict) and playlists_data.get("success") and "data" in playlists_data:
                all_playlists = playlists_data.get("data", [])
            elif isinstance(playlists_data, list):
                all_playlists = playlists_data
            else:
                all_playlists = []
            
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
            
            # Prepare update data
            update_data = {
                "playlists": group_playlists,
                "assets": list(asset_names),
                "deploy": True
            }
            
            # Send update
            result = self._handle_request("post", f"groups/{group_id}", json=update_data, timeout=10)
            
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