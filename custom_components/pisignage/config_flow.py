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
    DEFAULT_PORT_SERVER,
)

_LOGGER = logging.getLogger(__name__)


class PiSignageConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for PiSignage."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    async def async_step_user(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        """Handle the initial step to select server type."""
        errors = {}

        if user_input is not None:
            self.context["server_type"] = user_input[CONF_SERVER_TYPE]
            return await self.async_step_server_details()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_SERVER_TYPE, default=SERVER_TYPE_OPEN_SOURCE): vol.In([
                    SERVER_TYPE_HOSTED,
                    SERVER_TYPE_OPEN_SOURCE
                ])
            }),
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

            # Test connection
            try:
                response = await self.hass.async_add_executor_job(
                    self._test_connection, api_url, username, password
                )
                if response and response.get("success"):
                    return self.async_create_entry(
                        title=f"PiSignage ({host if server_type != SERVER_TYPE_HOSTED else host})",
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
                    errors["base"] = "auth_failed"
            except ConnectionError:
                errors["base"] = "cannot_connect"
            except Timeout:
                errors["base"] = "timeout_connect"
            except Exception:
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