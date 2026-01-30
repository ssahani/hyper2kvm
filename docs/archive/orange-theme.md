# Orange Theme for hyper2kvm TUI

## Overview

The hyper2kvm TUI features a vibrant **orange theme** that provides an energetic, modern look while maintaining excellent readability. The theme is consistently applied across all three TUI implementations (Textual, Curses, CLI).

## Color Palette

### Primary Colors

| Color Name | Hex Code | Usage |
|------------|----------|-------|
| **Bright Orange** | `#ff6600` | Headers, key highlights, primary accents |
| **Gold-Orange** | `#ffaa44` | Border titles, secondary accents |
| **Light Orange** | `#ffbb66` | Primary text, content |
| **Medium Orange** | `#ff7722` | Borders, separators |
| **Light Orange-Yellow** | `#ffcc66` | Status bar text |

### Background Colors

| Color Name | Hex Code | Usage |
|------------|----------|-------|
| **Deep Dark Brown** | `#1a0f00` | Screen background |
| **Dark Orange-Brown** | `#261500` | Container backgrounds |
| **Medium Dark Brown** | `#331a00` | Widget backgrounds |
| **Darker Brown** | `#442200` | In-progress migration backgrounds |

### Status Colors

| Status | Color | Hex Code | Usage |
|--------|-------|----------|-------|
| **Success** | Green | `#66ff66` | Completed migrations |
| **Error** | Red | `#ff4444` | Failed migrations, errors |
| **In Progress** | Bright Orange | `#ffaa33` | Active migrations |
| **Pending** | Standard Orange | `#ff6600` | Waiting migrations |

## Theme Application

### Textual Dashboard (Tier 1)

The Textual implementation uses CSS-like styling:

```css
/* Header - Bright orange background */
Header {
    background: #ff6600;
    color: #fff;
    text-style: bold;
}

/* Container - Dark background with light orange border */
#migrations_container {
    border: heavy #ff8833;
    background: #261500;
    border-title-color: #ffaa44;
}

/* Status bar - Dark background with light text */
#status_bar {
    background: #331a00;
    border: heavy #ff8833;
    color: #ffcc66;
}
```

### Curses Dashboard (Tier 2)

The curses implementation uses ANSI color pairs:

```python
# Orange theme using curses color pairs
curses.init_pair(5, curses.COLOR_BLACK, curses.COLOR_YELLOW)  # Header
curses.init_pair(6, curses.COLOR_YELLOW, curses.COLOR_BLACK)  # Accent
curses.init_pair(3, curses.COLOR_YELLOW, curses.COLOR_BLACK)  # In-progress
```

### CLI Dashboard (Tier 3)

The CLI implementation uses ASCII art with color where supported:

```
================================================================================
                   hyper2kvm Migration Dashboard
================================================================================

[ACTIVE MIGRATIONS]
--------------------------------------------------------------------------------
  web-server-01        [IN-PROG]  45% [=====     ]
```

## Widget Theming

### Migration Status Widget

Different states have distinct color schemes:

```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓  ← Light orange border (#ff8833)
┃ 🔄 web-server-01 (vmware) - IN_PROGRESS ┃  ← Gold-orange text (#ffaa44)
┃ Stage: export | 45% [████████░░░░░░░]   ┃
┃ Throughput: 150.5 MB/s | Elapsed: 2m 30s┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
```

**Completed:** Green border (#66ff66) with light green background
**Failed:** Red border (#ff4444) with light red background
**In Progress:** Bright orange border (#ffaa33) with orange background
**Pending:** Standard orange border (#ff6600)

### Metrics Widget

```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓  ← Medium orange border (#ff7722)
┃ 📊 Migration Metrics                    ┃  ← Gold-orange title
┃ ────────────────────────────────────── ┃
┃ Active Migrations:     2                ┃  ← Light orange text (#ffbb66)
┃ Total Migrations:      10 (✅ 7 | ❌ 1) ┃
┃ Success Rate:          70.0%            ┃
┃ Avg Throughput:        145.3 MB/s       ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
```

## Theme Consistency

All three implementations maintain visual consistency:

### Textual (Best)
- Full color gradient support
- CSS-defined orange shades
- Smooth transitions

### Curses (Good)
- ANSI 256-color support where available
- Yellow/orange approximations on basic terminals
- Consistent layout with Textual

### CLI (Basic)
- ASCII borders and progress bars
- ANSI colors where supported
- Same information hierarchy

## Accessibility

The orange theme was designed with readability in mind:

✅ **High Contrast**: Light orange text on dark backgrounds (>7:1 ratio)
✅ **Distinct States**: Each status has a unique color (success=green, error=red, etc.)
✅ **Fallbacks**: Works even without color support
✅ **Icons**: Emoji icons supplement colors for better recognition

## Customization

While the orange theme is the default, you can customize it:

### Textual Dashboard

Modify the CSS in `hyper2kvm/tui/dashboard.py`:

```python
CSS = """
    Header {
        background: #0066ff;  /* Change to blue */
        color: #fff;
    }
    /* ... more customization ... */
"""
```

### Curses Dashboard

Modify color pairs in `hyper2kvm/tui/fallback_dashboard.py`:

```python
curses.init_pair(5, curses.COLOR_BLACK, curses.COLOR_BLUE)  # Blue header
```

## Screenshots

### Textual Dashboard
```
╔════════════════════════════════════════════════════════════════════════════╗
║                     hyper2kvm Migration Dashboard | 14:23:45              ║
╠════════════════════════════════════════════════════════════════════════════╣
║                                                                            ║
║ 📦 Active Migrations                                                       ║
║ ┌────────────────────────────────────────────────────────────────────────┐ ║
║ │ 🔄 web-server-01 (vmware) - IN_PROGRESS                                │ ║
║ │ Stage: export | 45% [████████░░░░░░░░░░░░░░░░]                        │ ║
║ │ Throughput: 150.5 MB/s | Elapsed: 2m 30s                               │ ║
║ └────────────────────────────────────────────────────────────────────────┘ ║
║                                                                            ║
║ ┌──────────────────────────┐ ┌──────────────────────────────────────────┐ ║
║ │ 📊 Migration Metrics     │ │ 📝 Migration Logs                        │ ║
║ │ ──────────────────────── │ │ [14:23:30] ✅ Dashboard initialized      │ ║
║ │ Active Migrations:     2 │ │ [14:23:35] ⏳ Waiting for migrations...  │ ║
║ │ Total Migrations:     10 │ │ [14:23:40] 🔄 web-server-01: export     │ ║
║ │ Success Rate:      70.0% │ │                                          │ ║
║ └──────────────────────────┘ └──────────────────────────────────────────┘ ║
║                                                                            ║
║ Last update: 14:23:45 | Active migrations: 2 | Press 'q' to quit          ║
╠════════════════════════════════════════════════════════════════════════════╣
║ q Quit │ r Refresh │ l Logs │ m Migrations │ d Dark Mode                  ║
╚════════════════════════════════════════════════════════════════════════════╝
```

## Why Orange?

The orange theme was chosen for several reasons:

1. **Energy & Warmth**: Orange conveys activity and progress
2. **Visibility**: Excellent contrast on dark backgrounds
3. **Professionalism**: Not as harsh as pure yellow, not as cold as blue
4. **Brand Recognition**: Distinctive and memorable
5. **Accessibility**: Works well for most color vision types

## Alternative Themes

While orange is the default, here are some other color schemes you might consider:

### Blue Theme (Professional)
- Primary: `#0066ff`
- Background: `#000f1a`
- Good for: Corporate environments

### Green Theme (Eco-Friendly)
- Primary: `#00cc66`
- Background: `#001a0f`
- Good for: Energy/environment projects

### Purple Theme (Creative)
- Primary: `#9966ff`
- Background: `#0f001a`
- Good for: Creative/design teams

### Cyberpunk Theme (Matrix)
- Primary: `#00ff00`
- Background: `#000000`
- Good for: Retro/hacker aesthetic

## Contributing

To propose a new theme:

1. Create a color palette with 8-10 colors
2. Test on all three dashboard types
3. Ensure accessibility (contrast ratios)
4. Document the theme
5. Submit a PR with examples

## License

LGPL-3.0-or-later
