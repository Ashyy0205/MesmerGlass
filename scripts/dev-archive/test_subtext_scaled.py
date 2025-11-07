"""
Test SUBTEXT spacing with SCALED widths (text_scale = 1.5).

Moved to scripts/dev-archive as a developer-only utility.
"""

from mesmerglass.content.text_renderer import TextRenderer

renderer = TextRenderer()

messages = [
    "Yes",  # Very short
    "Relax",  # Short
    "AND DEEPER",  # Medium (from screenshot)
    "Breathe deeply now",  # Long
]

print("=" * 80)
print("SUBTEXT DYNAMIC SPACING TEST (with text_scale = 1.5)")
print("=" * 80)
print("\nFormula: spacing = base_width / (rendered_width * text_scale)")
print("  - base_width = 450px (reference for scaled dimensions)")
print("  - Clamped to range [1.02, 1.50] (2% to 50% gap)")
print("\n" + "-" * 80)

text_scale = 1.5

for msg in messages:
    rendered = renderer.render_main_text(msg, large=True, shadow=False)
    
    if rendered:
        width = rendered.width
        scaled_width = width * text_scale
        
        # Calculate spacing using SCALED width
        base_width = 450.0
        min_spacing = 1.02
        max_spacing = 1.50
        spacing = base_width / max(scaled_width, 50)
        spacing = max(min_spacing, min(max_spacing, spacing))
        
        gap_pct = (spacing - 1.0) * 100
        spacing_bar = "█" * int(spacing * 20)
        
        print(f"\nMessage: \"{msg}\"")
        print(f"  Original width: {width:4d} px")
        print(f"  Scaled width:   {scaled_width:4.0f} px (×{text_scale})")
        print(f"  Spacing:        {spacing:.3f}x ({gap_pct:5.1f}% gap)")
        print(f"  Visual:         {spacing_bar}")

print("\n" + "=" * 80)
print("EXPECTED RESULTS:")
print("  - 'Yes' (short) → Wide spacing (40-50% gap)")
print("  - 'AND DEEPER' (medium) → Balanced spacing (10-15% gap)")
print("  - Long messages → Tight spacing (2-5% gap)")
print("=" * 80)
