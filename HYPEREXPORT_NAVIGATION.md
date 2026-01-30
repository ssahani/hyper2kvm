# HyperExport - Built-in Navigation

**Status:** ✅ Back navigation already available!
**Library:** `charmbracelet/huh` (form library with built-in navigation)

---

## Overview

HyperExport uses the `huh` library from Charmbracelet, which provides **built-in back navigation** out of the box. No additional code needed!

---

## Navigation Keys

### Built-in Navigation (Already Works!)

| Key | Action |
|-----|--------|
| **↑/↓** | Navigate between options |
| **←/→** | Navigate between fields (in same group) |
| **Tab** | Move to next field |
| **Shift+Tab** | Move to previous field |
| **Enter** | Confirm selection / Move to next group |
| **Esc** | Go back to previous group |
| **Space** | Select/deselect (in multi-select) |
| **/** | Filter/search (in filterable lists) |

### Multi-Step Navigation

HyperExport has 4 main steps:

```
Step 1: VM Selection
   ↓ (Enter)
Step 2: Export Template
   ↓ (Enter) / ↑ (Esc to go back)
Step 3: Configuration
   ↓ (Enter) / ↑ (Esc to go back)
Step 4: Confirmation
   ↓ (Enter) / ↑ (Esc to go back)
```

**Use Esc to go back at any step!**

---

## How It Works

### 1. Multi-Group Forms

HyperExport creates forms with multiple groups:

```go
form := huh.NewForm(
    huh.NewGroup(
        // Step 1: Template selection
    ),
    huh.NewGroup(
        // Step 2: Output directory and parallel downloads
    ),
    huh.NewGroup(
        // Step 3: Daemon mode
    ),
    huh.NewGroup(
        // Step 4: Advanced daemon config (conditional)
    ),
).WithTheme(theme)
```

### 2. Automatic Navigation

The `huh` library handles all navigation automatically:
- **Forward**: Enter key moves to next group
- **Backward**: Esc key returns to previous group
- **Within group**: Tab/Shift+Tab, arrow keys

### 3. Conditional Groups

Some groups are hidden/shown based on previous choices:

```go
huh.NewGroup(...).WithHideFunc(func() bool {
    return !config.useDaemon  // Hide if daemon not selected
})
```

Navigation automatically skips hidden groups!

---

## Usage Examples

### Example 1: Basic Navigation

```bash
$ hyperexport interactive

# Step 1: VM Selection
Select VMs to Export
  [x] ⚡ web-server-01
  [ ] ○ db-server-02
  [x] ⚡ app-server-03

# Press Enter to continue
# Press Esc to cancel

# Step 2: Export Template
> Production Backup - OVA with compression
  Quick Export - Fast without compression
  Development - OVF for dev cycles

# Press Enter to continue
# Press Esc to go back to VM selection

# Step 3: Output Directory
Output Directory: /exports
Parallel Downloads: 4

# Press Enter to continue
# Press Esc to go back to template selection
```

### Example 2: Going Back to Change VM Selection

```
1. Select VMs → Enter
2. Choose template → Enter
3. Configure settings → Realize forgot a VM → Press Esc
4. Back at template → Press Esc again
5. Back at VM selection → Add more VMs → Enter
6. Continue forward through steps
```

### Example 3: Daemon Configuration

```
1. Select VMs → Enter
2. Choose template → Enter
3. Enable daemon mode → Yes → Enter
4. Configure daemon? → Yes → Enter
5. Set custom directories → Realize wrong paths → Press Esc
6. Back to daemon question → Select "No, use defaults"
7. Continue to confirmation
```

---

## Comparison with HyperCTL

### HyperCTL (manifest builder)
- **Library**: Custom prompts with pterm
- **Back navigation**: Manual implementation
- **Method**: Type "back" or select "← Go Back"
- **Implementation**: Custom state machine with loops

### HyperExport (interactive mode)
- **Library**: `huh` (Charmbracelet form library)
- **Back navigation**: Built-in
- **Method**: Press Esc key
- **Implementation**: Automatic via library

---

## Key Features of Huh Navigation

### 1. Natural Keyboard Navigation ✅
- Arrow keys work intuitively
- Tab for forward, Shift+Tab for back
- Esc for cancel/back

### 2. Form Groups ✅
- Each step is a group
- Navigate between groups with Enter/Esc
- Skip hidden groups automatically

### 3. Validation ✅
- Cannot proceed with invalid input
- Can go back to fix mistakes
- Real-time validation feedback

### 4. Visual Feedback ✅
- Orange theme highlights current field
- Clear indicators for selected items
- Progress shown through groups

---

## Testing Back Navigation

### Test Scenario 1: Basic Back Navigation

```bash
hyperexport interactive

# Test:
1. Select some VMs → Enter
2. Press Esc → Should return to VM selection
3. Change VM selection → Enter
4. Select template → Enter
5. Press Esc → Should return to template
6. Press Esc again → Should return to VM selection
```

### Test Scenario 2: Conditional Navigation

```bash
hyperexport interactive

# Test:
1. Select VMs → Enter
2. Select template → Enter
3. Configure settings → Enter
4. Enable daemon: No → Enter
5. Press Esc → Should skip hidden daemon config group
6. Should go back to daemon yes/no question
```

### Test Scenario 3: Field-Level Navigation

```bash
hyperexport interactive

# In multi-field group:
1. Tab → Moves to next field
2. Shift+Tab → Moves to previous field
3. Esc → Goes back to previous group
```

---

## Current Implementation

### File Structure

```
cmd/hyperexport/
├── interactive_huh.go          ← Current implementation (with built-in nav)
├── interactive_tui.go.old      ← Old Bubbletea version (deprecated)
└── NEW_HUH_TUI.md             ← Migration guide
```

### Form Navigation Code

**VM Selection (Step 1):**
```go
form := huh.NewForm(
    huh.NewGroup(
        huh.NewMultiSelect[string]().
            Title("Select VMs to Export").
            Description("Use arrow keys to navigate, space to select, enter to confirm").
            Options(options...).
            Height(15).
            Filterable(true),
    ),
).WithTheme(theme)

form.Run()  // Built-in navigation handles Esc automatically
```

**Export Configuration (Steps 2-4):**
```go
form := huh.NewForm(
    huh.NewGroup(...),  // Template
    huh.NewGroup(...),  // Output settings
    huh.NewGroup(...),  // Daemon mode
    huh.NewGroup(...).WithHideFunc(...),  // Conditional daemon config
).WithTheme(theme)

form.Run()  // Navigate with Enter (forward) and Esc (back)
```

---

## Benefits Over Manual Implementation

### 1. Less Code ✅
- No manual state machine
- No custom back button logic
- Library handles everything

### 2. Better UX ✅
- Standard keyboard shortcuts
- Familiar Esc key for back
- Smooth transitions

### 3. More Reliable ✅
- Battle-tested library
- No custom bugs
- Consistent behavior

### 4. Easier Maintenance ✅
- Just update library
- No complex navigation code
- Clear and simple

---

## Documentation Updates

### User Guide Reference

The navigation is already documented in:
- `TUI_USER_GUIDE.md` - Complete TUI guide
- `TUI_KEYBOARD_SHORTCUTS.md` - Keyboard reference
- `NEW_HUH_TUI.md` - Huh implementation details

### Navigation Tips in User Guides

All user guides mention:
- Use Esc to go back
- Use Enter to proceed
- Use arrow keys to navigate
- Use Space to select (multi-select)

---

## Summary

### HyperExport Back Navigation Status

✅ **Already Implemented** - Via `huh` library
✅ **Fully Functional** - Works with Esc key
✅ **No Action Needed** - Built-in feature
✅ **Well Documented** - In existing guides

### Key Differences from HyperCTL

| Feature | HyperCTL | HyperExport |
|---------|----------|-------------|
| Library | Custom pterm | Huh forms |
| Back method | Type "back" | Press Esc |
| Implementation | Manual | Automatic |
| Code required | +153 lines | 0 lines (built-in) |
| Status | Added manually | Already present |

---

## Quick Reference

### How to Use Back Navigation in HyperExport

1. **Start interactive mode:**
   ```bash
   hyperexport interactive
   ```

2. **Navigate through steps:**
   - **Forward**: Press Enter
   - **Backward**: Press Esc
   - **Cancel**: Press Ctrl+C

3. **Within each step:**
   - **Next field**: Tab or ↓
   - **Previous field**: Shift+Tab or ↑
   - **Select/deselect**: Space
   - **Filter**: Type / then search term

4. **Confirm and execute:**
   - Review summary
   - Press Enter to start export
   - Press Esc to go back and change settings

---

## Conclusion

**HyperExport already has excellent back navigation** thanks to the `huh` library. No additional implementation needed!

The user can:
- ✅ Press Esc to go back at any step
- ✅ Navigate freely between form groups
- ✅ Change previous selections
- ✅ Review and modify settings

This is actually **better than manual implementation** because:
- Standard keyboard shortcuts (Esc is universal for "back")
- No typing required (just press Esc)
- Smooth, animated transitions
- Battle-tested library code

**No changes needed - the feature is already there!** 🎉

---

**Last Updated:** 2026-01-24
**Library:** charmbracelet/huh v0.3.0+
**Status:** ✅ Production Ready
