"""
Image optimization tool for MesmerGlass media pools.

Identifies large images that cause performance issues and optionally
downscales them to optimal sizes for fast cycling.
"""
import sys
from pathlib import Path
from PIL import Image
import argparse

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def analyze_images(media_path: Path, max_mp: float = 5.0):
    """Analyze images in directory and report large ones."""
    
    # Find all image files
    image_files = []
    for ext in ['*.jpg', '*.jpeg', '*.png', '*.gif', '*.webp']:
        image_files.extend(media_path.glob(ext))
        image_files.extend(media_path.glob(ext.upper()))
    
    if not image_files:
        print(f"No images found in {media_path}")
        return
    
    print(f"\nAnalyzing {len(image_files)} images in: {media_path}")
    print(f"Flagging images larger than {max_mp:.1f} MP\n")
    print("=" * 80)
    
    large_images = []
    total_size_mb = 0
    
    for img_path in image_files:
        try:
            with Image.open(img_path) as img:
                width, height = img.size
                megapixels = (width * height) / 1_000_000
                
                # Estimate RAM usage (RGBA = 4 bytes per pixel)
                ram_mb = (width * height * 4) / (1024 * 1024)
                total_size_mb += ram_mb
                
                if megapixels > max_mp:
                    large_images.append({
                        'path': img_path,
                        'width': width,
                        'height': height,
                        'mp': megapixels,
                        'ram_mb': ram_mb
                    })
        except Exception as e:
            print(f"Error reading {img_path.name}: {e}")
    
    # Summary
    avg_mp = sum(img['mp'] for img in large_images) / len(large_images) if large_images else 0
    
    print(f"\nSUMMARY:")
    print(f"  Total images: {len(image_files)}")
    print(f"  Large images (>{max_mp:.1f}MP): {len(large_images)}")
    print(f"  Percentage: {len(large_images) / len(image_files) * 100:.1f}%")
    print(f"  Estimated total RAM: {total_size_mb:.1f} MB ({total_size_mb / 1024:.2f} GB)")
    print()
    
    if large_images:
        print(f"LARGE IMAGES (>{max_mp:.1f}MP):")
        print("-" * 80)
        
        # Sort by size
        large_images.sort(key=lambda x: x['mp'], reverse=True)
        
        for img in large_images[:20]:  # Show top 20
            print(f"  {img['path'].name}")
            print(f"    Size: {img['width']}x{img['height']} ({img['mp']:.1f}MP)")
            print(f"    RAM: {img['ram_mb']:.1f} MB")
            print()
        
        if len(large_images) > 20:
            print(f"  ... and {len(large_images) - 20} more")
    else:
        print("✓ No images larger than threshold found!")
    
    print("=" * 80)


def downscale_images(media_path: Path, output_path: Path, max_width: int = 1920, max_height: int = 1080, quality: int = 90):
    """Downscale large images to target resolution."""
    
    # Find all image files
    image_files = []
    for ext in ['*.jpg', '*.jpeg', '*.png']:
        image_files.extend(media_path.glob(ext))
        image_files.extend(media_path.glob(ext.upper()))
    
    if not image_files:
        print(f"No images found in {media_path}")
        return
    
    output_path.mkdir(exist_ok=True)
    
    print(f"\nDownscaling images to max {max_width}x{max_height}")
    print(f"Input: {media_path}")
    print(f"Output: {output_path}")
    print(f"Quality: {quality}")
    print("=" * 80)
    
    processed = 0
    downscaled = 0
    skipped = 0
    
    for img_path in image_files:
        try:
            with Image.open(img_path) as img:
                width, height = img.size
                
                # Check if needs downscaling
                if width <= max_width and height <= max_height:
                    skipped += 1
                    continue
                
                # Calculate new size maintaining aspect ratio
                ratio = min(max_width / width, max_height / height)
                new_width = int(width * ratio)
                new_height = int(height * ratio)
                
                # Resize
                img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                
                # Save
                output_file = output_path / img_path.name
                
                # Convert RGBA to RGB for JPEG
                if img_resized.mode == 'RGBA' and img_path.suffix.lower() in ['.jpg', '.jpeg']:
                    rgb_img = Image.new('RGB', img_resized.size, (255, 255, 255))
                    rgb_img.paste(img_resized, mask=img_resized.split()[3])
                    rgb_img.save(output_file, 'JPEG', quality=quality)
                else:
                    img_resized.save(output_file, quality=quality)
                
                downscaled += 1
                processed += 1
                
                if processed % 10 == 0:
                    print(f"  Processed: {processed}/{len(image_files)}")
                    
        except Exception as e:
            print(f"Error processing {img_path.name}: {e}")
    
    print("=" * 80)
    print(f"\nCOMPLETE:")
    print(f"  Total images: {len(image_files)}")
    print(f"  Downscaled: {downscaled}")
    print(f"  Skipped (already small): {skipped}")
    print(f"  Output directory: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Image optimization tool for MesmerGlass")
    parser.add_argument("media_path", type=Path, help="Path to media directory")
    parser.add_argument("--analyze", action="store_true", help="Analyze images and report large ones")
    parser.add_argument("--downscale", action="store_true", help="Downscale large images")
    parser.add_argument("--output", type=Path, help="Output directory for downscaled images")
    parser.add_argument("--max-mp", type=float, default=5.0, help="Max megapixels for analysis (default: 5.0)")
    parser.add_argument("--max-width", type=int, default=1920, help="Max width for downscaling (default: 1920)")
    parser.add_argument("--max-height", type=int, default=1080, help="Max height for downscaling (default: 1080)")
    parser.add_argument("--quality", type=int, default=90, help="JPEG quality for downscaling (default: 90)")
    
    args = parser.parse_args()
    
    if not args.media_path.exists():
        print(f"Error: Directory not found: {args.media_path}")
        sys.exit(1)
    
    if args.analyze or (not args.downscale):
        # Default to analyze if nothing specified
        analyze_images(args.media_path, max_mp=args.max_mp)
    
    if args.downscale:
        if not args.output:
            print("Error: --output required for downscaling")
            sys.exit(1)
        
        downscale_images(
            args.media_path,
            args.output,
            max_width=args.max_width,
            max_height=args.max_height,
            quality=args.quality
        )
