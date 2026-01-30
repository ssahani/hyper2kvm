# HyperExport Back Button Navigation Feature

**Feature:** Loop-based step navigation with visible back button on all screens
**Date:** 2026-01-24
**Status:** ✅ Implemented and Enhanced

---

## Overview

HyperExport interactive mode now includes explicit back button navigation on ALL screens, allowing users to navigate back and forth through the 3 main configuration steps and all sub-screens within Step 2.

---

## Navigation Flow

```
Step 1/3: VM Selection
   ↓ (select VMs and confirm)
Step 2/3: Export Configuration
   - Screen 2.1: Template Selection → "← Go Back" option
   - Screen 2.2: Output Directory → Press Esc to go back
   - Screen 2.3: Daemon Mode → "← Go Back" option
   - Screen 2.4: Configure Daemon → "← Go Back" option
   - Screen 2.5: Daemon Inputs → Press Esc to go back
   ↓ (configure export) / ↑ (select "← Go Back" or press Esc)
Step 3/3: Confirmation → "← Go Back" option
   ↓ (export)
```

**Use "← Go Back" option in select menus or press Esc in input fields!**

---

## Back Button Availability

### Step 1: VM Selection
- **No back button** on first visit (first step, nothing to go back to)
- **"← Go Back" available** if you navigate back from Step 2

### Step 2: Export Configuration

**Screens with "← Go Back" select option:**
1. **Template Selection** - Choose export template
   - Options: Quick Export, Production Backup, Development, Archive, **← Go Back**
   
2. **Daemon Mode** - Use systemd daemon?
   - Options: Yes use daemon, No direct execution, **← Go Back**
   
3. **Configure Daemon** - Customize daemon settings?
   - Options: Yes customize, No use defaults, **← Go Back**
   - Only shown if you selected "Yes, use daemon"

**Screens with Esc navigation:**
4. **Output Directory & Parallel Downloads** - Input fields
   - Description shows: "(press Esc to go back)"
   - Press Esc to return to previous screen
   
5. **Daemon Configuration Inputs** - Input fields (if customizing daemon)
   - Fields: Instance, Watch Dir, Output Dir, Poll Interval, Timeout
   - Each description shows: "(press Esc to go back)"
   - Only shown if you selected "Yes, customize"

### Step 3: Confirmation
- **"← Go Back" option** in confirmation menu
- Options: "Yes, export!", "Cancel", **← Go Back**

---

## Implementation Details

### Select-Based Back Navigation

Changed all `Confirm` widgets to `Select` widgets to support "← Go Back" option:

```go
// Daemon mode with back button
daemonOptions := []huh.Option[string]{
    huh.NewOption("Yes, use daemon", "yes"),
    huh.NewOption("No, direct execution", "no"),
}
if allowBack {
    daemonOptions = append(daemonOptions, huh.NewOption("← Go Back", backSentinel))
}

huh.NewSelect[string]().
    Title("hyper2kvm Daemon Mode").
    Description("Use systemd daemon for VM conversion?").
    Options(daemonOptions...).
    Value(&useDaemonStr)
```

### Input Field Esc Hints

All input fields show "(press Esc to go back)" in their descriptions:

```go
huh.NewInput().
    Title("Output Directory").
    Description("Where to save exported VMs (press Esc to go back)").
    Value(&config.outputDir).
    Placeholder(defaultOutputDir)
```

### Back Detection

After form completes, check all select fields for back sentinel:

```go
// Check if back button was selected in any field
if allowBack && (templateName == backSentinel || 
                 useDaemonStr == backSentinel || 
                 configureDaemonStr == backSentinel) {
    return nil, nil // Signal back navigation
}
```

---

## User Experience Examples

### Example 1: Going Back from Daemon Mode
```
1. Step 1: Select VMs → Enter
2. Step 2.1: Select template → Enter  
3. Step 2.2: Enter output dir → Enter
4. Step 2.3: Daemon mode screen → Select "← Go Back"
5. Returns to Step 1 (VM Selection)
```

### Example 2: Going Back from Input Fields
```
1. Step 1: Select VMs → Enter
2. Step 2.1: Select template → Enter
3. Step 2.2: Output dir screen → Press Esc
4. Returns to Step 2.1 (Template selection)
5. Can select "← Go Back" → Returns to Step 1
```

### Example 3: Going Back from Daemon Config
```
1. Complete Steps 1, 2.1, 2.2, 2.3 (select "Yes, use daemon")
2. Step 2.4: Configure daemon → Select "← Go Back"
3. Returns to Step 1 (VM Selection)
4. Can change VMs and continue forward
```

---

## Code Changes

**File Modified:** `/home/ssahani/go/github/hypersdk/cmd/hyperexport/interactive_huh.go`

**Commit 1 (659622e):** Initial back button implementation
- Loop-based navigation with step counter
- Back button in template selection
- Back button in confirmation

**Commit 2 (8d70924):** Back button on all screens
- Changed Confirm to Select for daemon mode
- Changed Confirm to Select for configure daemon  
- Added Esc hints to all input fields
- Removed advanced options (simplified flow)
- Check all select fields for backSentinel

**Changes Summary:**
- Initial: +133, -37 lines
- Enhancement: +48, -72 lines
- Net result: Cleaner code with better navigation

---

## Key Differences from HyperCTL

| Feature | HyperCTL (manifest) | HyperExport (interactive) |
|---------|---------------------|---------------------------|
| **Library** | pterm | huh (charmbracelet) |
| **Back in Select** | "← Go Back" option | "← Go Back" option |
| **Back in Input** | Type "back" | Press Esc |
| **Implementation** | Manual prompts | Form-based with groups |
| **Step Count** | 4 steps | 3 steps (with sub-screens) |

---

## Benefits

### 1. Better User Experience ✅
- No need to restart on mistakes
- Can go back from ANY screen
- Clear Esc hints on input fields

### 2. Flexible Navigation ✅
- Select screens: "← Go Back" option
- Input screens: Press Esc
- Works on all screens in Step 2

### 3. Consistent UI ✅
- "← Go Back" in all select menus
- Esc hints in all input descriptions
- Orange theme maintained

### 4. Error Prevention ✅
- Easy to correct mistakes
- No loss of previous selections
- Can review before executing

---

## Testing

### Manual Test Checklist

- [x] Build compiles successfully
- [x] Step 1: Back button only if navigated back from Step 2
- [x] Step 2.1: Template - "← Go Back" available
- [x] Step 2.2: Output dir - Esc hint shown, Esc works
- [x] Step 2.3: Daemon mode - "← Go Back" available
- [x] Step 2.4: Configure daemon - "← Go Back" available  
- [x] Step 2.5: Daemon inputs - Esc hints shown, Esc works
- [x] Step 3: Confirmation - "← Go Back" available
- [x] Can navigate back from any screen
- [x] Step counter shows correctly (1/3, 2/3, 3/3)
- [x] Orange theme preserved

### Test Commands

```bash
# Build hyperexport
cd /home/ssahani/go/github/hypersdk/cmd/hyperexport
go build -o hyperexport .

# Run interactive mode
./hyperexport interactive

# Test navigation:
1. Select VMs → Enter (go to Step 2)
2. Template → Enter
3. Output dir → Enter (or press Esc to go back)
4. Daemon mode → Select "← Go Back" (returns to Step 1)
5. Select VMs → Enter
6. Template → Enter
7. Output dir → Enter
8. Daemon mode → Select "Yes, use daemon" → Enter
9. Configure daemon → Select "← Go Back" (returns to Step 1)
```

---

## Summary

### Implementation Complete ✅

- ✅ Loop-based navigation with step counter  
- ✅ "← Go Back" in ALL select menus (template, daemon mode, configure daemon)
- ✅ Esc navigation in ALL input fields (with hints)
- ✅ Step indicators (Step 1/3, 2/3, 3/3)
- ✅ Back available on all screens in Steps 2-3
- ✅ Build successful
- ✅ Orange theme preserved

### Navigation Methods

**Step 1 (VM Selection):**
- Select VMs → Enter (forward)
- "← Go Back" (only if navigated back from Step 2)

**Step 2 (Export Configuration):**
All screens support back navigation:
- **Select menus** → "← Go Back" option
- **Input fields** → Press Esc (hint shown in description)

**Step 3 (Confirmation):**
- "Yes, export!" → Execute
- "Cancel" → Exit  
- "← Go Back" → Return to Step 2

---

**Status:** ✅ Production Ready
**Build:** Successful
**Testing:** Manual testing complete
**Enhancement:** All screens now have back navigation

---

**Last Updated:** 2026-01-24
**Library:** charmbracelet/huh + pterm
**Implementation:** Loop-based with explicit back buttons on all screens
**Commits:** 659622e (initial), 8d70924 (all screens)
