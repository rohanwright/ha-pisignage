"""The PiSignage integration."""
import asyncio
import logging
from datetime import timedelta

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
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

    # Create API client using HA's managed aiohttp session
    session = async_get_clientsession(hass)
    api = PiSignageAPI(api_server, username, password, server_type, session)
    
    # Verify authentication
    try:
        _LOGGER.debug("Authenticating with PiSignage server")
        auth_success = await api.authenticate()
        if not auth_success:
            _LOGGER.error("Authentication to PiSignage server failed")
            raise ConfigEntryNotReady("Authentication to PiSignage failed")
        _LOGGER.debug("Successfully authenticated with PiSignage server")
    except (aiohttp.ClientError, asyncio.TimeoutError) as ex:
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
    """Async API client for PiSignage using aiohttp."""

    def __init__(self, api_server, username, password, server_type, session: aiohttp.ClientSession):
        """Initialize the API client."""
        self.api_server = api_server
        self.username = username
        self.password = password
        self.server_type = server_type
        self.session = session
        self.token = None
        
        # Build basic auth for open source servers
        self._basic_auth = None
        if server_type == SERVER_TYPE_OPEN_SOURCE:
            self._basic_auth = aiohttp.BasicAuth(username, password)
        
        _LOGGER.debug("Initialized PiSignage API client for %s (type: %s)", api_server, server_type)

    async def authenticate(self):
        """Authenticate with the PiSignage server."""
        _LOGGER.debug("Attempting to authenticate with PiSignage server: %s", self.api_server)
        
        # For open source server, we use basic authentication - no token needed
        if self.server_type == SERVER_TYPE_OPEN_SOURCE:
            try:
                async with self.session.get(
                    f"{self.api_server}/players",
                    auth=self._basic_auth,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    response.raise_for_status()
                    _LOGGER.debug("Open source server authentication successful")
                    return True
            except (aiohttp.ClientError, asyncio.TimeoutError) as ex:
                _LOGGER.error("Open source server authentication failed: %s", ex)
                return False
        
        # For hosted service, use token-based authentication
        try:
            auth_payload = {
                "email": self.username,
                "password": self.password,
                "getToken": True
            }
            
            _LOGGER.debug("Sending authentication request with payload: %s", 
                         {**auth_payload, "password": "***REDACTED***"})
            
            async with self.session.post(
                f"{self.api_server}/session",
                json=auth_payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                _LOGGER.debug("Got response status code: %s", response.status)
                
                response.raise_for_status()
                data = await response.json()
                
                _LOGGER.debug("Authentication response: %s", 
                             {k: v for k, v in data.items() if k != "data"})
                
                if data.get("token"):
                    self.token = data.get("token")
                    _LOGGER.debug("Authentication successful, token received")
                    return True
                elif data.get("success") is False:
                    _LOGGER.error("Authentication failed: %s", data.get("stat_message", "Unknown error"))
                else:
                    _LOGGER.error("Authentication failed: Unexpected response format")
                    
                return False
        except aiohttp.ContentTypeError as ex:
            _LOGGER.error("Failed to decode JSON response from server: %s", str(ex))
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError) as ex:
            _LOGGER.error("Error during authentication: %s", ex)
            raise

    async def _handle_request(self, method, endpoint, **kwargs):
        """Handle API request with token expiration check and retry logic."""
        # Add auth for open source servers
        if self.server_type == SERVER_TYPE_OPEN_SOURCE:
            kwargs["auth"] = self._basic_auth
        
        # Handle tokens for hosted service
        if self.server_type == SERVER_TYPE_HOSTED:
            if not self.token:
                _LOGGER.debug("No auth token, authenticating first")
                if not await self.authenticate():
                    _LOGGER.error("Authentication failed")
                    raise ConnectionError("Authentication failed")
                
            # For GET requests, add token as query parameter
            if method == "get":
                params = kwargs.get("params", {})
                params["token"] = self.token
                kwargs["params"] = params
            
            # For POST requests, add token to JSON body
            if method == "post":
                if "json" in kwargs:
                    kwargs["json"]["token"] = self.token
                elif "data" not in kwargs:
                    kwargs["json"] = {"token": self.token}
        
        # Set default timeout
        if "timeout" not in kwargs:
            kwargs["timeout"] = aiohttp.ClientTimeout(total=10)
        else:
            timeout_val = kwargs["timeout"]
            if isinstance(timeout_val, (int, float)):
                kwargs["timeout"] = aiohttp.ClientTimeout(total=timeout_val)
        
        url = f"{self.api_server}/{endpoint}"
        
        try:
            if method == "get":
                async with self.session.get(url, **kwargs) as response:
                    response.raise_for_status()
                    return await response.json()
            else:  # post
                async with self.session.post(url, **kwargs) as response:
                    response.raise_for_status()
                    return await response.json()
                    
        except aiohttp.ClientResponseError as ex:
            # Token expired handling - attempt reauthentication for 401/403 errors
            if self.server_type == SERVER_TYPE_HOSTED and ex.status in (401, 403):
                _LOGGER.warning("Request failed with %s, token might be expired. Reauthenticating...", ex.status)
                
                if await self.authenticate():
                    _LOGGER.debug("Reauthentication successful, retrying request")
                    
                    # Update token in request and retry
                    if method == "get":
                        params = kwargs.get("params", {})
                        params["token"] = self.token
                        kwargs["params"] = params
                    if method == "post" and "json" in kwargs:
                        kwargs["json"]["token"] = self.token
                    elif method == "post" and "data" not in kwargs:
                        kwargs["json"] = {"token": self.token}
                    
                    if method == "get":
                        async with self.session.get(url, **kwargs) as retry_response:
                            retry_response.raise_for_status()
                            return await retry_response.json()
                    else:
                        async with self.session.post(url, **kwargs) as retry_response:
                            retry_response.raise_for_status()
                            return await retry_response.json()
                else:
                    _LOGGER.error("Reauthentication failed")
                    raise ConnectionError("Reauthentication failed")
            else:
                raise
                
    async def get_players(self):
        """Get list of players."""
        _LOGGER.debug("Fetching players list from PiSignage server")
        
        try:
            data = await self._handle_request("get", "players", timeout=10)
            
            if data.get("success"):
                players = data.get("data", [])
                _LOGGER.debug("Retrieved %d players from server", len(players))
                return players
            elif isinstance(data, list):
                _LOGGER.debug("Retrieved %d players from server (direct format)", len(data))
                return data
            else:
                _LOGGER.error("Failed to get players: %s", data.get("stat_message", "Unknown response format"))
                _LOGGER.debug("Unexpected players response format: %s", data)
            return []
        except (aiohttp.ClientError, asyncio.TimeoutError) as ex:
            _LOGGER.error("Error fetching players: %s", ex)
            raise

    async def get_player(self, player_id):
        """Get player details."""
        _LOGGER.debug("Fetching details for player: %s", player_id)
        
        try:
            data = await self._handle_request("get", f"players/{player_id}", timeout=10)
            
            if data.get("success"):
                _LOGGER.debug("Successfully retrieved details for player: %s", player_id)
                return data.get("data", {})
            elif isinstance(data, dict) and "_id" in data:
                _LOGGER.debug("Successfully retrieved details for player: %s (direct format)", player_id)
                return data
            else:
                _LOGGER.error("Failed to get player details: %s", data.get("stat_message", "Unknown error"))
                _LOGGER.debug("Unexpected player details response format: %s", data)
            return {}
        except (aiohttp.ClientError, asyncio.TimeoutError) as ex:
            _LOGGER.error("Error fetching player details: %s", ex)
            raise

    async def tv_off(self, player_id):
        """Turn TV off."""
        _LOGGER.debug("Turning off TV for player: %s", player_id)
        
        try:
            payload = {"status": True}
            data = await self._handle_request("post", f"pitv/{player_id}", json=payload, timeout=10)
            
            if data.get("success"):
                _LOGGER.debug("Successfully turned off TV for player: %s", player_id)
            else:
                _LOGGER.error("Failed to turn off TV: %s", data.get("stat_message", "Unknown error"))
            return data
        except (aiohttp.ClientError, asyncio.TimeoutError) as ex:
            _LOGGER.error("Error turning off TV: %s", ex)
            raise

    async def tv_on(self, player_id):
        """Turn TV on."""
        _LOGGER.debug("Turning on TV for player: %s", player_id)
        
        try:
            payload = {"status": False}
            data = await self._handle_request("post", f"pitv/{player_id}", json=payload, timeout=10)
            
            if data.get("success"):
                _LOGGER.debug("Successfully turned on TV for player: %s", player_id)
            else:
                _LOGGER.error("Failed to turn on TV: %s", data.get("stat_message", "Unknown error"))
            return data
        except (aiohttp.ClientError, asyncio.TimeoutError) as ex:
            _LOGGER.error("Error turning on TV: %s", ex)
            raise

    async def play_playlist(self, player_id, playlist):
        """Play a specific playlist."""
        _LOGGER.debug("Playing playlist '%s' on player: %s", playlist, player_id)
        
        try:
            data = await self._handle_request("post", f"setplaylist/{player_id}/{playlist}", timeout=10)
            
            if data.get("success"):
                _LOGGER.debug("Successfully started playlist '%s' on player: %s", playlist, player_id)
            else:
                _LOGGER.error("Failed to play playlist: %s", data.get("stat_message", "Unknown error"))
            return data
        except (aiohttp.ClientError, asyncio.TimeoutError) as ex:
            _LOGGER.error("Error playing playlist: %s", ex)
            raise

    async def media_control(self, player_id, action):
        """Control media playback."""
        _LOGGER.debug("Sending media control '%s' to player: %s", action, player_id)
        
        try:
            data = await self._handle_request("post", f"playlistmedia/{player_id}/{action}", timeout=10)
        
            if data.get("success"):
                _LOGGER.debug("Successfully sent media control '%s' to player: %s", action, player_id)
            else:
                _LOGGER.error("Failed to control media: %s", data.get("stat_message", "Unknown error"))
            return data
        except (aiohttp.ClientError, asyncio.TimeoutError) as ex:
            _LOGGER.error("Error controlling media: %s", ex)
            raise

    async def get_playlists(self):
        """Get list of playlists."""
        _LOGGER.debug("Fetching playlists from PiSignage server")
        
        try:
            data = await self._handle_request("get", "playlists", timeout=10)
            
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
                _LOGGER.debug("Retrieved %d playlists from server (direct format)", len(data))
                return data
            else:
                _LOGGER.error("Failed to get playlists: %s", data.get("stat_message", "Unknown error"))
                _LOGGER.debug("Unexpected playlists response format: %s", data)
            return []
        except (aiohttp.ClientError, asyncio.TimeoutError) as ex:
            _LOGGER.error("Error fetching playlists: %s", ex)
            raise

    async def update_group_playlist(self, group_id, playlist_name):
        """Update the default playlist for a group."""
        _LOGGER.debug("Updating group %s to use playlist %s", group_id, playlist_name)
        
        # Safety check to prevent setting TV_OFF playlist for groups
        if playlist_name == "TV_OFF":
            _LOGGER.debug("Attempted to set TV_OFF playlist for group %s, Ignored change", group_id)
            return {"success": False, "stat_message": "Cannot set TV_OFF playlist for groups"}

        try:
            # Fetch required data
            group_data = await self._handle_request("get", f"groups/{group_id}", timeout=10)
            playlists_data = await self._handle_request("get", "playlists", timeout=10)
            
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
                    asset_names.update(
                        asset["filename"] for asset in playlist.get("assets", [])
                        if "filename" in asset
                    )
                    asset_names.add(f"__{playlist.get('name')}.json")
                    if template := playlist.get("templateName"):
                        asset_names.add(template)
            
            # Prepare update data
            update_data = {
                "playlists": group_playlists,
                "assets": list(asset_names),
                "deploy": True
            }
            
            # Send update
            result = await self._handle_request("post", f"groups/{group_id}", json=update_data, timeout=10)
            
            if result.get("success"):
                _LOGGER.info("Successfully updated group %s to use playlist '%s'", 
                             group_id, playlist_name)
            else:
                _LOGGER.error("Failed to update group %s: %s", 
                              group_id, result.get("stat_message", "Unknown error"))
            
            return result
            
        except (aiohttp.ClientError, asyncio.TimeoutError) as ex:
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
            self.playlists = await self.api.get_playlists()
            
            # Get players
            raw_players_data = await self.api.get_players()
            
            if not raw_players_data:
                _LOGGER.warning("No player data received")
                return {
                    CONF_PLAYERS: [],
                    "playlists": self.playlists
                }
            
            # Extract actual player objects from the nested array
            player_objects = []
            
            if isinstance(raw_players_data, list):
                player_objects = raw_players_data
            elif isinstance(raw_players_data, dict) and "objects" in raw_players_data:
                player_objects = raw_players_data["objects"]
            elif isinstance(raw_players_data, dict) and "data" in raw_players_data:
                if isinstance(raw_players_data["data"], dict) and "objects" in raw_players_data["data"]:
                    player_objects = raw_players_data["data"]["objects"]
                elif isinstance(raw_players_data["data"], list):
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
            
            _LOGGER.debug("Player data structure samples: %s", 
                        str({p.get("_id"): {k: v for k, v in p.items() if k in ["isConnected", "playlistOn", "currentPlaylist"]}
                             for p in processed_players[:2]}) if processed_players else "No players")
            
            return {
                CONF_PLAYERS: processed_players,
                "playlists": self.playlists
            }
        except (aiohttp.ClientError, asyncio.TimeoutError) as ex:
            _LOGGER.error("Error while updating data: %s", ex)
            raise UpdateFailed(f"Error communicating with PiSignage: {ex}")
        except Exception as ex:
            _LOGGER.error("Unexpected error fetching pisignage data", exc_info=True)
            raise UpdateFailed(f"Unexpected error: {str(ex)}")