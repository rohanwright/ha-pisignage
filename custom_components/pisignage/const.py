"""Constants for the PiSignage integration."""

DOMAIN = "pisignage"

# Configuration
CONF_API_SERVER = "api_server"
CONF_SERVER_TYPE = "server_type"
CONF_API_HOST = "host"
CONF_API_PORT = "port" 
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_OTP = "otp"
CONF_PLAYERS = "players"
CONF_PLAYER_ID = "player_id"
CONF_PLAYER_NAME = "player_name"
CONF_USE_SSL = "use_ssl"
CONF_IGNORE_CEC = "ignore_cec"

# Server types
SERVER_TYPE_HOSTED = "hosted"
SERVER_TYPE_OPEN_SOURCE = "open_source"
SERVER_TYPE_PLAYER = "player"

DEFAULT_PORT_SERVER = 3000

# Platform types
MEDIA_PLAYER = "media_player"
SENSOR = "sensor"

# Attributes
ATTR_PLAYLISTS = "playlists"
ATTR_GROUP = "group"
ATTR_STATUS = "status"
ATTR_VERSION = "version"
ATTR_IP = "ip_address"
ATTR_LAST_SEEN = "last_seen"
ATTR_CURRENT_PLAYLIST = "current_playlist"
ATTR_CURRENT_FILE = "current_file"
ATTR_FREE_SPACE = "free_space"
ATTR_TV_STATUS = "tv_status"

# Scan interval
SCAN_INTERVAL_SECONDS = 30