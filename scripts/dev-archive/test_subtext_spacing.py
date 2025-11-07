"""
Test script to verify SUBTEXT dynamic spacing.

This script demonstrates that spacing adapts based on message length.

Moved to scripts/dev-archive as a developer-only utility.
"""

from mesmerglass.content.text_renderer import TextRenderer

renderer = TextRenderer()

messages = [
    "Yes",
    "Relax",
    "Breathe deeply",
    "Welcome to MesmerGlass",
    "Experience deep hypnotic relaxation now",
]

print("=" * 80)
print("SUBTEXT DYNAMIC SPACING TEST")
print("=" * 80)
print("\nFormula: spacing = base_width / text_width")
print("  - Clamped to range [1.02, 1.50] (2% to 50% gap)")
print("  - base_width = 300px (reference for balanced spacing)")
print("\n" + "-" * 80)

for msg in messages:
    rendered = renderer.render_main_text(msg, large=True, shadow=False)
    if rendered:
        width = rendered.width
        base_width = 300.0
        min_spacing = 1.02
        max_spacing = 1.50
        spacing = base_width / max(width, 50)
        spacing = max(min_spacing, min(max_spacing, spacing))
        gap_pct = (spacing - 1.0) * 100
        spacing_bar = "█" * int(spacing * 20)
        print(f"\nMessage: \"{msg}\"")
        print(f"  Width:   {width:4d} px")
        print(f"  Spacing: {spacing:.3f}x ({gap_pct:5.1f}% gap)")
        print(f"  Visual:  {spacing_bar}")

print("\n" + "=" * 80)
print("EXPECTED BEHAVIOR:")
print("  - Short messages (\"Yes\") → Maximum spacing (50% gap)")
print("  - Medium messages (\"Breathe deeply\") → Balanced spacing (~15% gap)")
print("  - Long messages (\"Experience...\") → Minimum spacing (2% gap)")
print("=" * 80)
