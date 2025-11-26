# Media Pool Size Recommendations

## Overview
MesmerGlass aggressively preloads images into RAM to eliminate loading delays during fast cycling. The number of images you can use depends on your available RAM and average image size.

## Memory Usage Guidelines

### Image Size vs Memory
- **1920x1080 (2MP)**: ~8 MB in RAM (RGBA format)
- **2560x1440 (3.7MP)**: ~14 MB in RAM
- **3840x2160 (4K, 8.3MP)**: ~32 MB in RAM
- **3968x4000 (16MP)**: ~64 MB in RAM

### Recommended Media Pool Sizes

| System RAM | Recommended Pool Size | Max Image Size | Notes |
|------------|----------------------|----------------|-------|
| 8 GB       | 100-150 images       | 1920x1080 (2MP) | Conservative for systems with limited RAM |
| 16 GB      | 200-300 images       | 2560x1440 (3.7MP) | Good balance for most users |
| 32 GB      | 400-500 images       | 2560x1440 (3.7MP) | Large pools with good variety |
| 64 GB+     | 800-1000 images      | 3840x2160 (8.3MP) | Maximum variety, can handle 4K |

## Performance Impact

### Image Loading Time by Size
- **1920x1080 (2MP)**: 2-5ms load time ✅ Optimal
- **2560x1440 (3.7MP)**: 5-10ms load time ✅ Good
- **3840x2160 (8.3MP)**: 15-30ms load time ⚠️ Acceptable
- **3968x4000 (16MP)**: 80-150ms load time ❌ Too slow for fast cycling

### Cycle Speed Impact
At cycle speed 100 (3 frames per cycle @ 60fps):
- **Each cycle = 50ms total**
- **Load time budget: <10ms** to avoid frame drops
- **Images >5MP will cause stuttering**

## Optimization Strategies

### 1. Downscale Large Images
Use batch image processing to resize images before adding to media pool:

```powershell
# Example using ImageMagick
magick mogrify -resize "1920x1080>" -quality 90 *.jpg
```

### 2. Filter by Size
Remove or relocate images larger than 5MP:

```python
# Example script to identify large images
from pathlib import Path
from PIL import Image

for img_path in Path("MEDIA/Images").glob("*.jpg"):
    img = Image.open(img_path)
    megapixels = (img.width * img.height) / 1_000_000
    if megapixels > 5.0:
        print(f"{img_path.name}: {img.width}x{img.height} ({megapixels:.1f}MP)")
```

### 3. Use Separate Pools
Create different media pools for different scenarios:
- **Fast cycling pool**: 200-300 images, all <2MP, optimized for speed
- **Slow cycling pool**: 500+ images, can include larger sizes
- **VR pool**: Higher resolution images for immersive mode

## Cache Settings

MesmerGlass automatically configures cache based on theme size:

| Theme Size | Cache Size | Behavior |
|------------|-----------|----------|
| ≤100 images | All images | Entire theme preloaded |
| 101-300 images | 200 images | Most images preloaded |
| 301-500 images | 300 images | Large portion preloaded |
| 500+ images | 500 images | Substantial portion preloaded |

## Preloading Behavior

- **On Startup**: Theme images are preloaded in background
- **During Playback**: Synchronous loading for any cache misses
- **Memory Management**: LRU eviction for cache management

## Troubleshooting

### Problem: Stuttering/Frame Drops
**Cause**: Images too large or too many images for available RAM

**Solutions**:
1. Check image sizes with visual cycle test
2. Downscale images >2MP
3. Reduce media pool size
4. Add more RAM

### Problem: Images Repeating Too Often
**Cause**: `LAST_IMAGE_COUNT` too low or pool size too small

**Solutions**:
1. Increase media pool size (more unique images)
2. Current `LAST_IMAGE_COUNT = 100` (tracks last 100 images)
3. With 500 images, expect ~76% unique rate

### Problem: High Memory Usage
**Cause**: Too many images preloaded or images too large

**Solutions**:
1. Reduce media pool size
2. Downscale images to 1920x1080
3. Adjust `_preload_aggressively` setting in code

## Testing Your Setup

Use the visual cycle test to validate your media pool:

```powershell
.\.venv\Scripts\python.exe scripts\visual_cycle_test.py --media-path "path\to\images" --speed 100 --duration 20
```

**Good Results**:
- Unique rate: >70%
- Average load time: <10ms
- Max load time: <30ms
- On-time frames: >95%

**Poor Results** (needs optimization):
- Average load time: >15ms
- Max load time: >50ms
- On-time frames: <90%

## Recommendations Summary

1. **Target 1920x1080 (2MP) images** for optimal performance
2. **Pool size: 200-300 images** for 16GB RAM systems
3. **Avoid images >5MP** - they cause stuttering
4. **Test with visual_cycle_test.py** before production use
5. **Monitor memory usage** during extended sessions
