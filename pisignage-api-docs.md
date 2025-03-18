# piSignage API Documentation

This document provides details for the key API endpoints of the piSignage platform, focusing on Session, Playlist, Player, Group, and Category operations.

## Authentication

Most endpoints require authentication. After logging in using the `/session` endpoint, you'll receive a token that should be included in subsequent requests either as a header `x-access-token` or as a query parameter `token`.

## 1. Session Management

### 1.1 Login to Server `/session` [POST]

Log in to the server and obtain an authentication token.

**Request Body:**
```json
{
  "email": "username_or_email",
  "password": "your_password",
  "getToken": true
}
```

**Response:**
```json
{
  "userInfo": {
    "_id": "user_id",
    "username": "username",
    "email": "email@example.com",
    "settings": {
      // User settings
    }
  },
  "token": "jwt_token_value"
}
```

### 1.2 Logout from Server `/session` [DELETE]

Log out and invalidate the current session.

**Response:**
```json
{
  "success": true
}
```

### 1.3 Login with Token `/token-session` [POST]

Log in using a previously obtained token.

**Request Body:**
```json
{
  "token": "your_jwt_token"
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "_id": "user_id",
    "username": "username",
    "email": "email@example.com",
    "settings": {
      // User settings
    }
  }
}
```

## 2. Playlist Management

### 2.1 Get All Playlists `/playlists` [GET]

Retrieve a list of all playlists.

**Response:**
```json
{
  "stat_message": "Sending playlist list",
  "success": true,
  "data": [
    {
      "name": "playlist_name",
      "version": 4,
      "layout": "1",
      "templateName": "template_name",
      "assets": [
        {
          "filename": "asset_filename",
          "duration": 10,
          "isVideo": false,
          "selected": true
        }
      ],
      "settings": {
        "ticker": {
          "enable": false,
          "behavior": "slide",
          "messages": "ticker message"
        }
      }
    }
  ]
}
```

### 2.2 Create New Playlist `/playlists` [POST]

Create a new playlist.

**Request Body:**
```json
{
  "file": "New Playlist Name"
}
```

**Response:**
```json
{
  "stat_message": "Playlist Created: ",
  "success": true,
  "data": "New Playlist Name"
}
```

### 2.3 Get Playlist Details `/playlists/{playlistName}` [GET]

Get information about a specific playlist.

**Parameters:**
- `playlistName` (path): Name of the playlist

**Response:**
```json
{
  "stat_message": "Sending playlist content",
  "success": true,
  "data": {
    "name": "playlist_name",
    "version": 4,
    "layout": "1",
    "assets": [
      {
        "filename": "asset_filename",
        "duration": 10,
        "isVideo": false,
        "selected": true
      }
    ],
    "settings": {
      "ticker": {
        "enable": false,
        "behavior": "slide",
        "messages": "ticker message"
      }
    }
  }
}
```

### 2.4 Update Playlist `/playlists/{playlistName}` [POST]

Update a playlist's details.

**Parameters:**
- `playlistName` (path): Name of the playlist to update

**Request Body:**
```json
{
  "name": "playlist_name",
  "layout": "1",
  "assets": [
    {
      "filename": "asset_filename",
      "duration": 10,
      "isVideo": false,
      "selected": true
    }
  ],
  "settings": {
    "ticker": {
      "enable": true,
      "behavior": "slide",
      "messages": "updated ticker message"
    }
  }
}
```

**Response:**
```json
{
  "stat_message": "Playlist Saved: ",
  "success": true,
  "data": {
    "name": "playlist_name",
    "layout": "1",
    "assets": [
      {
        "filename": "asset_filename",
        "duration": 10,
        "isVideo": false,
        "selected": true
      }
    ],
    "settings": {
      "ticker": {
        "enable": true,
        "behavior": "slide",
        "messages": "updated ticker message"
      }
    }
  }
}
```

### 2.5 Update Playlist Assets `/playlistfiles` [POST]

Update the assets in a playlist.

**Request Body:**
```json
{
  "playlist": "playlist_name",
  "assets": ["asset1.mp4", "asset2.jpg", "asset3.png"]
}
```

**Response:**
```json
{
  "stat_message": "asset update has been queued",
  "success": true
}
```

## 3. Player Management

### 3.1 Get All Players `/players` [GET]

Get information about all players.

**Parameters:**
- `group` (query): Filter by group ID
- `groupName` (query): Filter by group name
- `string` (query): Filter by player name (case-insensitive)
- `location` (query): Filter by location
- `label` (query): Filter by category
- `currentPlaylist` (query): Filter by current playlist
- `version` (query): Filter by software version
- `page` (query): Page number
- `per_page` (query): Number of items per page

**Response:**
```json
{
  "stat_message": "sending Player list",
  "success": true,
  "data": {
    "objects": [
      {
        "_id": "player_id",
        "name": "player_name",
        "cpuSerialNumber": "serial_number",
        "group": {
          "_id": "group_id",
          "name": "group_name"
        },
        "version": "2.4.5",
        "ip": "192.168.1.100",
        "currentPlaylist": "playlist_name",
        "tvStatus": true
      }
    ],
    "page": 1,
    "pages": 1,
    "count": 5,
    "currentVersion": {
      "version": "2.4.5",
      "platform_version": "stretch_9.6_admin_2019-01-30",
      "beta": "2.4.6"
    }
  }
}
```

### 3.2 Create New Player `/players` [POST]

Create a new player.

**Request Body:**
```json
{
  "name": "New Player",
  "cpuSerialNumber": "1234567890123456",
  "TZ": "Asia/Calcutta",
  "group": {
    "_id": "group_id",
    "name": "group_name"
  },
  "labels": ["label1", "label2"]
}
```

**Response:**
```json
{
  "stat_message": "new Player added successfully",
  "success": true,
  "data": {
    "_id": "new_player_id",
    "name": "New Player",
    "cpuSerialNumber": "1234567890123456",
    "TZ": "Asia/Calcutta",
    "group": {
      "_id": "group_id",
      "name": "group_name"
    },
    "labels": ["label1", "label2"]
  }
}
```

### 3.3 Get Player Details `/players/{playerId}` [GET]

Get information about a specific player.

**Parameters:**
- `playerId` (path): ID of the player

**Response:**
```json
{
  "stat_message": "Player details",
  "success": true,
  "data": {
    "_id": "player_id",
    "name": "player_name",
    "cpuSerialNumber": "serial_number",
    "group": {
      "_id": "group_id",
      "name": "group_name"
    },
    "version": "2.4.5",
    "ip": "192.168.1.100",
    "currentPlaylist": "playlist_name",
    "tvStatus": true
  }
}
```

### 3.4 Update Player `/players/{playerId}` [POST]

Update a player's details.

**Parameters:**
- `playerId` (path): ID of the player

**Request Body:**
```json
{
  "name": "Updated Player Name",
  "TZ": "America/New_York",
  "labels": ["new_label1", "new_label2"],
  "group": {
    "_id": "new_group_id",
    "name": "new_group_name"
  }
}
```

**Response:**
```json
{
  "stat_message": "updated Player details",
  "success": true,
  "data": {
    "_id": "player_id",
    "name": "Updated Player Name",
    "cpuSerialNumber": "serial_number",
    "TZ": "America/New_York",
    "labels": ["new_label1", "new_label2"],
    "group": {
      "_id": "new_group_id",
      "name": "new_group_name"
    }
  }
}
```

### 3.5 Delete Player `/players/{playerId}` [DELETE]

Remove a player.

**Parameters:**
- `playerId` (path): ID of the player

**Response:**
```json
{
  "stat_message": "Player record deleted successfully",
  "success": true
}
```

### 3.6 Get All Players Including Collaborators `/screens` [GET]

Get information about all players including those from collaborator accounts.

**Parameters:**
- `onlyInstallation` (query): If present, return only the user's players, not collaborators'

**Response:**
Similar to the `/players` endpoint response.

### 3.7 Control TV `/pitv/{playerId}` [POST]

Turn the TV connected to a player on or off.

**Parameters:**
- `playerId` (path): ID of the player

**Request Body:**
```json
{
  "status": false
}
```

**Response:**
```json
{
  "stat_message": "TV command issued",
  "success": true
}
```

### 3.8 Playlist Media Controls `/playlistmedia/{playerId}/{action}` [POST]

Control playback (next, previous, pause/play).

**Parameters:**
- `playerId` (path): ID of the player
- `action` (path): One of "pause", "backward", "forward"

**Response:**
```json
{
  "stat_message": "Playlist is paused",
  "success": true,
  "data": {
    "isPaused": true
  }
}
```

### 3.9 Play Specific Playlist `/setplaylist/{playerId}/{playlist}` [POST]

Play a specific playlist once.

**Parameters:**
- `playerId` (path): ID of the player
- `playlist` (path): Name of the playlist to play

**Response:**
```json
{
  "stat_message": "Playlist change response",
  "success": true,
  "data": {
    "msg": "Successfully changed playlist",
    "playlist": "current playlist name"
  }
}
```

## 4. Group Management

### 4.1 Get All Groups `/groups` [GET]

Get information about all groups.

**Parameters:**
- `string` (query): Filter by group name (case-insensitive)
- `all` (query): Include pseudo-groups for players not in any group
- `page` (query): Page number
- `per_page` (query): Number of items per page

**Response:**
```json
{
  "stat_message": "sending Group list",
  "success": true,
  "data": [
    {
      "_id": "group_id",
      "name": "group_name",
      "playlists": [
        {
          "name": "playlist_name",
          "settings": {
            "ads": {
              "adPlaylist": false,
              "noMainPlay": false
            }
          }
        }
      ],
      "labels": ["label1", "label2"],
      "orientation": "landscape",
      "resolution": "auto"
    }
  ]
}
```

### 4.2 Create New Group `/groups` [POST]

Create a new group.

**Request Body:**
```json
{
  "name": "New Group",
  "orientation": "landscape",
  "resolution": "auto",
  "labels": ["label1", "label2"]
}
```

**Response:**
```json
{
  "stat_message": "new Group added successfully",
  "success": true,
  "data": {
    "_id": "new_group_id",
    "name": "New Group",
    "orientation": "landscape",
    "resolution": "auto",
    "labels": ["label1", "label2"]
  }
}
```

### 4.3 Get Group Details `/groups/{groupId}` [GET]

Get information about a specific group.

**Parameters:**
- `groupId` (path): ID of the group

**Response:**
```json
{
  "stat_message": "Group details",
  "success": true,
  "data": {
    "_id": "group_id",
    "name": "group_name",
    "playlists": [
      {
        "name": "playlist_name",
        "settings": {
          "ads": {
            "adPlaylist": false,
            "noMainPlay": false
          }
        }
      }
    ],
    "labels": ["label1", "label2"],
    "orientation": "landscape",
    "resolution": "auto"
  }
}
```

### 4.4 Update Group `/groups/{groupId}` [POST]

Update a group's details and optionally deploy it.

**Parameters:**
- `groupId` (path): ID of the group

**Request Body:**
```json
{
  "name": "Updated Group Name",
  "deploy": true,
  "playlists": [
    {
      "name": "playlist_name",
      "settings": {
        "ads": {
          "adPlaylist": true,
          "adInterval": 60
        }
      }
    }
  ],
  "orientation": "portrait",
  "resolution": "1080p"
}
```

**Response:**
```json
{
  "stat_message": "updated Group details",
  "success": true,
  "data": {
    "_id": "group_id",
    "name": "Updated Group Name",
    "playlists": [
      {
        "name": "playlist_name",
        "settings": {
          "ads": {
            "adPlaylist": true,
            "adInterval": 60
          }
        }
      }
    ],
    "orientation": "portrait",
    "resolution": "1080p"
  }
}
```

### 4.5 Delete Group `/groups/{groupId}` [DELETE]

Remove a group.

**Parameters:**
- `groupId` (path): ID of the group

**Response:**
```json
{
  "stat_message": "Group record deleted successfully",
  "success": true
}
```

## 5. Category Management

### 5.1 Get All Categories `/labels` [GET]

Get all categories.

**Parameters:**
- `page` (query): Page number
- `per_page` (query): Number of items per page
- `string` (query): Filter by category name
- `mode` (query): Filter by category type (players, groups, playlists, or assets)

**Response:**
```json
{
  "stat_message": "sending Label list",
  "success": true,
  "data": [
    {
      "_id": "label_id",
      "name": "label_name",
      "mode": "assets",
      "installation": "username"
    }
  ]
}
```

### 5.2 Create New Category `/labels` [POST]

Create a new category.

**Request Body:**
```json
{
  "name": "New Label",
  "mode": "players"
}
```

**Response:**
```json
{
  "name": "New Label",
  "_id": "new_label_id",
  "mode": "players",
  "installation": "username"
}
```

### 5.3 Get Category Details `/labels/{labelId}` [GET]

Get details of a specific category.

**Parameters:**
- `labelId` (path): ID of the category

**Response:**
```json
{
  "name": "label_name",
  "_id": "label_id",
  "mode": "assets",
  "installation": "username"
}
```

### 5.4 Update Category `/labels/{labelId}` [POST]

Update a category.

**Parameters:**
- `labelId` (path): ID of the category

**Request Body:**
```json
{
  "name": "Updated Label Name",
  "mode": "players"
}
```

**Response:**
```json
{
  "stat_message": "updated Label details",
  "success": true,
  "data": {
    "name": "Updated Label Name",
    "_id": "label_id",
    "mode": "players",
    "installation": "username"
  }
}
```

### 5.5 Delete Category `/labels/{labelId}` [DELETE]

Delete a category.

**Parameters:**
- `labelId` (path): ID of the category

**Response:**
```json
{
  "stat_message": "Label deleted successfully",
  "success": true
}
```
