# PiSignage Home Assistant Integration

A Custom Integration for Home Assistant to connect with PiSignage Server (Open Source or Hosted PiSignage.com)

## Features

- Control PiSignage players
- Switch between playlists (Will Switch the default playlist for the group)
- Power on/off connected TVs with CEC
- Sensors for player data

## Installation

### HACS (Recommended)

1. Ensure [HACS](https://hacs.xyz/) is installed in your Home Assistant instance
2. Add this repository as a custom repository in HACS:
   - Go to HACS → Integrations → ⋮ (three dots) → Custom repositories
   - Add URL: `https://github.com/rohanwright/ha-pisignage`
   - Category: Integration
3. Click "Install" on the PiSignage integration
4. Restart Home Assistant

### Manual Installation

1. Download this repository
2. Copy the `custom_components/pisignage` directory to your Home Assistant's `custom_components` directory
3. Restart Home Assistant

## Configuration

1. Go to Home Assistant → Settings → Devices & Services → Add Integration
2. Search for "PiSignage" and select it
3. Enter your PiSignage server details:
   - Host: IP address or hostname of your PiSignage open source server, or the username of your hosted service (<u>username<u>.pisignage.com)
   - Port: Open Source Server port (default: 3000, Not needed for hosted)
   - Username: Your PiSignage username or email address
   - Password: Your PiSignage password
4. Click "Submit" to connect

## Available Entities

For each PiSignage player, the integration creates a device with the name of the player. Connected to the device is the following entities:

### Media Player

- Control the current playlist on the player (play/pause, next/previous item in the playlist)
- Select playlists from the source list which will update the primary playlist within the group and deploy
- Turn connected TV on/off with CEC if supported

### Sensors

- **Status**: Shows the current player status
- **CurrentPlalist**: Reports the device temperature (if available)
- **Storage**: Shows used storage space
- **Player IP**: The local IP address of the player
- **Location**: The configured location in PiSignage

## Services

### play_playlist

Start playing a specific playlist on a PiSignage player.

| Field | Type | Description |
| ----- | ---- | ----------- |
| entity_id | string | The player entity ID |
| playlist | string | Name of the playlist to play |

Example:
```yaml
service: pisignage.play_playlist
target:
  entity_id: media_player.pisignage_lobby
data:
  playlist: "Welcome Playlist"
```

### tv_control

Turn on or off the TV connected to the PiSignage player.

| Field | Type | Description |
| ----- | ---- | ----------- |
| entity_id | string | The player entity ID |
| status | string | Either "on" or "off" |

Example:
```yaml
service: pisignage.tv_control
target:
  entity_id: media_player.pisignage_lobby
data:
  status: "off"
```

## Automation Examples

### Turn on displays in the morning and off at night

```yaml
# Morning automation
automation:
  - alias: "Turn on digital signage in the morning"
    trigger:
      - platform: time
        at: "08:00:00"
    action:
      - service: media_player.turn_on
        target:
          entity_id: media_player.pisignage_lobby

# Evening automation
  - alias: "Turn off digital signage at night"
    trigger:
      - platform: time
        at: "19:00:00"
    action:
      - service: media_player.turn_off
        target:
          entity_id: media_player.pisignage_lobby
```

### Switch playlist based on time of day

```yaml
automation:
  - alias: "Switch to morning playlist"
    trigger:
      - platform: time
        at: "08:00:00"
    action:
      - service: media_player.select_source
        target:
          entity_id: media_player.pisignage_lobby
        data:
          source: "Morning Announcements"

  - alias: "Switch to afternoon playlist"
    trigger:
      - platform: time
        at: "12:00:00"
    action:
      - service: media_player.select_source
        target:
          entity_id: media_player.pisignage_lobby
        data:
          source: "Afternoon Announcements"
```

## Troubleshooting

- **Connection Issues**: Ensure your Home Assistant instance can reach your PiSignage server and that the credentials are correct.
- **Missing Players**: Make sure your players are registered with the PiSignage server and are online.
- **Playlist Control**: If playlist switching doesn't work, verify that the playlist names match exactly (case-sensitive).

## Credit

This integration was developed independently for the Home Assistant community. PiSignage is a product of Ariemtech Pvt. Ltd. This integration is not officially affiliated with or endorsed by Ariemtech.
