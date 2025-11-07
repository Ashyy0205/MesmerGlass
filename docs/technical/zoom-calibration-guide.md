# Zoom Calibration Tool - User Guide

## Purpose
This tool helps you calibrate the zoom rate formula by visually matching background motion to the spiral's perceived inward pull.

## How It Works
The tool shows you a live spiral + background image. You adjust the zoom rate slider until the background motion *feels right* - like it's perfectly synced with the spiral pulling you inward.

## Step-by-Step Calibration Process

### 1. Test Different Scenarios
Try these common scenarios (at minimum):

**Scenario A: Slow Linear (baseline)**
- Spiral Type: 3 (Linear)
- Rotation Speed: 4.0x
- Adjust zoom rate until it looks good
- Click "Calculate Formula"

**Scenario B: Fast Linear**
- Spiral Type: 3 (Linear)
- Rotation Speed: 20.0x
- Adjust zoom rate until it looks good
- Click "Calculate Formula"

**Scenario C: Slow Sqrt (strong pull)**
- Spiral Type: 4 (Sqrt)
- Rotation Speed: 4.0x
- Adjust zoom rate until it looks good
- Click "Calculate Formula"

**Scenario D: Slow Power (gentle pull)**
- Spiral Type: 6 (Power)
- Rotation Speed: 4.0x
- Adjust zoom rate until it looks good
- Click "Calculate Formula"

**Scenario E: Fast Sqrt**
- Spiral Type: 4 (Sqrt)
- Rotation Speed: 20.0x
- Adjust zoom rate until it looks good
- Click "Calculate Formula"

### 2. Export Results
After collecting 5+ scenarios, click **"Export Calibration Data"**

This saves a file like: `zoom_calibration_20251029_173045.txt`

### 3. Send Me the File
The text file contains:
- Your manual zoom rates for each scenario
- Calculated multipliers
- Summary statistics
- Suggested new formula

I'll use this data to improve the zoom formula!

## Tips for Calibration

### What to Look For:
✅ Background should zoom **in sync** with spiral's rotation
✅ Motion should feel **smooth and continuous**
✅ No jarring speed mismatches
✅ Should create stronger "falling in" feeling

### Common Issues:
❌ **Too slow**: Background barely moves, spiral feels faster
❌ **Too fast**: Background zooms quickly, spiral feels slower
❌ **Timing off**: Zoom accelerates at different rate than spiral

### Best Practice:
- Let each scenario run for 10-15 seconds before adjusting
- Make small tweaks (0.01-0.02 at a time)
- Trust your gut feeling about what "looks right"
- The perfect rate is when you can't tell if it's the spiral or background pulling you in

## Output File Format

The exported file will look like:
```
============================================================
ZOOM CALIBRATION DATA
Generated: 2025-10-29 17:30:45
============================================================

CALIBRATION POINTS:
------------------------------------------------------------
#    Type   Speed    Manual Rate   Multiplier
------------------------------------------------------------
1    Linear   4.0x       0.180         0.900
2    Linear  20.0x       1.200         0.600
3    Sqrt     4.0x       0.280         0.500
4    Power    4.0x       0.080         1.212
5    Sqrt    20.0x       1.600         0.571

============================================================
SUMMARY
============================================================

Total Points: 5
Average Multiplier: 0.7566
Std Deviation: 0.2891
Range: 0.500 to 1.212

CURRENT FORMULA:
  zoom_rate = 0.5 * (rotation_speed / 10.0) * zoom_factor

SUGGESTED FORMULA:
  zoom_rate = 0.7566 * (rotation_speed / 10.0) * zoom_factor
```

## Why This Helps

The current formula uses a **fixed multiplier (0.5)** which might not be optimal.

Your calibration data will show:
- If the multiplier should be higher or lower
- If different spiral types need different factors
- If the relationship between speed and zoom is linear or not

This real-world data is much better than theoretical guesses!

## Controls Reference

**Spiral Type Slider (1-7):**
- 1 = Log (gentle, wide spacing)
- 2 = Quad (moderate)
- 3 = Linear (moderate) - **DEFAULT**
- 4 = Sqrt (strong, tight center)
- 5 = Inverse (moderate)
- 6 = Power (very gentle, extreme curves)
- 7 = Sawtooth (moderate)

**Rotation Speed Slider (4.0-40.0):**
- 4.0 = Slow/normal
- 10.0 = Moderate
- 20.0 = Fast
- 40.0 = Very fast

**Zoom Rate Slider (0.0-5.0):**
- Manual override of zoom rate
- Current formula expects ~0.2 for type 3 at speed 4.0
- Adjust until motion looks right

**Calculate Formula Button:**
- Records current settings as calibration point
- Shows implied multiplier for this scenario

**Reset Button:**
- Resets to default values
- Type 3, Speed 4.0, Rate 0.2

**Export Calibration Data:**
- Enabled after 1+ calibration points
- Saves all data to text file
- Includes summary and suggested formula
