"""
Weighted random selection with anti-repetition tracking.

Based on Trance's shuffler algorithm - provides fair random selection
while avoiding recent repeats for better variety.
"""

import random
from typing import List, Optional


class Shuffler:
    """
    Weighted random shuffler with last-N anti-repetition.
    
    Maintains dynamic weights for each item. When an item is selected,
    its weight decreases (making it less likely to be chosen again soon).
    When an item falls off the "last N" history, its weight increases back.
    
    This creates variety while maintaining randomness - you won't see
    the same item twice within the last N selections.
    
    Example:
        # Shuffle through 20 images, avoid repeating within last 8
        shuffler = Shuffler(item_count=20, initial_weight=10, history_size=8)
        
        for _ in range(100):
            index = shuffler.next()
            print(f"Show image {index}")
    
    Args:
        item_count: Number of items to shuffle between
        initial_weight: Starting weight for each item (default: 10)
        history_size: How many recent selections to avoid repeating (default: 8)
    """
    
    def __init__(
        self,
        item_count: int,
        initial_weight: int = 10,
        history_size: int = 8
    ):
        if item_count <= 0:
            raise ValueError(f"item_count must be positive, got {item_count}")
        if initial_weight < 0:
            raise ValueError(f"initial_weight must be non-negative, got {initial_weight}")
        if history_size < 0:
            raise ValueError(f"history_size must be non-negative, got {history_size}")
        
        self.item_count = item_count
        self.initial_weight = initial_weight
        self.history_size = history_size
        
        # Initialize all items with equal weight
        self.weights: List[int] = [initial_weight] * item_count
        self.total_weight = initial_weight * item_count
        
        # Track last N selections (FIFO queue)
        self.history: List[int] = []
    
    def next(self) -> int:
        """
        Select next item using weighted random selection.
        
        Returns:
            Index of selected item [0, item_count)
        
        Raises:
            ValueError: If total weight is 0 (all items exhausted)
        """
        if self.total_weight <= 0:
            raise ValueError(
                "Total weight is 0 - all items have been exhausted. "
                "Consider increasing initial_weight or history_size."
            )
        
        # Weighted random selection
        # Pick a random value in [0, total_weight)
        value = random.randint(0, self.total_weight - 1)
        
        # Find which item this value corresponds to
        for i in range(self.item_count):
            if value < self.weights[i]:
                # Found the item - track selection and return
                self._track_selection(i)
                return i
            value -= self.weights[i]
        
        # Fallback (should never reach here with valid weights)
        return 0
    
    def _track_selection(self, index: int) -> None:
        """
        Track a selection and adjust weights.
        
        Args:
            index: Index of item that was selected
        """
        # Add to history
        self.history.append(index)
        
        # Decrease weight of selected item
        self.decrease(index)
        
        # If history is too long, restore weight of oldest item
        if len(self.history) > self.history_size:
            oldest = self.history.pop(0)
            self.increase(oldest)
    
    def increase(self, index: int) -> None:
        """
        Increase selection probability for an item.
        
        Args:
            index: Index of item to make more likely
        """
        if index < 0 or index >= self.item_count:
            raise ValueError(f"Index {index} out of range [0, {self.item_count})")
        
        self.weights[index] += 1
        self.total_weight += 1
    
    def decrease(self, index: int) -> None:
        """
        Decrease selection probability for an item.
        
        Only decreases if weight is positive (prevents negative weights).
        
        Args:
            index: Index of item to make less likely
        """
        if index < 0 or index >= self.item_count:
            raise ValueError(f"Index {index} out of range [0, {self.item_count})")
        
        if self.weights[index] > 0:
            self.weights[index] -= 1
            self.total_weight -= 1
    
    def get_weight(self, index: int) -> int:
        """
        Get current weight of an item.
        
        Args:
            index: Index of item
            
        Returns:
            Current weight value
        """
        if index < 0 or index >= self.item_count:
            raise ValueError(f"Index {index} out of range [0, {self.item_count})")
        return self.weights[index]
    
    def get_history(self) -> List[int]:
        """
        Get list of recently selected indices.
        
        Returns:
            Copy of history list (oldest to newest)
        """
        return self.history.copy()
    
    def reset(self) -> None:
        """
        Reset shuffler to initial state.
        
        Clears history and restores all weights to initial values.
        """
        self.weights = [self.initial_weight] * self.item_count
        self.total_weight = self.initial_weight * self.item_count
        self.history = []
    
    def __repr__(self) -> str:
        return (
            f"Shuffler(item_count={self.item_count}, "
            f"initial_weight={self.initial_weight}, "
            f"history_size={self.history_size}, "
            f"total_weight={self.total_weight})"
        )
