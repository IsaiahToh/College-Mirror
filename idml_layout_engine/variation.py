"""
Variation Engine - Rule-Based Layout Variation
===============================================

This module implements controlled, rule-based layout variation
that is fully deterministic and seedable.

Variation Types:
1. Slot swapping - Exchange compatible slots between columns
2. Quote placement - Move quotes to different compatible positions
3. Image placement - Swap image positions

All variations:
- Respect slot compatibility rules
- Respect column constraints
- Are fully reproducible with the same seed
- Do NOT use AI or heuristics

The variation engine takes a LayoutTemplate and a set of content
assignments, then applies rule-based modifications to create
visual variety while maintaining layout correctness.

Design Principles:
- Deterministic: Same inputs + seed = same output
- Conservative: Only swap known-compatible elements
- Debuggable: All variations logged and traceable
- Reversible: Original assignments can be reconstructed
"""

from __future__ import annotations

import random
import logging
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple, Set
from copy import deepcopy

from .models import (
    Slot,
    SlotType,
    VerticalPosition,
    LayoutTemplate,
    ContentBlock,
    ContentSection,
    ContentType,
    SlotAssignment,
    PageInstance,
)


logger = logging.getLogger(__name__)


# =============================================================================
# Variation Rules
# =============================================================================


@dataclass
class VariationRule:
    """
    A rule that defines a valid variation operation.
    
    Rules specify:
    - What types of slots can be swapped
    - Under what conditions the swap is valid
    - How often the rule should be applied (probability)
    
    Attributes:
        rule_id: Unique identifier for this rule
        slot_type: Type of slot this rule applies to
        allowed_vertical_positions: Which vertical positions can participate
        cross_column_only: If True, only swap between different columns
        probability: Chance of applying this rule (0.0 to 1.0)
        description: Human-readable description
    """
    rule_id: str
    slot_type: SlotType
    allowed_vertical_positions: Set[VerticalPosition] = field(
        default_factory=lambda: {VerticalPosition.TOP, VerticalPosition.MIDDLE, VerticalPosition.BOTTOM}
    )
    cross_column_only: bool = True
    probability: float = 0.5
    description: str = ""
    
    def applies_to(self, slot: Slot) -> bool:
        """Check if this rule applies to the given slot."""
        if slot.is_fixed:
            return False
        if slot.slot_type != self.slot_type:
            return False
        if slot.vertical_position not in self.allowed_vertical_positions:
            return False
        return True


# Default variation rules
DEFAULT_VARIATION_RULES = [
    VariationRule(
        rule_id="swap_images_top",
        slot_type=SlotType.IMAGE,
        allowed_vertical_positions={VerticalPosition.TOP},
        cross_column_only=True,
        probability=0.6,
        description="Swap image positions in top zone between columns",
    ),
    VariationRule(
        rule_id="swap_images_middle",
        slot_type=SlotType.IMAGE,
        allowed_vertical_positions={VerticalPosition.MIDDLE},
        cross_column_only=True,
        probability=0.5,
        description="Swap image positions in middle zone between columns",
    ),
    VariationRule(
        rule_id="swap_quotes",
        slot_type=SlotType.QUOTE,
        allowed_vertical_positions={VerticalPosition.MIDDLE, VerticalPosition.BOTTOM},
        cross_column_only=True,
        probability=0.4,
        description="Swap quote positions between columns",
    ),
]


# =============================================================================
# Variation Operations
# =============================================================================


@dataclass
class VariationOperation:
    """
    Record of a single variation operation that was applied.
    
    Used for debugging, logging, and potentially reversing variations.
    """
    operation_id: str
    rule_id: str
    slot_a_id: str
    slot_b_id: str
    description: str
    applied: bool = True
    
    def __repr__(self) -> str:
        status = "applied" if self.applied else "skipped"
        return f"Variation({self.rule_id}: {self.slot_a_id} <-> {self.slot_b_id} [{status}])"


# =============================================================================
# Variation Engine
# =============================================================================


class VariationEngine:
    """
    Rule-based engine for applying layout variations.
    
    The variation engine:
    1. Takes a layout template with content assignments
    2. Identifies candidate slots for variation based on rules
    3. Applies variations deterministically using a seeded RNG
    4. Returns modified assignments with variation log
    
    Usage:
        engine = VariationEngine(seed=42)
        
        varied_assignments, operations = engine.apply_variations(
            template=layout_template,
            assignments=original_assignments
        )
    
    Determinism:
        Given the same template, assignments, and seed, the engine
        will always produce the same output. This is critical for
        reproducibility and debugging.
    """
    
    def __init__(
        self,
        seed: Optional[int] = None,
        rules: Optional[List[VariationRule]] = None,
        max_variations_per_page: int = 3,
    ):
        """
        Initialize the variation engine.
        
        Args:
            seed: Random seed for reproducibility (None = random)
            rules: List of variation rules to apply (None = defaults)
            max_variations_per_page: Maximum variations to apply per page
        """
        self.seed = seed if seed is not None else random.randint(0, 2**31)
        self.rng = random.Random(self.seed)
        self.rules = rules or DEFAULT_VARIATION_RULES
        self.max_variations_per_page = max_variations_per_page
        
        # Track applied operations for logging/debugging
        self.operations: List[VariationOperation] = []
        self._operation_counter = 0
        
        logger.info(f"VariationEngine initialized with seed={self.seed}")
    
    def reset(self, new_seed: Optional[int] = None) -> None:
        """
        Reset the engine state.
        
        Args:
            new_seed: New seed to use (None = keep current seed)
        """
        if new_seed is not None:
            self.seed = new_seed
        self.rng = random.Random(self.seed)
        self.operations = []
        self._operation_counter = 0
    
    def apply_variations(
        self,
        template: LayoutTemplate,
        assignments: Dict[str, SlotAssignment],
    ) -> Tuple[Dict[str, SlotAssignment], List[VariationOperation]]:
        """
        Apply rule-based variations to slot assignments.
        
        Args:
            template: The layout template defining available slots
            assignments: Current slot assignments (slot_id -> assignment)
            
        Returns:
            Tuple of (modified assignments dict, list of operations applied)
        """
        # Deep copy assignments to avoid modifying original
        varied = deepcopy(assignments)
        
        # Reset operation tracking for this run
        self.operations = []
        
        # Find swappable slot pairs for each rule
        for rule in self.rules:
            swap_pairs = self._find_swap_candidates(template, varied, rule)
            
            for slot_a, slot_b in swap_pairs:
                # Check probability
                if self.rng.random() > rule.probability:
                    self._record_operation(
                        rule.rule_id, slot_a.slot_id, slot_b.slot_id,
                        f"Skipped by probability ({rule.probability})",
                        applied=False
                    )
                    continue
                
                # Apply the swap
                self._swap_assignments(varied, slot_a.slot_id, slot_b.slot_id)
                self._record_operation(
                    rule.rule_id, slot_a.slot_id, slot_b.slot_id,
                    rule.description,
                    applied=True
                )
        
        logger.info(f"Applied {len([o for o in self.operations if o.applied])} variations")
        return varied, self.operations
    
    def _find_swap_candidates(
        self,
        template: LayoutTemplate,
        assignments: Dict[str, SlotAssignment],
        rule: VariationRule,
    ) -> List[Tuple[Slot, Slot]]:
        """
        Find candidate slot pairs that can be swapped under the given rule.
        
        Only returns pairs where:
        1. Both slots match the rule criteria
        2. Both slots have assignments (or neither does)
        3. Slots are in different columns (if cross_column_only)
        4. Slots are size-compatible
        
        Args:
            template: The layout template
            assignments: Current assignments
            rule: The variation rule to apply
            
        Returns:
            List of (slot_a, slot_b) pairs that can be swapped
        """
        # Find slots matching this rule
        matching_slots = [
            slot for slot in template.slots
            if rule.applies_to(slot)
        ]
        
        # Group by vertical position
        by_position: Dict[VerticalPosition, List[Slot]] = {}
        for slot in matching_slots:
            if slot.vertical_position not in by_position:
                by_position[slot.vertical_position] = []
            by_position[slot.vertical_position].append(slot)
        
        pairs = []
        
        for position, slots in by_position.items():
            # Need at least 2 slots to form a pair
            if len(slots) < 2:
                continue
            
            # Find valid pairs
            for i, slot_a in enumerate(slots):
                for slot_b in slots[i + 1:]:
                    # Check cross-column requirement
                    if rule.cross_column_only:
                        if slot_a.column_index == slot_b.column_index:
                            continue
                    
                    # Check size compatibility
                    if not self._are_size_compatible(slot_a, slot_b):
                        continue
                    
                    # Check both have assignments or neither does
                    has_a = slot_a.slot_id in assignments
                    has_b = slot_b.slot_id in assignments
                    if has_a != has_b:
                        continue  # One assigned, one not - don't swap
                    
                    pairs.append((slot_a, slot_b))
        
        # Shuffle pairs for variety (still deterministic due to seeded RNG)
        self.rng.shuffle(pairs)
        
        return pairs
    
    def _are_size_compatible(self, slot_a: Slot, slot_b: Slot) -> bool:
        """
        Check if two slots are size-compatible for swapping.
        
        Slots are compatible if their paragraph units are within
        20% of each other (configurable).
        """
        if slot_a.paragraph_units == 0 or slot_b.paragraph_units == 0:
            return False
        
        ratio = slot_a.paragraph_units / slot_b.paragraph_units
        return 0.8 <= ratio <= 1.25
    
    def _swap_assignments(
        self,
        assignments: Dict[str, SlotAssignment],
        slot_id_a: str,
        slot_id_b: str,
    ) -> None:
        """
        Swap the content assignments between two slots.
        
        Modifies the assignments dict in place.
        """
        assignment_a = assignments.get(slot_id_a)
        assignment_b = assignments.get(slot_id_b)
        
        if assignment_a and assignment_b:
            # Swap the content between slots
            content_a = assignment_a.content
            content_b = assignment_b.content
            
            assignments[slot_id_a] = SlotAssignment(
                slot=assignment_a.slot,
                content=content_b,
            )
            assignments[slot_id_b] = SlotAssignment(
                slot=assignment_b.slot,
                content=content_a,
            )
        elif assignment_a and not assignment_b:
            # Move A's content to B
            assignments[slot_id_b] = SlotAssignment(
                slot=assignment_a.slot.with_geometry(assignment_a.slot.geometry),
                content=assignment_a.content,
            )
            del assignments[slot_id_a]
        elif assignment_b and not assignment_a:
            # Move B's content to A
            assignments[slot_id_a] = SlotAssignment(
                slot=assignment_b.slot.with_geometry(assignment_b.slot.geometry),
                content=assignment_b.content,
            )
            del assignments[slot_id_b]
        # If neither has assignment, nothing to swap
    
    def _record_operation(
        self,
        rule_id: str,
        slot_a_id: str,
        slot_b_id: str,
        description: str,
        applied: bool,
    ) -> None:
        """Record a variation operation."""
        op = VariationOperation(
            operation_id=f"op_{self._operation_counter}",
            rule_id=rule_id,
            slot_a_id=slot_a_id,
            slot_b_id=slot_b_id,
            description=description,
            applied=applied,
        )
        self.operations.append(op)
        self._operation_counter += 1
        
        if applied:
            logger.debug(f"Applied: {op}")
        else:
            logger.debug(f"Skipped: {op}")
    
    def get_variation_report(self) -> str:
        """
        Generate a human-readable report of applied variations.
        
        Returns:
            Multi-line string describing all operations
        """
        lines = [
            f"Variation Report (seed={self.seed})",
            "=" * 40,
            "",
        ]
        
        applied = [op for op in self.operations if op.applied]
        skipped = [op for op in self.operations if not op.applied]
        
        lines.append(f"Applied: {len(applied)}, Skipped: {len(skipped)}")
        lines.append("")
        
        if applied:
            lines.append("Applied Operations:")
            for op in applied:
                lines.append(f"  - [{op.rule_id}] {op.slot_a_id} <-> {op.slot_b_id}")
                lines.append(f"    {op.description}")
        
        if skipped:
            lines.append("")
            lines.append("Skipped Operations:")
            for op in skipped:
                lines.append(f"  - [{op.rule_id}] {op.slot_a_id} <-> {op.slot_b_id}")
                lines.append(f"    {op.description}")
        
        return "\n".join(lines)


# =============================================================================
# Content-to-Slot Assignment
# =============================================================================


class SlotAssigner:
    """
    Assigns content blocks to layout slots.
    
    The assigner takes content sections and a layout template,
    then produces a set of slot assignments that map content
    to layout positions.
    
    Assignment Strategy:
    1. Titles go to TITLE slots
    2. Quotes go to QUOTE slots (with placement preferences)
    3. Body paragraphs flow into PARAGRAPH slots
    4. Images go to IMAGE slots on same page as their section title
    
    The assigner respects:
    - Slot type compatibility
    - Size constraints (paragraph units)
    - Page boundaries
    """
    
    def __init__(self, template: LayoutTemplate):
        """
        Initialize the slot assigner.
        
        Args:
            template: The layout template to use for assignments
        """
        self.template = template
    
    def assign_content(
        self,
        sections: List[ContentSection],
    ) -> Dict[str, SlotAssignment]:
        """
        Assign content sections to slots.
        
        Each section gets assigned to its own spread to avoid overlapping.
        
        Args:
            sections: List of content sections to assign
            
        Returns:
            Dictionary mapping slot_id to SlotAssignment
        """
        assignments: Dict[str, SlotAssignment] = {}
        
        # Track which slots are used
        used_slots: Set[str] = set()
        
        # Get available spread indices
        available_spreads = sorted(set(s.spread_index for s in self.template.slots))
        
        for section_idx, section in enumerate(sections):
            # Assign each section to its own spread
            target_spread = available_spreads[section_idx] if section_idx < len(available_spreads) else None
            section_assignments = self._assign_section(section, used_slots, target_spread)
            assignments.update(section_assignments)
            used_slots.update(section_assignments.keys())
        
        return assignments
    
    def _assign_section(
        self,
        section: ContentSection,
        used_slots: Set[str],
        target_spread: Optional[int] = None,
    ) -> Dict[str, SlotAssignment]:
        """
        Assign a single content section to slots.
        
        Args:
            section: The content section to assign
            used_slots: Set of already-used slot IDs
            target_spread: Target spread index for this section (None = any spread)
            
        Returns:
            Dictionary of assignments for this section
        """
        assignments = {}
        
        # Assign title - prefer target spread if specified
        title_slot = self._find_available_slot(
            SlotType.TITLE, used_slots, prefer_column=0, target_spread=target_spread
        )
        if title_slot:
            assignments[title_slot.slot_id] = SlotAssignment(
                slot=title_slot,
                content=section.title,
            )
            used_slots.add(title_slot.slot_id)
        
        # Find the MAIN body slot - the largest paragraph slot on target spread
        # This slot's story (possibly threaded) will receive ALL body content
        main_body_slot = self._find_main_body_slot(used_slots, target_spread)
        
        # Assign all body paragraphs (includes subheaders and quote placeholders)
        # to the same slot's story - they will flow through threaded frames
        body_paragraphs = section.get_body_paragraphs()
        
        if main_body_slot and body_paragraphs:
            # Create a single assignment with all paragraphs
            assignment = SlotAssignment(slot=main_body_slot, content=body_paragraphs[0])
            for para in body_paragraphs[1:]:
                assignment.add_content(para)
            assignments[main_body_slot.slot_id] = assignment
            # Mark this slot as used
            used_slots.add(main_body_slot.slot_id)
        
        # Assign images - prefer target spread
        for idx, image_path in enumerate(section.image_paths):
            image_slot = self._find_available_slot(
                SlotType.IMAGE, used_slots, target_spread=target_spread
            )
            if image_slot:
                # Create a pseudo content block for the image
                image_content = ContentBlock(
                    content_id=f"{section.section_id}_image_{idx}",
                    content_type=ContentType.BODY,  # Will be treated specially
                    text="",
                    section_title=section.title.text,
                    sequence_index=1000 + idx,  # High index for images (not part of text sequence)
                    image_path=image_path,
                )
                assignments[image_slot.slot_id] = SlotAssignment(
                    slot=image_slot,
                    content=image_content,
                )
                used_slots.add(image_slot.slot_id)
        
        return assignments
    
    def _find_main_body_slot(
        self,
        used_slots: Set[str],
        target_spread: Optional[int] = None,
    ) -> Optional[Slot]:
        """
        Find the main body slot - the largest paragraph slot with a threaded story.
        
        This slot will receive all body content, which flows through
        the threaded frame chain.
        
        Args:
            used_slots: Set of already-used slot IDs
            target_spread: Target spread index (None = any spread)
        
        Returns:
            The best slot for body content, or None if unavailable
        """
        candidates = [
            slot for slot in self.template.get_slots_by_type(SlotType.PARAGRAPH)
            if slot.slot_id not in used_slots
        ]
        
        # Filter by target spread if specified
        if target_spread is not None:
            spread_candidates = [s for s in candidates if s.spread_index == target_spread]
            if spread_candidates:
                candidates = spread_candidates
        
        if not candidates:
            return None
        
        # Prefer slots on earlier spreads, then by size (largest first)
        def priority_key(slot: Slot) -> Tuple[int, float]:
            # Negative height so larger slots come first
            return (slot.spread_index, -slot.geometry.height)
        
        candidates.sort(key=priority_key)
        return candidates[0]
    
    def _find_available_slot(
        self,
        slot_type: SlotType,
        used_slots: Set[str],
        prefer_column: Optional[int] = None,
        prefer_position: Optional[VerticalPosition] = None,
        target_spread: Optional[int] = None,
    ) -> Optional[Slot]:
        """
        Find an available slot of the given type.
        
        Slots are prioritized by their spatial position:
        1. Target spread (if specified)
        2. Spread index (earlier spreads first)
        3. For TITLE slots: prefer larger slots (styled titles are typically bigger)
        4. Y position (top to bottom)
        5. X position (left to right)
        
        This ensures content fills the page top-to-bottom before
        moving to the next page.
        
        Args:
            slot_type: Type of slot to find
            used_slots: Set of already-used slot IDs
            prefer_column: Preferred column (optional)
            prefer_position: Preferred vertical position (optional)
            target_spread: Target spread index (optional)
            
        Returns:
            Available Slot or None if none available
        """
        candidates = [
            slot for slot in self.template.get_slots_by_type(slot_type)
            if slot.slot_id not in used_slots
        ]
        
        # Filter by target spread if specified
        if target_spread is not None:
            spread_candidates = [s for s in candidates if s.spread_index == target_spread]
            if spread_candidates:
                candidates = spread_candidates
        
        if not candidates:
            return None
        
        # Sort by spatial position: spread index, then Y, then X
        # This ensures we fill content top-to-bottom, left-to-right
        def spatial_key(slot: Slot) -> Tuple[int, float, float]:
            return (slot.spread_index, slot.geometry.y, slot.geometry.x)
        
        # For TITLE slots, prefer larger slots (styled titles are bigger)
        # This ensures we use the main styled title instead of small headers
        if slot_type == SlotType.TITLE:
            def title_key(slot: Slot) -> Tuple[int, float]:
                # Sort by spread_index first, then by -height (larger first)
                return (slot.spread_index, -slot.geometry.height)
            candidates.sort(key=title_key)
        else:
            candidates.sort(key=spatial_key)
        
        return candidates[0]
