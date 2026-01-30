# Back Button Navigation in Manifest Builder TUI

**Feature:** Step-based navigation with back button support
**Commit:** `62bc4d4`
**Date:** 2026-01-24
**Status:** ✅ Implemented and Tested

---

## Overview

The manifest builder TUI now includes comprehensive back button navigation, allowing users to navigate back and forth through configuration steps without starting over.

---

## Features Added

### 1. Step Navigation System ✅

**Step Indicators:**
```
Step 1/4: Source Configuration
Step 2/4: Pipeline Configuration
Step 3/4: Output Configuration
Step 4/4: Review Manifest
```

Each step shows the current position and total number of steps.

### 2. Back Button Options ✅

#### In Select Menus
```
Select source type:
  1. vmdk
  2. ova
  3. ovf
  4. vhd
  5. vhdx
  6. raw
  7. ami
  8. ← Go Back          <-- Back button option

Enter choice (1-8):
```

#### In Text Input
```
Enter source path [/path/to/disk.vmdk] (type 'back' to go back):
```

#### In Yes/No Prompts
```
Enable INSPECT stage (detect OS)? [Y/n] (type 'back' to go back):
```

### 3. Navigation Flow ✅

**Forward Navigation:**
- Complete current step → Automatically advance to next step

**Backward Navigation:**
- Select "← Go Back" in menus
- Type "back" in text inputs
- Type "back" in yes/no prompts
- Returns to previous step with choices preserved

**First Step Handling:**
- Back button disabled on Step 1 (no previous step)
- Only forward navigation available

---

## User Experience

### Example Navigation Flow

```
📝 Manifest Builder

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Step 1/4: Source Configuration
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Select source type:
  1. vmdk
  2. ova
  3. ovf
  4. vhd
  5. vhdx
  6. raw
  7. ami

Enter choice (1-7): 1

Enter source path [/path/to/disk.vmdk]: /vms/photon.vmdk

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Step 2/4: Pipeline Configuration
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Enable INSPECT stage (detect OS)? [Y/n] (type 'back' to go back): back

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Step 1/4: Source Configuration     <-- Back to Step 1
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Select source type:
  1. vmdk
  2. ova      <-- Can change choice
  3. ovf
  4. vhd
  5. vhdx
  6. raw
  7. ami

Enter choice (1-7): 2

Enter source path [/path/to/disk.ova]: /vms/backup.ova

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Step 2/4: Pipeline Configuration   <-- Continue forward
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### Final Review Step

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Step 4/4: Review Manifest
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

┌─ Generated Manifest ─────────────────────────┐
│ {                                            │
│   "version": "1.0",                          │
│   "pipeline": {                              │
│     "load": {                                │
│       "source_type": "ova",                  │
│       "source_path": "/vms/backup.ova"       │
│     },                                       │
│     ...                                      │
│   }                                          │
│ }                                            │
└──────────────────────────────────────────────┘

What would you like to do?
  1. Save manifest to file
  2. Cancel (exit without saving)
  3. ← Go Back                <-- Can go back to edit

Enter choice (1-3):
```

---

## Technical Implementation

### New Helper Functions

#### 1. `promptSelectWithBack()`
```go
func promptSelectWithBack(prompt string, options []string, allowBack bool) string
```
- Displays numbered menu with options
- Adds "← Go Back" option if `allowBack` is true
- Returns `"<back>"` if back is selected
- Returns selected option otherwise

#### 2. `promptInputWithBack()`
```go
func promptInputWithBack(prompt, defaultValue string, allowBack bool) string
```
- Text input with default value
- Shows "(type 'back' to go back)" hint if allowed
- Returns `"<back>"` if user types "back"
- Returns entered value otherwise

#### 3. `promptConfirmWithBack()`
```go
func promptConfirmWithBack(prompt string, defaultValue bool, allowBack bool) string
```
- Yes/No confirmation
- Shows "(type 'back' to go back)" hint if allowed
- Returns `"<back>"` if user types "back"
- Returns `"yes"` or `"no"` otherwise

### Navigation Logic

```go
currentStep := 1
totalSteps := 4

for {
    switch currentStep {
    case 1:
        // Step 1: No back button (first step)
        result := promptSelectWithBack("Select:", options, false)
        if result == "<back>" {
            currentStep--  // Never happens on step 1
            continue
        }
        currentStep++  // Advance to step 2

    case 2:
        // Step 2: Back button enabled
        result := promptInputWithBack("Enter:", "", true)
        if result == "<back>" {
            currentStep--  // Go back to step 1
            continue
        }
        currentStep++  // Advance to step 3

    case 3:
        // Step 3: Back button enabled
        result := promptConfirmWithBack("Enable?", true, true)
        if result == "<back>" {
            currentStep--  // Go back to step 2
            continue
        }
        currentStep++  // Advance to step 4

    case 4:
        // Step 4: Review with back button
        action := promptSelectWithBack("Action?", actions, true)
        if action == "<back>" {
            currentStep--  // Go back to step 3
            continue
        }
        return  // Done
    }
}
```

---

## Usage Examples

### Basic Navigation

```bash
# Start the manifest builder
hyperctl manifest create

# Navigation options:
# - Enter numbers to select from menus
# - Type 'back' in text inputs to go back
# - Select "← Go Back" in menus to return to previous step
# - Step 1: Back is disabled (first step)
# - Steps 2-4: Back is always available
```

### Common Workflows

#### Workflow 1: Correcting a Mistake
```
1. Step 1: Select VMDK → Enter wrong path
2. Step 2: Realize mistake → Type 'back'
3. Step 1: Enter correct path
4. Continue normally
```

#### Workflow 2: Changing Source Type
```
1. Step 1: Select VMDK
2. Step 2: Configure pipeline
3. Step 3: Realize need OVA instead → Select "← Go Back"
4. Step 2: Back again
5. Step 1: Change to OVA
6. Re-configure steps 2-3
```

#### Workflow 3: Reviewing Before Save
```
1. Complete all steps 1-3
2. Step 4: Review manifest
3. Notice configuration issue → Select "← Go Back"
4. Fix issue in previous steps
5. Return to Step 4 and save
```

---

## Benefits

### 1. User-Friendly Navigation ✅
- Can correct mistakes without starting over
- Natural back-and-forth workflow
- Clear step indicators

### 2. Flexibility ✅
- Change decisions at any point
- Review and modify previous choices
- No forced linear progression

### 3. Error Prevention ✅
- Review before finalizing
- Correct mistakes easily
- No need to exit and restart

### 4. Intuitive Controls ✅
- Simple "back" command
- Visual "← Go Back" option
- Consistent across all prompt types

---

## Code Changes Summary

**File Modified:** `cmd/hyperctl/manifest.go`
**Lines Changed:** +215, -62
**Net Change:** +153 lines

### Changes Breakdown

1. **Refactored `handleManifestCreate()`**
   - Changed from sequential flow to loop-based navigation
   - Added step counter (currentStep, totalSteps)
   - Implemented switch-case for each step
   - Added back navigation logic

2. **Added New Helper Functions**
   - `promptSelectWithBack()` - 28 lines
   - `promptInputWithBack()` - 19 lines
   - `promptConfirmWithBack()` - 32 lines

3. **Enhanced User Interface**
   - Step indicators (Step X/Y)
   - Back button hints in prompts
   - Consistent navigation across all steps

---

## Testing

### Manual Testing Checklist

- [x] Build compiles successfully
- [x] Step 1: Back button disabled
- [x] Step 2: Back button works (returns to Step 1)
- [x] Step 3: Back button works (returns to Step 2)
- [x] Step 4: Back button works (returns to Step 3)
- [x] Text input: "back" command works
- [x] Yes/No: "back" command works
- [x] Menu: "← Go Back" selection works
- [x] Step indicators show correctly
- [x] Can navigate forward and backward multiple times
- [x] Can change previous selections
- [x] Can complete full flow without using back
- [x] Can cancel at final step

### Test Command

```bash
# Test the manifest builder
/home/ssahani/go/github/hypersdk/cmd/hyperctl/hyperctl manifest create

# Try these scenarios:
1. Go through all steps normally (no back)
2. Use back at each step
3. Make multiple changes by going back
4. Test cancel option in final step
```

---

## Commit Information

**Repository:** github.com:ssahani/hypersdk.git
**Commit:** `62bc4d4`
**Branch:** main
**Date:** 2026-01-24

**Commit Message:**
```
feat: Add back button navigation to manifest builder TUI

Add step-based navigation with back button support in the interactive
manifest builder, allowing users to navigate back and forth through
the configuration steps.
```

---

## Future Enhancements

### Potential Improvements

1. **Save Draft Feature**
   - Save incomplete manifest
   - Resume from saved state

2. **Navigation Shortcuts**
   - Jump to specific step (e.g., "goto 3")
   - Skip optional steps

3. **Visual Navigation Map**
   - Show all steps with completion status
   - Highlight current step

4. **Undo/Redo**
   - Undo last change
   - Redo undone change

5. **Validation Preview**
   - Show what will be validated
   - Preview before finalizing

---

## Comparison: Before vs After

### Before (Linear Flow)
```
Step 1 → Step 2 → Step 3 → Step 4
  ↓        ↓        ↓        ↓
 Done    Done     Done     Done
                           (Can't go back!)
```

**Problem:** If you made a mistake in Step 1, you had to:
1. Exit the builder
2. Start over from beginning
3. Re-enter all information

### After (Navigable Flow)
```
Step 1 ←→ Step 2 ←→ Step 3 ←→ Step 4
  ↓        ↓          ↓         ↓
Edit → Back   Edit → Back   Edit → Done
```

**Solution:** Can go back and correct at any time:
1. Realize mistake
2. Type 'back' or select "← Go Back"
3. Fix the mistake
4. Continue forward

---

## User Feedback

Expected improvements in user experience:
- ✅ Reduced frustration from mistakes
- ✅ Faster manifest creation
- ✅ Better confidence in choices
- ✅ More exploration of options

---

**Status:** ✅ Feature Complete and Deployed
**Documentation:** Complete
**Testing:** Passed
**Availability:** Available in latest hyperctl build
