"""
Core Algorithms for IDML Layout Engine
=======================================

This module contains the core algorithms used by the layout engine:

1. Column Detection - Assign frames to columns based on geometry
2. Slot Normalization - Compute vertical positions and ordering
3. Interchangeable Slot Grouping - Group slots that can be swapped
4. Content-to-Slot Assignment - Match content to appropriate slots
5. Text Flow Estimation - Estimate how content fills slots

All algorithms are:
- Deterministic (same inputs → same outputs)
- Well-documented with invariants
- Designed for debuggability
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional, Set
from collections import defaultdict
import math

from .models import (
    Slot,
    SlotType,
    VerticalPosition,
    LayoutTemplate,
    FrameGeometry,
    PageDimensions,
    ContentBlock,
    ContentType,
)


# =============================================================================
# Column Detection
# =============================================================================


def detect_column(
    geometry: FrameGeometry,
    page_dimensions: PageDimensions,
    is_left_page: bool = True,
) -> int:
    """
    Detect which column a frame belongs to based on its geometry.
    
    Algorithm:
    1. Calculate the frame's horizontal center
    2. Calculate column boundaries based on page dimensions
    3. Return the column index whose range contains the center
    
    Edge Cases:
    - Frames spanning multiple columns: Assigned to column with most overlap
    - Frames outside all columns: Assigned to nearest column
    
    Args:
        geometry: The frame's geometry
        page_dimensions: Page dimension information
        is_left_page: Whether this is a left (verso) page
        
    Returns:
        0-based column index
        
    Invariants:
    - Result is in range [0, page_dimensions.column_count)
    - Deterministic for same inputs
    """
    # Calculate frame's horizontal center
    frame_center_x = geometry.center_x
    
    # Get margin (accounts for left/right page)
    left_margin = (
        page_dimensions.margin_inside 
        if is_left_page 
        else page_dimensions.margin_outside
    )
    
    # Calculate column boundaries
    column_width = page_dimensions.column_width
    gutter = page_dimensions.column_gutter
    
    best_column = 0
    min_distance = float('inf')
    
    for col_idx in range(page_dimensions.column_count):
        # Column left edge
        col_start = left_margin + col_idx * (column_width + gutter)
        # Column center
        col_center = col_start + column_width / 2
        
        # Distance from frame center to column center
        distance = abs(frame_center_x - col_center)
        
        if distance < min_distance:
            min_distance = distance
            best_column = col_idx
    
    return best_column


def detect_column_with_overlap(
    geometry: FrameGeometry,
    page_dimensions: PageDimensions,
    is_left_page: bool = True,
) -> Tuple[int, float]:
    """
    Detect column with overlap percentage.
    
    Returns both the column index and the percentage of the frame
    that overlaps with that column. Useful for detecting frames
    that span multiple columns.
    
    Args:
        geometry: The frame's geometry
        page_dimensions: Page dimension information
        is_left_page: Whether this is a left page
        
    Returns:
        Tuple of (column_index, overlap_percentage)
        overlap_percentage is in range [0.0, 1.0]
    """
    left_margin = (
        page_dimensions.margin_inside 
        if is_left_page 
        else page_dimensions.margin_outside
    )
    
    column_width = page_dimensions.column_width
    gutter = page_dimensions.column_gutter
    
    best_column = 0
    max_overlap = 0.0
    
    for col_idx in range(page_dimensions.column_count):
        col_start = left_margin + col_idx * (column_width + gutter)
        col_end = col_start + column_width
        
        # Calculate overlap
        overlap_start = max(geometry.x, col_start)
        overlap_end = min(geometry.right, col_end)
        
        if overlap_end > overlap_start:
            overlap_width = overlap_end - overlap_start
            overlap_ratio = overlap_width / geometry.width
            
            if overlap_ratio > max_overlap:
                max_overlap = overlap_ratio
                best_column = col_idx
    
    return best_column, max_overlap


# =============================================================================
# Vertical Position Normalization
# =============================================================================


def compute_vertical_position(
    geometry: FrameGeometry,
    page_dimensions: PageDimensions,
) -> VerticalPosition:
    """
    Compute the normalized vertical position of a frame.
    
    Divides the page into three equal zones:
    - TOP: Upper third of the page
    - MIDDLE: Middle third
    - BOTTOM: Lower third
    
    Uses the frame's vertical center for classification.
    
    Args:
        geometry: The frame's geometry
        page_dimensions: Page dimension information
        
    Returns:
        VerticalPosition enum value
        
    Note:
        Uses page height, not content height (excludes margins).
        This is intentional - we want consistent zones regardless
        of margin settings.
    """
    page_height = page_dimensions.height
    frame_center_y = geometry.center_y
    
    # Divide into thirds
    third = page_height / 3
    
    if frame_center_y < third:
        return VerticalPosition.TOP
    elif frame_center_y < 2 * third:
        return VerticalPosition.MIDDLE
    else:
        return VerticalPosition.BOTTOM


def compute_normalized_y(
    geometry: FrameGeometry,
    page_dimensions: PageDimensions,
) -> float:
    """
    Compute a normalized Y position (0.0 to 1.0).
    
    Useful for fine-grained vertical ordering within a zone.
    
    Args:
        geometry: The frame's geometry
        page_dimensions: Page dimension information
        
    Returns:
        Normalized Y position where:
        - 0.0 = top of page
        - 1.0 = bottom of page
    """
    return geometry.y / page_dimensions.height


def sort_frames_vertically(
    frames: List[FrameGeometry],
    page_dimensions: PageDimensions,
) -> List[Tuple[int, FrameGeometry]]:
    """
    Sort frames by their vertical position (top to bottom).
    
    Args:
        frames: List of frame geometries
        page_dimensions: Page dimension information
        
    Returns:
        List of (original_index, geometry) tuples, sorted by Y position
    """
    indexed = [(i, f) for i, f in enumerate(frames)]
    return sorted(indexed, key=lambda x: x[1].y)


# =============================================================================
# Interchangeable Slot Grouping
# =============================================================================


@dataclass
class SlotGroup:
    """
    A group of interchangeable slots.
    
    Slots in the same group can be swapped during variation
    without affecting layout correctness.
    """
    group_id: str
    slot_ids: Set[str]
    slot_type: SlotType
    vertical_position: VerticalPosition
    size_range: Tuple[float, float]  # (min, max) paragraph units
    
    def can_include(self, slot: Slot, size_tolerance: float = 0.2) -> bool:
        """
        Check if a slot can be included in this group.
        
        Args:
            slot: The slot to check
            size_tolerance: Allowed size variation (0.2 = 20%)
            
        Returns:
            True if slot is compatible with this group
        """
        if slot.slot_type != self.slot_type:
            return False
        if slot.vertical_position != self.vertical_position:
            return False
        
        # Check size compatibility
        min_size, max_size = self.size_range
        allowed_min = min_size * (1 - size_tolerance)
        allowed_max = max_size * (1 + size_tolerance)
        
        return allowed_min <= slot.paragraph_units <= allowed_max


def group_interchangeable_slots(
    slots: List[Slot],
    size_tolerance: float = 0.2,
    require_different_columns: bool = True,
) -> Dict[str, Set[str]]:
    """
    Group slots that can be safely interchanged.
    
    Two slots are interchangeable if:
    1. They have the same slot_type
    2. They have the same vertical_position
    3. They have similar sizes (within tolerance)
    4. Neither is marked as fixed
    5. They are in different columns (if require_different_columns=True)
    
    Args:
        slots: List of slots to group
        size_tolerance: Maximum size difference ratio (0.2 = 20%)
        require_different_columns: If True, only group across columns
        
    Returns:
        Dictionary mapping group_id to set of slot_ids
        
    Algorithm:
        Uses a greedy clustering approach:
        1. Sort slots by (type, vertical_position, size)
        2. For each slot, find or create a compatible group
        3. Validate final groups have slots from different columns
    """
    groups: Dict[str, Set[str]] = {}
    group_counter = 0
    
    # Group candidates by (type, vertical_position)
    candidates: Dict[Tuple[SlotType, VerticalPosition], List[Slot]] = defaultdict(list)
    
    for slot in slots:
        if slot.is_fixed:
            continue
        key = (slot.slot_type, slot.vertical_position)
        candidates[key].append(slot)
    
    # For each candidate group, create actual groups
    for (slot_type, vert_pos), slot_list in candidates.items():
        if len(slot_list) < 2:
            continue  # Need at least 2 slots
        
        # Sort by paragraph_units for easier size comparison
        sorted_slots = sorted(slot_list, key=lambda s: s.paragraph_units)
        
        # Find compatible pairs/groups
        if require_different_columns:
            # Group slots from different columns
            by_column: Dict[int, List[Slot]] = defaultdict(list)
            for slot in sorted_slots:
                by_column[slot.column_index].append(slot)
            
            # Only create groups if we have slots in multiple columns
            if len(by_column) >= 2:
                group_id = f"group_{slot_type.name.lower()}_{vert_pos.name.lower()}_{group_counter}"
                group_counter += 1
                
                # Include all slots - actual compatibility checked during variation
                groups[group_id] = {s.slot_id for s in sorted_slots}
        else:
            # Group by size compatibility
            current_group: Set[str] = set()
            current_base_size = sorted_slots[0].paragraph_units
            
            for slot in sorted_slots:
                size_ratio = slot.paragraph_units / current_base_size
                if 1 - size_tolerance <= size_ratio <= 1 + size_tolerance:
                    current_group.add(slot.slot_id)
                else:
                    # Start new group if current has multiple slots
                    if len(current_group) >= 2:
                        group_id = f"group_{slot_type.name.lower()}_{vert_pos.name.lower()}_{group_counter}"
                        groups[group_id] = current_group
                        group_counter += 1
                    
                    current_group = {slot.slot_id}
                    current_base_size = slot.paragraph_units
            
            # Don't forget the last group
            if len(current_group) >= 2:
                group_id = f"group_{slot_type.name.lower()}_{vert_pos.name.lower()}_{group_counter}"
                groups[group_id] = current_group
                group_counter += 1
    
    return groups


# =============================================================================
# Content-to-Slot Assignment
# =============================================================================


def compute_content_size(
    content: ContentBlock,
    chars_per_paragraph_unit: int = 500,
) -> float:
    """
    Estimate the size of a content block in paragraph units.
    
    A "paragraph unit" is a normalized measure of vertical space,
    approximately equal to one average paragraph (3-5 lines).
    
    Args:
        content: The content block
        chars_per_paragraph_unit: Characters per paragraph unit
        
    Returns:
        Estimated size in paragraph units (minimum 1.0)
        
    Note:
        This is a rough estimate. Actual size depends on:
        - Font size
        - Line height
        - Column width
        - Hyphenation settings
        
        For precise estimates, would need typography metrics.
    """
    if not content.text:
        return 1.0
    
    char_count = len(content.text.strip())
    return max(1.0, char_count / chars_per_paragraph_unit)


def find_best_slot(
    content: ContentBlock,
    available_slots: List[Slot],
    prefer_column: Optional[int] = None,
    prefer_position: Optional[VerticalPosition] = None,
) -> Optional[Slot]:
    """
    Find the best available slot for a content block.
    
    Matching Criteria (in priority order):
    1. Slot type matches content type
    2. Slot has sufficient size (paragraph_units)
    3. Preferred column (if specified)
    4. Preferred vertical position (if specified)
    
    Args:
        content: The content block to place
        available_slots: List of available slots
        prefer_column: Preferred column index
        prefer_position: Preferred vertical position
        
    Returns:
        Best matching Slot, or None if no suitable slot found
    """
    # Map content type to slot type
    type_mapping = {
        ContentType.TITLE: SlotType.TITLE,
        ContentType.BODY: SlotType.PARAGRAPH,
        ContentType.QUOTE: SlotType.QUOTE,
    }
    
    required_slot_type = type_mapping.get(content.content_type, SlotType.PARAGRAPH)
    content_size = compute_content_size(content)
    
    # Filter to compatible slots
    compatible = [
        slot for slot in available_slots
        if slot.slot_type == required_slot_type
        and slot.paragraph_units >= content_size * 0.8  # Allow some overflow
    ]
    
    if not compatible:
        # Fallback: any slot of right type
        compatible = [
            slot for slot in available_slots
            if slot.slot_type == required_slot_type
        ]
    
    if not compatible:
        return None
    
    # Score and sort candidates
    def score_slot(slot: Slot) -> Tuple[int, int, float]:
        column_score = 0 if prefer_column is None or slot.column_index == prefer_column else 1
        position_score = 0 if prefer_position is None or slot.vertical_position == prefer_position else 1
        size_diff = abs(slot.paragraph_units - content_size)
        return (column_score, position_score, size_diff)
    
    compatible.sort(key=score_slot)
    return compatible[0]


def assign_content_to_slots(
    content_blocks: List[ContentBlock],
    template: LayoutTemplate,
) -> Dict[str, Tuple[Slot, ContentBlock]]:
    """
    Assign all content blocks to slots.
    
    Uses a greedy algorithm:
    1. Sort content by priority (titles first, then quotes, then body)
    2. For each content block, find the best available slot
    3. Mark the slot as used
    
    Args:
        content_blocks: List of content blocks to assign
        template: The layout template with slots
        
    Returns:
        Dictionary mapping slot_id to (Slot, ContentBlock) tuples
        
    Note:
        This does not handle overflow. If there are more content
        blocks than available slots, some content will not be assigned.
        Use a page expansion algorithm for handling overflow.
    """
    assignments: Dict[str, Tuple[Slot, ContentBlock]] = {}
    used_slots: Set[str] = set()
    
    # Priority order: TITLE > QUOTE > BODY
    priority = {
        ContentType.TITLE: 0,
        ContentType.QUOTE: 1,
        ContentType.BODY: 2,
    }
    
    sorted_content = sorted(
        content_blocks,
        key=lambda c: (priority.get(c.content_type, 99), c.sequence_index)
    )
    
    for content in sorted_content:
        available = [
            slot for slot in template.slots
            if slot.slot_id not in used_slots
        ]
        
        best_slot = find_best_slot(content, available)
        
        if best_slot:
            assignments[best_slot.slot_id] = (best_slot, content)
            used_slots.add(best_slot.slot_id)
    
    return assignments


# =============================================================================
# Text Flow Estimation
# =============================================================================


@dataclass
class FlowEstimate:
    """
    Estimate of how text will flow through slots.
    """
    total_content_units: float  # Total paragraph units of content
    total_slot_units: float     # Total paragraph units of slots
    overflow_units: float       # Units that won't fit
    fill_ratio: float           # Ratio of content to capacity
    pages_needed: int           # Estimated pages needed


def estimate_text_flow(
    content_blocks: List[ContentBlock],
    template: LayoutTemplate,
) -> FlowEstimate:
    """
    Estimate how content will flow through the template.
    
    This is useful for:
    - Determining if additional pages are needed
    - Detecting severe overflow/underflow
    - Planning page breaks
    
    Args:
        content_blocks: All content to be placed
        template: The layout template
        
    Returns:
        FlowEstimate with capacity analysis
    """
    # Calculate total content size
    total_content = sum(
        compute_content_size(block) for block in content_blocks
    )
    
    # Calculate total slot capacity (excluding fixed slots)
    text_slot_types = {SlotType.TITLE, SlotType.PARAGRAPH, SlotType.QUOTE}
    total_capacity = sum(
        slot.paragraph_units 
        for slot in template.slots
        if slot.slot_type in text_slot_types and not slot.is_fixed
    )
    
    # Calculate overflow
    overflow = max(0, total_content - total_capacity)
    
    # Calculate fill ratio
    fill_ratio = total_content / total_capacity if total_capacity > 0 else float('inf')
    
    # Estimate pages needed
    if total_capacity > 0:
        pages_needed = math.ceil(total_content / total_capacity)
    else:
        pages_needed = 1
    
    return FlowEstimate(
        total_content_units=total_content,
        total_slot_units=total_capacity,
        overflow_units=overflow,
        fill_ratio=fill_ratio,
        pages_needed=pages_needed,
    )


def will_text_fit(
    content: ContentBlock,
    slot: Slot,
    safety_margin: float = 0.9,
) -> bool:
    """
    Check if a content block will fit in a slot.
    
    Args:
        content: The content block
        slot: The target slot
        safety_margin: Fraction of slot size to use (0.9 = 90%)
        
    Returns:
        True if content will likely fit
    """
    content_size = compute_content_size(content)
    available_size = slot.paragraph_units * safety_margin
    return content_size <= available_size
