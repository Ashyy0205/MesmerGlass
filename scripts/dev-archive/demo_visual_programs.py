#!/usr/bin/env python3
"""
Interactive demo of all 7 visual program types.

Demonstrates the complete visual program system with real-time visualization
of cycler execution, image changes, text cycling, and spiral rotation.

Controls:
    1-7: Switch to specific visual program
    SPACE: Pause/Resume
    R: Reset current visual
    N: Next visual (auto-cycle)
    Q/ESC: Quit
    
Visual Programs:
    1. SimpleVisual - Basic slideshow (48 frames/image, 16 images)
    2. SubTextVisual - Images with text cycling (multi-layer)
    3. AccelerateVisual - Accelerating slideshow (56→12 frames)
    4. SlowFlashVisual - Slow/fast alternating (64→8 frames)
    5. FlashTextVisual - Rapid text flashing (6 frames/flash)
    6. ParallelImagesVisual - Multiple images simultaneously
    7. AnimationVisual - Video-focused (placeholder)
"""

import sys
import time
from pathlib import Path
from typing import Optional, List

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pygame
from mesmerglass.mesmerloom.visuals import (
    SimpleVisual, SubTextVisual, AccelerateVisual,
    SlowFlashVisual, FlashTextVisual, ParallelImagesVisual, AnimationVisual
)
from mesmerglass.engine.shuffler import Shuffler


# Color scheme
BG_COLOR = (20, 20, 30)
TEXT_COLOR = (220, 220, 255)
HIGHLIGHT_COLOR = (100, 255, 100)
DIM_COLOR = (120, 120, 150)
ACCENT_COLOR = (255, 180, 100)
PROGRESS_COLOR = (80, 180, 255)


class VisualDemoApp:
    """Interactive demo application for visual programs."""
    
    def __init__(self):
        pygame.init()
        
        # Window setup
        self.width = 1400
        self.height = 900
        self.screen = pygame.display.set_mode((self.width, self.height))
        pygame.display.set_caption("MesmerGlass Visual Programs Demo")
        
        # Fonts
        self.font_title = pygame.font.Font(None, 48)
        self.font_large = pygame.font.Font(None, 36)
        self.font_normal = pygame.font.Font(None, 28)
        self.font_small = pygame.font.Font(None, 22)
        
        # Demo data
        self.image_paths = [Path(f"image_{i}.jpg") for i in range(20)]
        self.text_lines = [
            "You are getting sleepy",
            "Deeper and deeper",
            "So relaxed",
            "Let go",
            "Sink down",
            "Peaceful",
            "Calm",
            "Drifting"
        ]
        self.video_paths = [Path(f"video_{i}.mp4") for i in range(10)]
        
        # State tracking
        self.current_image_index = 0
        self.current_text = ""
        self.current_subtext = ""
        self.current_slot_images = {}  # For ParallelImagesVisual
        self.spiral_rotation = 0.0
        self.image_changes = []  # History of image changes with timestamps
        self.text_changes = []   # History of text changes
        self.subtext_changes = []  # History of subtext changes
        self.spiral_updates = []  # Spiral rotation updates
        
        # Visual programs
        self.visuals = self._create_visuals()
        self.visual_names = [
            "SimpleVisual",
            "SubTextVisual", 
            "AccelerateVisual",
            "SlowFlashVisual",
            "FlashTextVisual",
            "ParallelImagesVisual",
            "AnimationVisual"
        ]
        self.current_visual_index = 0
        self.current_visual = self.visuals[self.current_visual_index]
        
        # Timing
        self.paused = False
        self.clock = pygame.time.Clock()
        self.fps = 60
        self.frame_count = 0
        self.start_time = time.time()
        
    def _create_visuals(self):
        """Create all visual program instances."""
        return [
            # 1. SimpleVisual
            SimpleVisual(
                image_paths=self.image_paths,
                on_change_image=self._on_change_image,
                on_rotate_spiral=self._on_rotate_spiral,
                on_preload_image=None
            ),
            
            # 2. SubTextVisual
            SubTextVisual(
                image_paths=self.image_paths,
                text_lines=self.text_lines,
                on_change_image=self._on_change_image,
                on_change_text=self._on_change_text,
                on_change_subtext=self._on_change_subtext,
                on_rotate_spiral=self._on_rotate_spiral
            ),
            
            # 3. AccelerateVisual
            AccelerateVisual(
                image_paths=self.image_paths,
                on_change_image=self._on_change_image,
                on_rotate_spiral=self._on_rotate_spiral
            ),
            
            # 4. SlowFlashVisual
            SlowFlashVisual(
                image_paths=self.image_paths,
                on_change_image=self._on_change_image,
                on_rotate_spiral=self._on_rotate_spiral
            ),
            
            # 5. FlashTextVisual
            FlashTextVisual(
                image_paths=self.image_paths,
                text_lines=self.text_lines,
                on_change_image=self._on_change_image,
                on_change_text=self._on_change_text,
                on_rotate_spiral=self._on_rotate_spiral
            ),
            
            # 6. ParallelImagesVisual
            ParallelImagesVisual(
                image_paths=self.image_paths,
                on_change_image=self._on_change_parallel_image,
                on_rotate_spiral=self._on_rotate_spiral
            ),
            
            # 7. AnimationVisual
            AnimationVisual(
                video_paths=self.video_paths,
                on_change_video=self._on_change_image,
                on_rotate_spiral=self._on_rotate_spiral
            )
        ]
    
    # Callbacks
    def _on_change_image(self, index: int):
        """Callback when image changes."""
        self.current_image_index = index
        self.image_changes.append((self.frame_count, index))
        # Keep last 20 changes
        if len(self.image_changes) > 20:
            self.image_changes.pop(0)
    
    def _on_change_parallel_image(self, slot: int, index: int):
        """Callback for parallel image changes."""
        self.current_slot_images[slot] = index
        self.image_changes.append((self.frame_count, f"Slot {slot}: {index}"))
        if len(self.image_changes) > 20:
            self.image_changes.pop(0)
    
    def _on_change_text(self, text: str):
        """Callback when text changes."""
        self.current_text = text
        self.text_changes.append((self.frame_count, text))
        if len(self.text_changes) > 15:
            self.text_changes.pop(0)
    
    def _on_change_subtext(self, text: str):
        """Callback when subtext changes."""
        self.current_subtext = text
    
    def _on_rotate_spiral(self):
        """Callback for spiral rotation."""
        degrees = 2.0  # Default rotation amount
        self.spiral_rotation = (self.spiral_rotation + degrees) % 360.0
        self.spiral_updates.append((self.frame_count, degrees))
        if len(self.spiral_updates) > 60:  # Keep last 1 second
            self.spiral_updates.pop(0)
    
    def switch_visual(self, index: int):
        """Switch to a different visual program."""
        if 0 <= index < len(self.visuals):
            self.current_visual_index = index
            self.current_visual = self.visuals[index]
            self.current_visual.reset()
            self.image_changes.clear()
            self.text_changes.clear()
            self.subtext_changes.clear()
            self.spiral_updates.clear()
            self.current_slot_images.clear()
            self.spiral_rotation = 0.0
            self.frame_count = 0
            self.start_time = time.time()
    
    def next_visual(self):
        """Cycle to next visual program."""
        self.switch_visual((self.current_visual_index + 1) % len(self.visuals))
    
    def reset_current(self):
        """Reset current visual program."""
        self.current_visual.reset()
        self.image_changes.clear()
        self.text_changes.clear()
        self.subtext_changes.clear()
        self.spiral_updates.clear()
        self.current_slot_images.clear()
        self.spiral_rotation = 0.0
        self.frame_count = 0
        self.start_time = time.time()
    
    def update(self):
        """Update visual program state."""
        if not self.paused:
            cycler = self.current_visual.get_cycler()
            if cycler:
                cycler.advance()
                self.frame_count += 1
                
                # Auto-switch when complete
                if self.current_visual.complete():
                    self.next_visual()
    
    def draw(self):
        """Draw the demo UI."""
        self.screen.fill(BG_COLOR)
        
        # Title
        title = self.font_title.render("MesmerGlass Visual Programs Demo", True, TEXT_COLOR)
        self.screen.blit(title, (20, 20))
        
        # Current visual info
        y = 90
        visual_name = self.visual_names[self.current_visual_index]
        name_text = self.font_large.render(f"Current: {visual_name}", True, HIGHLIGHT_COLOR)
        self.screen.blit(name_text, (20, y))
        
        # Status
        y += 50
        status = "PAUSED" if self.paused else "RUNNING"
        status_color = ACCENT_COLOR if self.paused else HIGHLIGHT_COLOR
        status_text = self.font_normal.render(f"Status: {status}", True, status_color)
        self.screen.blit(status_text, (20, y))
        
        # Progress
        y += 40
        progress = self.current_visual.progress()
        progress_text = self.font_normal.render(f"Progress: {progress*100:.1f}%", True, TEXT_COLOR)
        self.screen.blit(progress_text, (20, y))
        
        # Progress bar
        bar_width = 400
        bar_height = 20
        bar_x = 220
        bar_y = y
        pygame.draw.rect(self.screen, DIM_COLOR, (bar_x, bar_y, bar_width, bar_height), 2)
        if progress > 0:
            fill_width = int(bar_width * progress)
            pygame.draw.rect(self.screen, PROGRESS_COLOR, (bar_x+2, bar_y+2, fill_width-4, bar_height-4))
        
        # Cycler stats
        y += 45
        cycler = self.current_visual.get_cycler()
        if cycler:
            index_text = self.font_normal.render(f"Frame: {cycler.index()} / {cycler.length()}", True, TEXT_COLOR)
            self.screen.blit(index_text, (20, y))
            
            y += 35
            complete = "Yes" if cycler.complete() else "No"
            complete_color = ACCENT_COLOR if cycler.complete() else TEXT_COLOR
            complete_text = self.font_normal.render(f"Complete: {complete}", True, complete_color)
            self.screen.blit(complete_text, (20, y))
        
        # Runtime
        y += 40
        runtime = time.time() - self.start_time
        runtime_text = self.font_normal.render(f"Runtime: {runtime:.1f}s", True, TEXT_COLOR)
        self.screen.blit(runtime_text, (20, y))
        
        # Current state
        y += 50
        state_title = self.font_large.render("Current State:", True, ACCENT_COLOR)
        self.screen.blit(state_title, (20, y))
        
        y += 45
        if isinstance(self.current_visual, ParallelImagesVisual):
            # Show all slots
            for slot, img_idx in sorted(self.current_slot_images.items()):
                slot_text = self.font_normal.render(f"Slot {slot}: Image #{img_idx}", True, TEXT_COLOR)
                self.screen.blit(slot_text, (40, y))
                y += 35
        else:
            image_text = self.font_normal.render(f"Image: #{self.current_image_index}", True, TEXT_COLOR)
            self.screen.blit(image_text, (40, y))
        
        y += 40
        if self.current_text:
            text_display = self.current_text[:40] + "..." if len(self.current_text) > 40 else self.current_text
            text_text = self.font_normal.render(f'Text: "{text_display}"', True, TEXT_COLOR)
            self.screen.blit(text_text, (40, y))
        
        y += 40
        spiral_text = self.font_normal.render(f"Spiral: {self.spiral_rotation:.1f}°", True, TEXT_COLOR)
        self.screen.blit(spiral_text, (40, y))
        
        # Image change history
        y += 60
        history_title = self.font_large.render("Recent Changes:", True, ACCENT_COLOR)
        self.screen.blit(history_title, (20, y))
        
        y += 45
        for frame, data in reversed(self.image_changes[-10:]):
            if isinstance(data, str):
                change_text = self.font_small.render(f"F{frame}: {data}", True, DIM_COLOR)
            else:
                change_text = self.font_small.render(f"F{frame}: Image #{data}", True, DIM_COLOR)
            self.screen.blit(change_text, (40, y))
            y += 28
        
        # Visual selector (right side)
        selector_x = 750
        selector_y = 90
        selector_title = self.font_large.render("Visual Programs:", True, ACCENT_COLOR)
        self.screen.blit(selector_title, (selector_x, selector_y))
        
        selector_y += 50
        for i, name in enumerate(self.visual_names):
            color = HIGHLIGHT_COLOR if i == self.current_visual_index else TEXT_COLOR
            prefix = "▶ " if i == self.current_visual_index else "  "
            visual_text = self.font_normal.render(f"{prefix}{i+1}. {name}", True, color)
            self.screen.blit(visual_text, (selector_x, selector_y))
            selector_y += 40
        
        # Visual descriptions
        selector_y += 30
        desc_title = self.font_normal.render("Description:", True, ACCENT_COLOR)
        self.screen.blit(desc_title, (selector_x, selector_y))
        
        selector_y += 35
        descriptions = [
            ["Basic slideshow", "48 frames/image", "16 images total", "2.0°/frame rotation"],
            ["Images + text cycling", "Multi-layer subtext", "4/12/24/48 frame periods", "4.0°/frame rotation"],
            ["Accelerating slideshow", "56→12 frames/image", "Increasing zoom/rotation", "Dynamic timing"],
            ["Slow/fast alternating", "64 frames (slow)", "8 frames (fast)", "Pacing variation"],
            ["Rapid text flashing", "6 frames/flash", "Subliminal effect", "3.0°/frame rotation"],
            ["Multiple images", "3 simultaneous slots", "Independent timing", "Visual layering"],
            ["Video-focused", "300 frames/video", "6 videos total", "1.5°/frame rotation"]
        ]
        
        for line in descriptions[self.current_visual_index]:
            desc_text = self.font_small.render(f"• {line}", True, DIM_COLOR)
            self.screen.blit(desc_text, (selector_x + 20, selector_y))
            selector_y += 28
        
        # Controls (bottom)
        controls_y = self.height - 140
        controls_title = self.font_normal.render("Controls:", True, ACCENT_COLOR)
        self.screen.blit(controls_title, (selector_x, controls_y))
        
        controls_y += 35
        controls = [
            "1-7: Select visual program",
            "SPACE: Pause/Resume",
            "R: Reset current visual",
            "N: Next visual (auto-cycle)",
            "Q/ESC: Quit"
        ]
        for control in controls:
            control_text = self.font_small.render(control, True, DIM_COLOR)
            self.screen.blit(control_text, (selector_x, controls_y))
            controls_y += 25
        
        pygame.display.flip()
    
    def handle_events(self):
        """Handle pygame events."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_q, pygame.K_ESCAPE):
                    return False
                
                elif event.key == pygame.K_SPACE:
                    self.paused = not self.paused
                
                elif event.key == pygame.K_r:
                    self.reset_current()
                
                elif event.key == pygame.K_n:
                    self.next_visual()
                
                elif pygame.K_1 <= event.key <= pygame.K_7:
                    index = event.key - pygame.K_1
                    self.switch_visual(index)
        
        return True
    
    def run(self):
        """Main application loop."""
        running = True
        
        print("=" * 60)
        print("MesmerGlass Visual Programs Demo")
        print("=" * 60)
        print("\nControls:")
        print("  1-7: Select visual program")
        print("  SPACE: Pause/Resume")
        print("  R: Reset current visual")
        print("  N: Next visual (auto-cycle)")
        print("  Q/ESC: Quit")
        print("\nStarting with SimpleVisual...")
        print()
        
        while running:
            running = self.handle_events()
            self.update()
            self.draw()
            self.clock.tick(self.fps)
        
        pygame.quit()
        print("\nDemo finished!")
        print(f"Total runtime: {time.time() - self.start_time:.1f}s")


if __name__ == "__main__":
    app = VisualDemoApp()
    app.run()
