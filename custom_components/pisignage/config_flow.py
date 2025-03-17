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

from .const import (
    DOMAIN,
    CONF_API_HOST,
    CONF_API_PORT,
    CONF_SERVER_TYPE,
    CONF_USE_SSL,
    SERVER_TYPE_HOSTED,
    SERVER_TYPE_OPEN_SOURCE,
    SERVER_TYPE_PLAYER,
    DEFAULT_PORT_SERVER,
    DEFAULT_PORT_PLAYER,
    DEFAULT_PATH,
)

_LOGGER = logging.getLogger(__name__)


class PiSignageConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for PiSignage."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            # Process the selected server type
            server_type = user_input[CONF_SERVER_TYPE]
            host = user_input[CONF_HOST]
            use_ssl = user_input.get(CONF_USE_SSL, server_type == SERVER_TYPE_HOSTED)
            
            # Set the appropriate port based on server type
            if server_type == SERVER_TYPE_PLAYER:
                port = user_input.get(CONF_PORT, DEFAULT_PORT_PLAYER)
            else:
                port = user_input.get(CONF_PORT, DEFAULT_PORT_SERVER)
                
            username = user_input[CONF_USERNAME]
            password = user_input[CONF_PASSWORD]

            _LOGGER.info(
                "Attempting to set up PiSignage %s at %s", 
                server_type, 
                f"{host}:{port}" if server_type != SERVER_TYPE_HOSTED else f"{username}.pisignage.com"
            )

            # Check if already configured
            await self.async_set_unique_id(f"{host}_{username}")
            self._abort_if_unique_id_configured()

            # Construct API URL based on server type
            if server_type == SERVER_TYPE_HOSTED:
                # For hosted servers, the format is: https://username.pisignage.com/api
                # Always use HTTPS for hosted servers
                api_url = f"https://{username}.pisignage.com{DEFAULT_PATH}"
                _LOGGER.debug("Using hosted server URL: %s", api_url)
            else:
                # For open source servers or players
                protocol = "https" if use_ssl else "http"
                api_url = f"{protocol}://{host}:{port}{DEFAULT_PATH}"
                _LOGGER.debug("Using local server URL: %s", api_url)
                
            # Test connection
            try:
                _LOGGER.debug("Testing connection to PiSignage server")
                response = await self.hass.async_add_executor_job(
                    self._test_connection, api_url, username, password
                )
                
                if response and response.get("success"):
                    _LOGGER.info("Successfully connected to PiSignage server")
                    return self.async_create_entry(
                        title=f"PiSignage ({host if server_type != SERVER_TYPE_HOSTED else username})",
                        data={
                            CONF_SERVER_TYPE: server_type,
                            CONF_API_HOST: host,
                            CONF_API_PORT: port,
                            CONF_USERNAME: username,
                            CONF_PASSWORD: password,
                            CONF_USE_SSL: use_ssl,
                        },
                    )
                else:
                    _LOGGER.error(
                        "Authentication failed: %s", 
                        response.get("stat_message", "Unknown error") if response else "No response"
                    )
                    errors["base"] = "auth_failed"
            except ConnectionError as ex:
                _LOGGER.error("Connection error while setting up PiSignage: %s", ex)
                errors["base"] = "cannot_connect"
            except Timeout as ex:
                _LOGGER.error("Timeout while setting up PiSignage: %s", ex)
                errors["base"] = "timeout_connect"
            except Exception as ex:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception while setting up PiSignage: %s", ex)
                errors["base"] = "unknown"

        # Show form with server type options
        server_type_options = [
            SERVER_TYPE_HOSTED,
            SERVER_TYPE_OPEN_SOURCE,
            SERVER_TYPE_PLAYER
        ]
        
        # Prepare the form schema
        schema = {
            vol.Required(CONF_SERVER_TYPE, default=SERVER_TYPE_OPEN_SOURCE): vol.In(server_type_options),
            vol.Required(CONF_HOST): str,
            vol.Required(CONF_USERNAME): str,
            vol.Required(CONF_PASSWORD): str,
        }
        
        # Conditionally add port and SSL options based on selected server type
        if user_input is None or user_input.get(CONF_SERVER_TYPE) != SERVER_TYPE_HOSTED:
            default_port = DEFAULT_PORT_PLAYER if user_input and user_input.get(CONF_SERVER_TYPE) == SERVER_TYPE_PLAYER else DEFAULT_PORT_SERVER
            schema[vol.Optional(CONF_PORT, default=default_port)] = int
            
            # Only add SSL option for non-hosted servers (hosted always uses SSL)
            if user_input is None or user_input.get(CONF_SERVER_TYPE) != SERVER_TYPE_HOSTED:
                schema[vol.Optional(CONF_USE_SSL, default=False)] = bool

        _LOGGER.debug("Showing PiSignage configuration form")
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(schema),
            errors=errors,
        )

    def _test_connection(self, api_url, username, password):
        """Test connection to PiSignage and return authentication token."""
        session_url = f"{api_url}/session"
        _LOGGER.debug("Testing PiSignage connection to: %s", session_url)
        
        try:
            session = requests.Session()
            
            # Format authentication payload according to API docs
            auth_payload = {
                "email": username,
                "password": password,
                "getToken": True  # Using boolean true, not string "true"
            }
            
            _LOGGER.debug("Sending authentication request with payload: %s", 
                         {**auth_payload, "password": "***REDACTED***"})
            
            response = session.post(
                session_url,
                json=auth_payload,
                timeout=10,
            )
            
            _LOGGER.debug("Got response status code: %s", response.status_code)
            
            # Log headers for debugging
            _LOGGER.debug("Response headers: %s", dict(response.headers))
            
            # Check for non-200 status code
            response.raise_for_status()
            
            # Try to decode JSON
            try:
                result = response.json()
                
                # Log full response for debugging
                _LOGGER.debug("Full response: %s", result)
                
                # Check for successful response - either a "success" field or presence of token
                if result.get("success") is False:
                    # Explicit failure
                    _LOGGER.error("Authentication failed with message: %s", 
                                 result.get("stat_message", "Unknown error"))
                    return result
                elif "token" in result:
                    # Direct token response (different API format)
                    _LOGGER.debug("Authentication successful, token found in response")
                    # Create a compatible response structure
                    return {"success": True, "data": {"token": result.get("token")}}
                elif result.get("success") is True:
                    # Standard success response
                    _LOGGER.debug("Authentication successful, using standard response format")
                    return result
                else:
                    # No clear success/failure indicator
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