# Custom Text Messages Per Cue

## Overview

Each playback entry in a cue's playback pool can now specify custom text messages that will be displayed when that playback is active. This allows you to tailor the text content to match the specific visual characteristics of each playback.

## UI Access

### Opening the Cue Editor

1. **Load Session**: Open MesmerGlass and load your session
2. **Navigate to Session Runner Tab**: Click the "Session Runner" tab
3. **Load Cuelist**: Click "📂 Load Cuelist..." and select your cuelist
4. **Select Cue**: Click on any cue in the cue list to select it
5. **Edit Cue**: Click "✏️ Edit Cue..." button

### Cue Editor Features

The Cue Editor dialog provides:

- **Basic Properties**:
  - Cue name
  - Duration (in seconds)
  - Selection mode (when to switch playbacks)

- **Playback Pool Management**:
  - Add/remove playback entries
  - Set weight (selection probability)
  - Set min/max duration per playback
  - **Custom text messages** per playback entry

### Adding Custom Text Messages

For each playback entry:

1. Find the "Custom Text Messages (optional)" section
2. Enter your text messages, **one per line**
3. Leave empty to use the playback's default text
4. Example:
   ```
   Focus on my words
   Let your mind relax
   Deeper and deeper
   ```

### Saving Changes

- Click "Save" to apply changes
- Changes are immediately saved to the session
- No need to restart the session - changes take effect on next playback switch

## Configuration

### Session JSON Format

Add a `text_messages` array to any playback entry in your cue's playback pool:

```json
{
  "playback_pool": [
    {
      "playback": "1",
      "weight": 1.0,
      "min_duration_s": 5.0,
      "max_duration_s": 10.0,
      "text_messages": [
        "Focus on my words",
        "Let your mind relax",
        "Deeper and deeper"
      ]
    },
    {
      "playback": "2",
      "weight": 1.0,
      "min_duration_s": 5.0,
      "max_duration_s": 10.0,
      "text_messages": [
        "Feel the spiral spinning",
        "Your thoughts are melting",
        "Surrender to the pattern"
      ]
    }
  ]
}
```

### Field Details

- **`text_messages`** (optional): Array of strings
  - Custom text messages to display when this playback is active
  - Overrides the playback's configured text settings
  - Randomly cycles through the messages in sync with media
  - If omitted, uses the playback's default text configuration

## Behavior

1. **When playback starts**: Custom text messages (if specified) are loaded into the text director
2. **Text cycling**: Messages cycle randomly in sync with media changes
3. **Text rendering**: Uses the playback's configured text mode (centered_sync, subtext, etc.)
4. **Fallback**: If no `text_messages` specified, uses the playback's configured text library

## Example Use Cases

### Intensity Progression
```json
{
  "cues": [
    {
      "name": "Gentle Introduction",
      "playback_pool": [
        {
          "playback": "slow_spiral",
          "text_messages": [
            "Relax and breathe",
            "Let yourself drift",
            "Nothing to worry about"
          ]
        }
      ]
    },
    {
      "name": "Deeper Trance",
      "playback_pool": [
        {
          "playback": "fast_spiral",
          "text_messages": [
            "Blank and empty",
            "Obey and submit",
            "Nothing but the spiral"
          ]
        }
      ]
    }
  ]
}
```

### Theme-Specific Messages
```json
{
  "playback_pool": [
    {
      "playback": "pink_spiral",
      "text_messages": [
        "Pink is your favorite color",
        "You love everything pink",
        "Pink makes you feel so good"
      ]
    },
    {
      "playback": "blue_spiral",
      "text_messages": [
        "Blue is calming and peaceful",
        "The blue spiral soothes you",
        "Drift into the blue"
      ]
    }
  ]
}
```

### Randomized Pool with Consistent Text
```json
{
  "playback_pool": [
    {
      "playback": "spiral_1",
      "weight": 2.0,
      "text_messages": ["Focus", "Obey", "Submit"]
    },
    {
      "playback": "spiral_2",
      "weight": 1.0,
      "text_messages": ["Focus", "Obey", "Submit"]
    },
    {
      "playback": "spiral_3",
      "weight": 1.0,
      "text_messages": ["Focus", "Obey", "Submit"]
    }
  ]
}
```

## Implementation Details

### Code Flow
1. `SessionRunner._start_cue()` or `_switch_playback()` selects a playback entry
2. Loads the playback configuration
3. Checks if `playback_entry.text_messages` exists
4. If yes: Calls `_apply_custom_text()` to override text director
5. Text director cycles through custom messages in sync with media

### Priority Order
1. **Custom text messages** (from cue's playback_pool entry) - highest priority
2. **Playback's text configuration** (from playback JSON) - default
3. **ThemeBank text** (if use_theme_bank=true) - fallback
4. **Sample text library** - ultimate fallback

### Compatibility
- Fully backward compatible - `text_messages` is optional
- Existing sessions without `text_messages` work exactly as before
- Can be added to any existing session by editing the JSON

## Tips

- Keep messages short (1-5 words) for readability
- Match message intensity to visual intensity (slow spiral = gentle text, fast spiral = direct commands)
- Use 3-10 messages per playback for good variety
- Text mode (centered_sync, subtext) is inherited from the playback's configuration
- Custom text applies immediately when playback switches (no delay)

## Related Documentation
- [Custom Modes](custom-modes-parity.md)
- [Text Rendering](text-rendering.md)
- [Sessions](sessions.md)
