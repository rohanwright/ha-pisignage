"""Config flow for PiSignage integration."""
import logging
import voluptuous as vol
from typing import Any, Dict, Optional

import requests
from requests.exceptions import ConnectionError, HTTPError, Timeout

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.const import (
    CONF_HOST,
    CONF_PORT,
    CONF_USERNAME,
    CONF_PASSWORD,
)
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    CONF_API_HOST,
    CONF_API_PORT,
    CONF_SERVER_TYPE,
    CONF_USE_SSL,
    CONF_OTP,
    CONF_PLAYERS,
    CONF_IGNORE_CEC,
    SERVER_TYPE_HOSTED,
    SERVER_TYPE_OPEN_SOURCE,
    DEFAULT_PORT_SERVER,
)

_LOGGER = logging.getLogger(__name__)


class PiSignageConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for PiSignage."""

    VERSION = 2
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    def __init__(self):
        """Initialize the PiSignage config flow."""
        self.server_connection_info = {}
        self.api_url = None

    async def async_step_user(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        """Handle the initial step to select server type."""
        errors = {}

        if user_input is not None:
            self.context["server_type"] = user_input[CONF_SERVER_TYPE]
            return await self.async_step_server_details()

        schema = vol.Schema({
            vol.Required(CONF_SERVER_TYPE, default=SERVER_TYPE_OPEN_SOURCE): 
                selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            SERVER_TYPE_HOSTED,
                            SERVER_TYPE_OPEN_SOURCE,
                        ],
                        translation_key="server_type",
                        mode=selector.SelectSelectorMode.LIST,
                    )
                ),
        })

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_server_details(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        """Handle the second step to gather server details."""
        errors = {}
        server_type = self.context["server_type"]

        if user_input is not None:
            host = user_input[CONF_HOST]
            username = user_input[CONF_USERNAME]
            password = user_input[CONF_PASSWORD]
            use_ssl = user_input.get(CONF_USE_SSL, server_type == SERVER_TYPE_HOSTED)
            port = user_input.get(CONF_PORT, DEFAULT_PORT_SERVER)

            # Store connection info for later steps
            self.server_connection_info = {
                CONF_SERVER_TYPE: server_type,
                CONF_API_HOST: host,
                CONF_API_PORT: port,
                CONF_USERNAME: username,
                CONF_PASSWORD: password,
                CONF_USE_SSL: use_ssl,
            }

            # Set unique ID and check if already configured
            await self.async_set_unique_id(f"{host}_{username}")
            self._abort_if_unique_id_configured()

            # Construct API URL
            if server_type == SERVER_TYPE_HOSTED:
                # Use `host` as the username in the hosted URL
                api_url = f"https://{host}.pisignage.com/api"
            else:
                protocol = "https" if use_ssl else "http"
                api_url = f"{protocol}://{host}:{port}/api"
                
            self.api_url = api_url

            # Test connection
            try:
                response = await self.hass.async_add_executor_job(
                    self._test_connection, api_url, username, password, server_type
                )
                
                if response and response.get("success"):
                    return self.async_create_entry(
                        title=f"PiSignage ({host})",
                        data=self.server_connection_info,
                    )
                elif response and response.get("message") == "OTP needed":
                    # OTP is required, proceed to OTP step
                    return await self.async_step_otp()
                else:
                    # Any other response is treated as authentication failure
                    error_message = response.get("message", "") if response else ""
                    _LOGGER.error("Authentication failed: %s", error_message)
                    errors["base"] = "auth_failed"
            except ConnectionError:
                errors["base"] = "cannot_connect"
            except Timeout:
                errors["base"] = "timeout_connect"
            except HTTPError as http_err:
                if http_err.response.status_code == 401:
                    # Try to parse the response to check for OTP requirement or other error
                    try:
                        error_data = http_err.response.json()
                        _LOGGER.debug("401 response content: %s", error_data)
                        
                        if error_data.get("message") == "OTP needed":
                            # OTP is required, proceed to OTP step
                            return await self.async_step_otp()
                        else:
                            # Handle specific error messages
                            error_message = error_data.get("message", "")
                            if "not registered" in error_message.lower():
                                errors["base"] = "invalid_user"
                            elif "incorrect password" in error_message.lower():
                                errors["base"] = "invalid_password"
                            else:
                                errors["base"] = "auth_failed"
                            _LOGGER.error("Authentication error: %s", error_message)
                    except Exception as ex:
                        _LOGGER.error("Error parsing 401 response: %s", str(ex))
                        errors["base"] = "auth_failed"
                else:
                    errors["base"] = "unknown"
            except Exception as ex:
                _LOGGER.error("Unexpected error: %s", str(ex))
                errors["base"] = "unknown"

        # Prepare schema for server details
        schema = {
            vol.Required(CONF_HOST): str,
            vol.Required(CONF_USERNAME): str,
            vol.Required(CONF_PASSWORD): str,
        }
        if server_type != SERVER_TYPE_HOSTED:
            schema[vol.Optional(CONF_PORT, default=DEFAULT_PORT_SERVER)] = int
            schema[vol.Optional(CONF_USE_SSL, default=False)] = bool

        return self.async_show_form(
            step_id="server_details",
            data_schema=vol.Schema(schema),
            errors=errors,
        )
        
    async def async_step_otp(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        """Handle OTP verification step."""
        errors = {}

        if user_input is not None:
            otp_code = user_input[CONF_OTP]
            
            try:
                # Try authentication again with OTP code
                response = await self.hass.async_add_executor_job(
                    self._test_connection_with_otp, 
                    self.api_url,
                    self.server_connection_info[CONF_USERNAME],
                    self.server_connection_info[CONF_PASSWORD],
                    otp_code
                )
                
                if response and response.get("success"):
                    return self.async_create_entry(
                        title=f"PiSignage ({self.server_connection_info[CONF_API_HOST]})",
                        data=self.server_connection_info,
                    )
                else:
                    error_message = response.get("message", "") if response else ""
                    _LOGGER.error("OTP authentication failed: %s", error_message)
                    errors["base"] = "otp_failed"
            except (ConnectionError, HTTPError, Timeout):
                errors["base"] = "cannot_connect"
            except Exception as ex:
                _LOGGER.error("Unexpected error during OTP verification: %s", str(ex))
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="otp",
            data_schema=vol.Schema({
                vol.Required(CONF_OTP): str,
            }),
            errors=errors,
        )

    def _test_connection(self, api_url, username, password, server_type):
        """Test connection to PiSignage and return authentication token."""
        _LOGGER.debug("Testing PiSignage connection to: %s (server type: %s)", api_url, server_type)
        
        try:
            session = requests.Session()
            
            # Different authentication approach based on server type
            if server_type == SERVER_TYPE_OPEN_SOURCE:
                # For open source server, use basic auth
                session.auth = (username, password)
                
                # Simply try to get the players list to verify credentials
                response = session.get(
                    f"{api_url}/players",
                    timeout=10,
                )
                
                _LOGGER.debug("Got response status code: %s", response.status_code)
                
                # Check for successful status code
                response.raise_for_status()
                
                # Try to parse as JSON to validate response format
                result = response.json()
                
                # If we got this far, authentication was successful
                return {"success": True}
                
            else:
                # For hosted service, use token-based auth
                auth_payload = {
                    "email": username,
                    "password": password,
                    "getToken": True
                }
                
                _LOGGER.debug("Sending authentication request with payload: %s", 
                            {**auth_payload, "password": "***REDACTED***"})
                
                response = session.post(
                    f"{api_url}/session",
                    json=auth_payload,
                    timeout=10,
                )
                
                _LOGGER.debug("Got response status code: %s", response.status_code)
                
                # Try to decode JSON regardless of status code to handle error messages
                try:
                    result = response.json()
                    _LOGGER.debug("Response content: %s", result)
                    
                    # Special handling for OTP required
                    if response.status_code == 401 and result.get("message") == "OTP needed":
                        _LOGGER.debug("OTP authentication required")
                        return result
                        
                    # Check for non-200 status code after handling special cases
                    response.raise_for_status()
                    
                    # Check for successful response - either a "success" field or presence of token
                    if result.get("token"):
                        _LOGGER.debug("Authentication successful, token found in response")
                        # Create a compatible response structure
                        return {"success": True, "data": {"token": result.get("token")}}
                    elif result.get("success") is False:
                        _LOGGER.error("Authentication failed with message: %s", 
                                    result.get("stat_message", "Unknown error"))
                        return result
                    else:
                        _LOGGER.error("Ambiguous authentication response, no success flag or token found")
                        return {"success": False, "stat_message": "Ambiguous response"}
                except ValueError as ex:
                    # Handle case where response isn't JSON
                    _LOGGER.error("Response isn't valid JSON: %s", str(ex))
                    _LOGGER.debug("Response content: %s", response.text)
                    raise
                    
        except requests.exceptions.JSONDecodeError as ex:
            _LOGGER.error("Failed to decode JSON response from server: %s", str(ex))
            _LOGGER.debug("Response content: %s", response.text if 'response' in locals() else "No response")
            raise
        except requests.exceptions.ConnectionError as ex:
            _LOGGER.error("Connection error to PiSignage server: %s", str(ex))
            raise
        except requests.exceptions.RequestException as ex:
            _LOGGER.error("Request error to PiSignage server: %s", str(ex))
            _LOGGER.debug("Response content: %s", response.text if 'response' in locals() else "No response")
            raise
            
    def _test_connection_with_otp(self, api_url, username, password, otp_code):
        """Test connection to PiSignage with OTP code and return authentication token."""
        session_url = f"{api_url}/session"
        _LOGGER.debug("Testing PiSignage connection with OTP to: %s", session_url)
        
        try:
            session = requests.Session()
            
            # Format authentication payload with OTP code
            auth_payload = {
                "email": username,
                "password": password,
                "code": otp_code,
                "getToken": True
            }
            
            _LOGGER.debug("Sending authentication request with OTP and payload: %s", 
                         {**auth_payload, "password": "***REDACTED***", "code": "***REDACTED***"})
            
            response = session.post(
                session_url,
                json=auth_payload,
                timeout=10,
            )
            
            _LOGGER.debug("Got response status code: %s", response.status_code)
            
            # Try to decode JSON regardless of status code
            try:
                result = response.json()
                _LOGGER.debug("OTP auth response content: %s", result)
                
                # Check for non-200 status code after parsing JSON
                response.raise_for_status()
                
                # Check for successful response - either a "success" field or presence of token
                if result.get("token"):
                    _LOGGER.debug("Authentication with OTP successful, token found in response")
                    # Create a compatible response structure
                    return {"success": True, "data": {"token": result.get("token")}}
                else:
                    _LOGGER.error("Authentication with OTP failed")
                    return {"success": False, "stat_message": "OTP authentication failed",
                           "message": result.get("message", "Unknown error")}
            except ValueError as ex:
                # Handle case where response isn't JSON
                _LOGGER.error("OTP Response isn't valid JSON: %s", str(ex))
                _LOGGER.debug("OTP Response content: %s", response.text)
                raise
                
        except Exception as ex:
            _LOGGER.error("Error in OTP authentication: %s", str(ex))
            raise
            
    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return PiSignageOptionsFlow(config_entry)


class PiSignageOptionsFlow(config_entries.OptionsFlow):
    """Handle PiSignage options."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.options = dict(config_entry.options)
        # Initialize ignore_cec dictionary if it doesn't exist
        if CONF_IGNORE_CEC not in self.options:
            self.options[CONF_IGNORE_CEC] = {}

    async def async_step_init(self, user_input=None):
        """Handle options flow."""
        if user_input is not None:
            # Process user input from the multi-select
            new_ignore_cec = {}
            selected_players = user_input.get(CONF_IGNORE_CEC, [])
            
            # Get all players from coordinator to process all players (both selected and unselected)
            coordinator = self.hass.data[DOMAIN][self.config_entry.entry_id]["coordinator"]
            players = coordinator.data.get(CONF_PLAYERS, [])
            
            # Set the ignore_cec value to True for selected players, False otherwise
            for player in players:
                player_id = player.get("_id")
                # If player_id is in the selected list, set to True, otherwise False
                new_ignore_cec[player_id] = player_id in selected_players
            
            self.options[CONF_IGNORE_CEC] = new_ignore_cec
            return self.async_create_entry(title="", data=self.options)

        # Get all players from coordinator
        coordinator = self.hass.data[DOMAIN][self.config_entry.entry_id]["coordinator"]
        players = coordinator.data.get(CONF_PLAYERS, [])
        
        if not players:
            return self.async_abort(reason="no_players_found")
        
        # Create a dictionary of player ID -> player name for the multi_select
        player_dict = {}
        for player in players:
            player_id = player.get("_id")
            player_name = player.get("name", f"Player {player_id}")
            player_dict[player_id] = player_name
        
        # Get list of player IDs where ignore_cec is currently True
        current_selections = [
            player_id 
            for player_id, ignore in self.options.get(CONF_IGNORE_CEC, {}).items() 
            if ignore
        ]
        
        import homeassistant.helpers.config_validation as cv
        
        return self.async_show_form(
            step_id="init", 
            data_schema=vol.Schema({
                vol.Optional(
                    CONF_IGNORE_CEC,
                    default=current_selections,
                ): cv.multi_select(player_dict),
            }),
            description_placeholders={"players_count": str(len(players))},
        )