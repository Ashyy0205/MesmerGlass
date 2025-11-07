# How to Enable SUBTEXT (Scrolling Carousel Bands) in MesmerGlass

## Quick Start (3 Steps)

1. **Launch MesmerGlass**
   ```powershell
   .\.venv\Scripts\python.exe run.py
   ```

2. **Navigate to Text Tab**
   - Click the "Text" tab in the main window

3. **Enable and Configure SUBTEXT Mode**
   - ✅ **Check** "Enable Independent Text Rendering"
   - Select **"Subtext (Scrolling Bands)"** from the dropdown
   - Click **"Apply to All"** button
   - Optionally: Set "Duration per Text" to 30-60 seconds

4. **Start Spiral/Visual**
   - Go to "Spiral" tab
   - Enable spiral
   - Launch on a display

---

## What You Should See

### SUBTEXT Mode (Correct - Carousel Effect)
```
┌─────────────────────────────────────────┐
│ Obey Submit Focus Watch... → (scrolling)│
│                                         │
│ Obey Submit Focus Watch... →            │
│                                         │
│ Obey Submit Focus Watch... →  (CENTER)  │
│                                         │
│ Obey Submit Focus Watch... →            │
│                                         │
│ Obey Submit Focus Watch... →            │
└─────────────────────────────────────────┘
```
**Characteristics:**
- ~17 horizontal bands
- Text scrolls left-to-right continuously
- Semi-transparent (ghostly effect)
- Fills screen vertically
- Text repeats across each band width

### FILL_SCREEN Mode (Old - Static Grid)
```
┌─────────────────────────────────────────┐
│ Obey Obey Obey Obey Obey Obey Obey Obey│
│ Obey Obey Obey Obey Obey Obey Obey Obey│
│ Obey Obey Obey Obey Obey Obey Obey Obey│
│ Obey Obey Obey Obey Obey Obey Obey Obey│
│ Obey Obey Obey Obey Obey Obey Obey Obey│
│ Obey Obey Obey Obey Obey Obey Obey Obey│
└─────────────────────────────────────────┘
```
**Characteristics:**
- 8×6 grid (48 instances)
- Static wallpaper
- No scrolling
- For images, not text

---

## Troubleshooting

### "I don't see any text"
**Problem:** Text rendering not enabled

**Solution:**
1. Go to Text Tab
2. **Check** "Enable Independent Text Rendering" checkbox
3. Verify texts are enabled (checkboxes in text list)

---

### "I see a static grid instead of scrolling"
**Problem:** Wrong mode selected (FILL_SCREEN instead of SUBTEXT)

**Solution:**
1. In Text Tab, change dropdown from "Fill Screen" to "Subtext (Scrolling Bands)"
2. Click "Apply to All"
3. Restart visual if needed

---

### "Text scrolling is too fast/slow"
**Problem:** Scroll speed needs adjustment

**Solution (temporary):**
```python
# In Python console or edit text_director.py
director._scroll_speed = 0.001  # Slower
director._scroll_speed = 0.005  # Faster
```

**Future:** UI control will be added

---

### "No text library loaded"
**Problem:** Text library empty

**Solution:**
1. Text Tab automatically loads 20 default texts
2. If empty, use "Enable All" button
3. Check that at least one text has weight > 0%

---

## Advanced: Test Without GUI

Run the demo script to verify SUBTEXT works:

```powershell
.\.venv\Scripts\python.exe test_subtext_demo.py
```

Expected output:
```
✓ PASS: Bands rendered
✓ PASS: Scrolling enabled
✓ PASS: SUBTEXT mode active
✓ PASS: Text concatenated
✓ PASS: Multiple bands

✓ ALL CHECKS PASSED!
```

---

## Comparison: What Changed

### Before (User Confusion)
- Selected "Fill Screen" expecting scrolling carousel
- Got static 8×6 grid wallpaper
- No animation

### After (Correct Behavior)
- Select "Subtext (Scrolling Bands)" 
- Get ~17 horizontal scrolling bands
- Continuous left-to-right animation
- Carousel/marquee effect

---

## Next Steps After Enabling

1. **Adjust timing**: Set "Duration per Text" to control how long each text shows
2. **Customize texts**: Add/remove texts in the library list
3. **Adjust weights**: Use sliders to control which texts appear more often
4. **Try other modes**: Experiment with "Split Word" (scattered), "None" (centered), etc.

---

## Summary

The SUBTEXT mode is **fully implemented and working**. The key is to:

1. ✅ **Enable** "Independent Text Rendering" checkbox
2. ✅ **Select** "Subtext (Scrolling Bands)" mode
3. ✅ **Click** "Apply to All"

Then you'll see the proper scrolling carousel bands effect!
