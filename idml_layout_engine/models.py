"""
Data Models for IDML Layout Engine
===================================

This module defines the core data structures used throughout the layout engine.
All models are designed to be:
- Immutable where possible (using frozen dataclasses)
- Serializable for debugging and caching
- Self-documenting with comprehensive docstrings

Key Concepts:
- Slot: A positioned placeholder in the layout template
- LayoutTemplate: The complete layout schema extracted from reference IDML
- ContentBlock: Parsed content from Word documents
- PageInstance: A realized page with content assigned to slots

Coordinate System:
- All measurements are in points (1 point = 1/72 inch)
- Origin (0, 0) is at the top-left corner of the page
- X increases rightward, Y increases downward
- This matches InDesign's internal coordinate system
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, List, Dict, Tuple, Set, FrozenSet
from pathlib import Path
import json


# =============================================================================
# Enumerations
# =============================================================================


class SlotType(Enum):
    """
    The semantic type of a layout slot.
    
    Determines what kind of content can be placed in the slot and
    how it should be rendered.
    """
    TITLE = auto()      # Section title frame
    SUBHEADER = auto()  # Subheading frame
    PARAGRAPH = auto()  # Body text paragraph frame
    QUOTE = auto()      # Pull quote or highlighted text frame
    IMAGE = auto()      # Image/graphic frame
    HEADER = auto()     # Page header (usually fixed)
    FOOTER = auto()     # Page footer (usually fixed)
    

class VerticalPosition(Enum):
    """
    Normalized vertical position within a column.
    
    Used for grouping interchangeable slots. Slots at the same
    vertical position in different columns may be swappable.
    
    The page is divided into thirds:
    - TOP: Upper third (y < page_height / 3)
    - MIDDLE: Middle third (page_height / 3 <= y < 2 * page_height / 3)
    - BOTTOM: Lower third (y >= 2 * page_height / 3)
    """
    TOP = auto()
    MIDDLE = auto()
    BOTTOM = auto()


class ContentType(Enum):
    """
    The semantic type of a content block parsed from Word documents.
    
    Parsing Rules:
    - TITLE: Bold + underlined text at the top of the document
    - SUBHEADER: Bold text (not underlined) after the title
    - QUOTE: Quote paragraph (detected via rules/patterns)
    - BODY: Regular body paragraph
    """
    TITLE = auto()      # Section title (bold + underlined)
    SUBHEADER = auto()  # Subheader (bold only, not underlined)
    BODY = auto()       # Body paragraph
    QUOTE = auto()      # Quote paragraph (detected via rules)


# =============================================================================
# Geometry Models
# =============================================================================


@dataclass(frozen=True)
class FrameGeometry:
    """
    Represents the geometric properties of a frame in the layout.
    
    All measurements are in points. This is an immutable value object
    that can be used as a dictionary key.
    
    Attributes:
        x: Left edge position from page origin
        y: Top edge position from page origin  
        width: Frame width
        height: Frame height
        
    Invariants:
        - width > 0
        - height > 0
        - x and y can be negative (for frames extending beyond page bounds)
    """
    x: float
    y: float
    width: float
    height: float
    
    def __post_init__(self):
        """Validate geometry invariants."""
        if self.width <= 0:
            raise ValueError(f"Width must be positive, got {self.width}")
        if self.height <= 0:
            raise ValueError(f"Height must be positive, got {self.height}")
    
    @property
    def right(self) -> float:
        """Right edge position (x + width)."""
        return self.x + self.width
    
    @property
    def bottom(self) -> float:
        """Bottom edge position (y + height)."""
        return self.y + self.height
    
    @property
    def center_x(self) -> float:
        """Horizontal center position."""
        return self.x + self.width / 2
    
    @property
    def center_y(self) -> float:
        """Vertical center position."""
        return self.y + self.height / 2
    
    def contains_point(self, px: float, py: float) -> bool:
        """Check if a point is inside this frame."""
        return self.x <= px <= self.right and self.y <= py <= self.bottom
    
    def intersects(self, other: FrameGeometry) -> bool:
        """Check if this frame intersects with another frame."""
        return not (
            self.right < other.x or
            other.right < self.x or
            self.bottom < other.y or
            other.bottom < self.y
        )
    
    def to_dict(self) -> Dict:
        """Serialize to dictionary for debugging/logging."""
        return {
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
        }


@dataclass(frozen=True)
class PageDimensions:
    """
    Page dimensions and margin information.
    
    Extracted from the reference IDML's document preferences and
    margin settings.
    
    Attributes:
        width: Total page width in points
        height: Total page height in points
        margin_top: Top margin in points
        margin_bottom: Bottom margin in points
        margin_inside: Inside margin (gutter) in points
        margin_outside: Outside margin in points
        column_count: Number of columns in the text area
        column_gutter: Space between columns in points
    """
    width: float
    height: float
    margin_top: float = 36.0       # 0.5 inch default
    margin_bottom: float = 36.0
    margin_inside: float = 36.0
    margin_outside: float = 36.0
    column_count: int = 2
    column_gutter: float = 12.0    # Standard gutter
    
    @property
    def content_width(self) -> float:
        """Width available for content (excluding margins)."""
        return self.width - self.margin_inside - self.margin_outside
    
    @property
    def content_height(self) -> float:
        """Height available for content (excluding margins)."""
        return self.height - self.margin_top - self.margin_bottom
    
    @property
    def column_width(self) -> float:
        """Width of a single column."""
        total_gutter = self.column_gutter * (self.column_count - 1)
        return (self.content_width - total_gutter) / self.column_count
    
    def get_column_x(self, column_index: int, is_left_page: bool = True) -> float:
        """
        Get the X position of a column's left edge.
        
        Args:
            column_index: 0-based column index
            is_left_page: True for left (even) pages, False for right (odd)
            
        Returns:
            X coordinate of column's left edge
        """
        if column_index < 0 or column_index >= self.column_count:
            raise ValueError(f"Column index {column_index} out of range [0, {self.column_count})")
        
        # Account for inside/outside margin swapping on facing pages
        left_margin = self.margin_inside if is_left_page else self.margin_outside
        
        return left_margin + column_index * (self.column_width + self.column_gutter)
    
    def to_dict(self) -> Dict:
        """Serialize to dictionary."""
        return {
            "width": self.width,
            "height": self.height,
            "margin_top": self.margin_top,
            "margin_bottom": self.margin_bottom,
            "margin_inside": self.margin_inside,
            "margin_outside": self.margin_outside,
            "column_count": self.column_count,
            "column_gutter": self.column_gutter,
        }


# =============================================================================
# Slot Models
# =============================================================================


@dataclass(frozen=True)
class Slot:
    """
    A positioned placeholder in the layout template.
    
    Slots are the atomic units of layout. Each slot represents a position
    where content can be placed. Slots are extracted from the reference
    IDML and define the available positions for content assignment.
    
    Attributes:
        slot_id: Unique identifier for this slot
        slot_type: What kind of content this slot accepts
        geometry: Position and size of the slot
        column_index: Which column this slot belongs to (0-based)
        vertical_position: Normalized vertical position (top/middle/bottom)
        paragraph_units: Size expressed in paragraph units (for sizing estimation)
        style_name: InDesign style applied to this slot's content
        is_fixed: If True, this slot cannot participate in variations
        group_id: ID for grouping interchangeable slots (None if not swappable)
        original_frame_id: The Self attribute from the original IDML frame
        spread_index: Index of the spread this slot is on (for ordering)
        
    Invariants:
        - slot_id is unique within a LayoutTemplate
        - column_index >= 0
        - paragraph_units > 0
        - group_id is shared only by compatible slots
    """
    slot_id: str
    slot_type: SlotType
    geometry: FrameGeometry
    column_index: int
    vertical_position: VerticalPosition
    paragraph_units: float = 1.0
    style_name: Optional[str] = None
    is_fixed: bool = False
    group_id: Optional[str] = None
    original_frame_id: Optional[str] = None
    spread_index: int = 0
    parent_story_id: Optional[str] = None  # For grouping threaded text frames
    
    def __post_init__(self):
        """Validate slot invariants."""
        if self.column_index < 0:
            raise ValueError(f"Column index must be non-negative, got {self.column_index}")
        if self.paragraph_units <= 0:
            raise ValueError(f"Paragraph units must be positive, got {self.paragraph_units}")
    
    def is_compatible_with(self, other: Slot) -> bool:
        """
        Check if this slot can be swapped with another slot.
        
        Two slots are compatible if:
        - They have the same slot_type
        - They have the same vertical_position
        - Neither is fixed
        - They have similar paragraph_units (within 20% tolerance)
        
        Note: This does NOT check group_id - that's for explicit grouping.
        """
        if self.is_fixed or other.is_fixed:
            return False
        if self.slot_type != other.slot_type:
            return False
        if self.vertical_position != other.vertical_position:
            return False
        
        # Check size compatibility (within 20% tolerance)
        size_ratio = self.paragraph_units / other.paragraph_units
        if size_ratio < 0.8 or size_ratio > 1.25:
            return False
        
        return True
    
    def with_geometry(self, new_geometry: FrameGeometry) -> Slot:
        """Create a copy of this slot with updated geometry."""
        return Slot(
            slot_id=self.slot_id,
            slot_type=self.slot_type,
            geometry=new_geometry,
            column_index=self.column_index,
            vertical_position=self.vertical_position,
            paragraph_units=self.paragraph_units,
            style_name=self.style_name,
            is_fixed=self.is_fixed,
            group_id=self.group_id,
            original_frame_id=self.original_frame_id,
        )
    
    def to_dict(self) -> Dict:
        """Serialize to dictionary."""
        return {
            "slot_id": self.slot_id,
            "slot_type": self.slot_type.name,
            "geometry": self.geometry.to_dict(),
            "column_index": self.column_index,
            "vertical_position": self.vertical_position.name,
            "paragraph_units": self.paragraph_units,
            "style_name": self.style_name,
            "is_fixed": self.is_fixed,
            "group_id": self.group_id,
            "original_frame_id": self.original_frame_id,
        }


# =============================================================================
# Layout Template
# =============================================================================


@dataclass
class LayoutTemplate:
    """
    The complete layout schema extracted from a reference IDML.
    
    A LayoutTemplate defines all available slots and their relationships.
    It is extracted once from the reference IDML and reused for all
    content assignments.
    
    Attributes:
        template_id: Unique identifier for this template
        page_dimensions: Page size and margin information
        slots: All slots in the template
        slot_groups: Mapping from group_id to sets of slot_ids
        source_idml_path: Path to the reference IDML (for provenance)
        
    Slot Organization:
        Slots are organized by:
        - Page (first page vs subsequent pages)
        - Column (0-based index)
        - Vertical position (top/middle/bottom)
        
        This organization enables efficient slot lookup and variation.
    """
    template_id: str
    page_dimensions: PageDimensions
    slots: List[Slot] = field(default_factory=list)
    slot_groups: Dict[str, Set[str]] = field(default_factory=dict)
    source_idml_path: Optional[str] = None
    
    # Cached indexes (built lazily)
    _slots_by_id: Optional[Dict[str, Slot]] = field(default=None, repr=False)
    _slots_by_type: Optional[Dict[SlotType, List[Slot]]] = field(default=None, repr=False)
    _slots_by_column: Optional[Dict[int, List[Slot]]] = field(default=None, repr=False)
    
    def __post_init__(self):
        """Build slot indexes."""
        self._rebuild_indexes()
    
    def _rebuild_indexes(self) -> None:
        """Rebuild all slot indexes. Call after modifying slots."""
        self._slots_by_id = {s.slot_id: s for s in self.slots}
        
        self._slots_by_type = {}
        for s in self.slots:
            if s.slot_type not in self._slots_by_type:
                self._slots_by_type[s.slot_type] = []
            self._slots_by_type[s.slot_type].append(s)
        
        self._slots_by_column = {}
        for s in self.slots:
            if s.column_index not in self._slots_by_column:
                self._slots_by_column[s.column_index] = []
            self._slots_by_column[s.column_index].append(s)
    
    def get_slot(self, slot_id: str) -> Optional[Slot]:
        """Get a slot by ID."""
        if self._slots_by_id is None:
            self._rebuild_indexes()
        return self._slots_by_id.get(slot_id)
    
    def get_slots_by_type(self, slot_type: SlotType) -> List[Slot]:
        """Get all slots of a given type."""
        if self._slots_by_type is None:
            self._rebuild_indexes()
        return self._slots_by_type.get(slot_type, [])
    
    def get_slots_by_column(self, column_index: int) -> List[Slot]:
        """Get all slots in a given column, sorted by Y position."""
        if self._slots_by_column is None:
            self._rebuild_indexes()
        slots = self._slots_by_column.get(column_index, [])
        return sorted(slots, key=lambda s: s.geometry.y)
    
    def get_interchangeable_slots(self, slot: Slot) -> List[Slot]:
        """
        Get all slots that can be swapped with the given slot.
        
        Returns slots that share the same group_id, or if no group_id,
        returns compatible slots based on type and position.
        """
        if slot.group_id:
            # Use explicit grouping
            group_slot_ids = self.slot_groups.get(slot.group_id, set())
            return [
                s for s in self.slots 
                if s.slot_id in group_slot_ids and s.slot_id != slot.slot_id
            ]
        else:
            # Fall back to compatibility check
            return [s for s in self.slots if s.is_compatible_with(slot)]
    
    def add_slot(self, slot: Slot) -> None:
        """Add a slot to the template."""
        self.slots.append(slot)
        
        # Update group mapping if slot has a group
        if slot.group_id:
            if slot.group_id not in self.slot_groups:
                self.slot_groups[slot.group_id] = set()
            self.slot_groups[slot.group_id].add(slot.slot_id)
        
        # Invalidate indexes
        self._slots_by_id = None
        self._slots_by_type = None
        self._slots_by_column = None
    
    def to_dict(self) -> Dict:
        """Serialize to dictionary."""
        return {
            "template_id": self.template_id,
            "page_dimensions": self.page_dimensions.to_dict(),
            "slots": [s.to_dict() for s in self.slots],
            "slot_groups": {k: list(v) for k, v in self.slot_groups.items()},
            "source_idml_path": self.source_idml_path,
        }
    
    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)


# =============================================================================
# Content Models
# =============================================================================


@dataclass
class ContentBlock:
    """
    A parsed content block from a Word document.
    
    Represents a single semantic unit of content (title, paragraph, or quote)
    that will be assigned to a slot during layout.
    
    Attributes:
        content_id: Unique identifier for this content block
        content_type: The semantic type of this content
        text: The actual text content
        section_title: The title of the section this block belongs to
        sequence_index: Order within the section (0 = title, 1+ = body/quotes)
        source_file: Path to the source Word document
        image_path: If this is an IMAGE type, path to the image file
        
    Invariants:
        - content_id is unique within a content set
        - sequence_index >= 0
        - text is not empty for text content types
        - image_path is set iff content_type is IMAGE (handled via ContentType)
    """
    content_id: str
    content_type: ContentType
    text: str
    section_title: str
    sequence_index: int
    source_file: Optional[str] = None
    image_path: Optional[str] = None
    
    # Estimated size in paragraph units (set during layout planning)
    estimated_paragraph_units: float = 1.0
    
    def __post_init__(self):
        """Validate content block invariants."""
        if self.sequence_index < 0:
            raise ValueError(f"Sequence index must be non-negative, got {self.sequence_index}")
        if not self.text and self.content_type != ContentType.BODY:
            # Allow empty body paragraphs for spacing, but not empty titles/quotes
            pass  # Relaxed validation - will be caught during layout
    
    def to_dict(self) -> Dict:
        """Serialize to dictionary."""
        return {
            "content_id": self.content_id,
            "content_type": self.content_type.name,
            "text": self.text[:100] + "..." if len(self.text) > 100 else self.text,
            "section_title": self.section_title,
            "sequence_index": self.sequence_index,
            "source_file": self.source_file,
            "image_path": self.image_path,
            "estimated_paragraph_units": self.estimated_paragraph_units,
        }


@dataclass
class ContentSection:
    """
    A complete content section parsed from a Word document.
    
    Represents all content from a single .docx file, organized into
    a title and body blocks with optional images.
    
    Attributes:
        section_id: Unique identifier for this section
        title: The section title (first paragraph of the document)
        body_blocks: List of body content blocks (paragraphs and quotes)
        image_paths: List of image paths associated with this section
        source_file: Path to the source Word document
    """
    section_id: str
    title: ContentBlock
    body_blocks: List[ContentBlock] = field(default_factory=list)
    image_paths: List[str] = field(default_factory=list)
    source_file: Optional[str] = None
    quote_count: int = 0  # Number of quote placeholders to generate
    
    def add_quote_placeholders(self, count: int, seed: Optional[int] = None) -> None:
        """
        Add placeholder quote blocks at random positions in the body.
        
        Quotes are distributed evenly throughout the body content,
        with some randomness for visual variety.
        
        Args:
            count: Number of quote placeholders to add
            seed: Random seed for reproducibility
        """
        import random
        rng = random.Random(seed)
        
        self.quote_count = count
        if count <= 0 or not self.body_blocks:
            return
        
        # Get positions of body paragraphs (not subheaders - insert after body text)
        body_indices = [
            i for i, block in enumerate(self.body_blocks) 
            if block.content_type == ContentType.BODY
        ]
        
        if not body_indices:
            # No body paragraphs, just append at end
            for i in range(count):
                self._add_single_quote(i, len(self.body_blocks))
            return
        
        # Choose positions spread across the body paragraphs
        # Divide body paragraphs into (count+1) sections and pick one from each section
        num_body = len(body_indices)
        insert_positions = []
        
        if count >= num_body:
            # More quotes than body paragraphs - distribute evenly
            for i in range(count):
                pos = body_indices[i % num_body] + 1
                insert_positions.append(pos)
        else:
            # Divide into sections and pick from each
            section_size = num_body / (count + 1)
            for i in range(count):
                # Target the middle of each section
                section_start = int((i + 1) * section_size) - 1
                section_start = max(0, min(section_start, num_body - 1))
                
                # Pick the body paragraph index
                body_idx = body_indices[section_start]
                # Insert AFTER this body paragraph
                insert_positions.append(body_idx + 1)
        
        # Sort positions in reverse order so insertions don't shift indices
        insert_positions.sort(reverse=True)
        
        # Insert quotes at calculated positions
        for i, pos in enumerate(insert_positions):
            quote_block = ContentBlock(
                content_id=f"{self.section_id}_quote_{count - 1 - i}",
                content_type=ContentType.QUOTE,
                text="Sample quote",
                section_title=self.title.text if self.title else "",
                sequence_index=pos,
                source_file=self.source_file,
            )
            self.body_blocks.insert(pos, quote_block)
    
    def _add_single_quote(self, index: int, position: int) -> None:
        """Add a single quote at the specified position."""
        quote_block = ContentBlock(
            content_id=f"{self.section_id}_quote_{index}",
            content_type=ContentType.QUOTE,
            text="Sample quote",
            section_title=self.title.text if self.title else "",
            sequence_index=position,
            source_file=self.source_file,
        )
        self.body_blocks.insert(position, quote_block)
    
    @property
    def all_blocks(self) -> List[ContentBlock]:
        """Get all content blocks including title."""
        return [self.title] + self.body_blocks
    
    def get_quotes(self) -> List[ContentBlock]:
        """Get all quote blocks in this section."""
        return [b for b in self.body_blocks if b.content_type == ContentType.QUOTE]
    
    def get_body_paragraphs(self) -> List[ContentBlock]:
        """Get all body, subheader, and quote blocks for the text flow."""
        return [b for b in self.body_blocks if b.content_type in (ContentType.BODY, ContentType.SUBHEADER, ContentType.QUOTE)]
    
    def to_dict(self) -> Dict:
        """Serialize to dictionary."""
        return {
            "section_id": self.section_id,
            "title": self.title.to_dict(),
            "body_blocks": [b.to_dict() for b in self.body_blocks],
            "image_paths": self.image_paths,
            "source_file": self.source_file,
        }


# =============================================================================
# Page Instance Models
# =============================================================================


@dataclass
class SlotAssignment:
    """
    Assignment of content block(s) to a slot.
    
    Represents the binding between content and layout position.
    A slot can receive multiple content blocks (for threaded stories).
    """
    slot: Slot
    content: ContentBlock = None  # Primary content block
    content_blocks: List[ContentBlock] = field(default_factory=list)  # All content blocks for this slot
    
    def __post_init__(self):
        """Ensure content_blocks is populated."""
        if self.content and not self.content_blocks:
            self.content_blocks = [self.content]
        elif self.content_blocks and not self.content:
            self.content = self.content_blocks[0] if self.content_blocks else None
    
    def add_content(self, content: ContentBlock) -> None:
        """Add a content block to this assignment."""
        self.content_blocks.append(content)
        if self.content is None:
            self.content = content
    
    def to_dict(self) -> Dict:
        """Serialize to dictionary."""
        return {
            "slot_id": self.slot.slot_id,
            "content_id": self.content.content_id if self.content else None,
            "content_count": len(self.content_blocks),
        }


@dataclass
class PageInstance:
    """
    A realized page with content assigned to slots.
    
    Represents a single page in the output document with all content
    assignments resolved.
    
    Attributes:
        page_id: Unique identifier for this page
        page_number: 1-based page number in the output
        spread_index: Which spread this page belongs to
        is_left_page: True for left (verso) pages, False for right (recto)
        assignments: List of slot-content assignments for this page
        
    Invariants:
        - page_number >= 1
        - Each slot appears at most once in assignments
        - All assigned slots must be compatible with their content types
    """
    page_id: str
    page_number: int
    spread_index: int
    is_left_page: bool
    assignments: List[SlotAssignment] = field(default_factory=list)
    
    def __post_init__(self):
        """Validate page instance invariants."""
        if self.page_number < 1:
            raise ValueError(f"Page number must be >= 1, got {self.page_number}")
    
    def add_assignment(self, slot: Slot, content: ContentBlock) -> None:
        """Add a slot-content assignment."""
        # Validate slot-content compatibility
        if slot.slot_type == SlotType.TITLE and content.content_type != ContentType.TITLE:
            raise ValueError(f"Cannot assign {content.content_type} to TITLE slot")
        if slot.slot_type == SlotType.QUOTE and content.content_type != ContentType.QUOTE:
            raise ValueError(f"Cannot assign {content.content_type} to QUOTE slot")
        
        self.assignments.append(SlotAssignment(slot=slot, content=content))
    
    def get_slots_used(self) -> Set[str]:
        """Get the set of slot IDs used on this page."""
        return {a.slot.slot_id for a in self.assignments}
    
    def to_dict(self) -> Dict:
        """Serialize to dictionary."""
        return {
            "page_id": self.page_id,
            "page_number": self.page_number,
            "spread_index": self.spread_index,
            "is_left_page": self.is_left_page,
            "assignments": [a.to_dict() for a in self.assignments],
        }


@dataclass
class DocumentLayout:
    """
    Complete layout plan for an output document.
    
    Contains all pages with their slot assignments, ready for
    IDML generation.
    
    Attributes:
        layout_id: Unique identifier for this layout
        template: The layout template used
        pages: All pages in document order
        variation_seed: The random seed used for variations
        metadata: Additional metadata about the layout
    """
    layout_id: str
    template: LayoutTemplate
    pages: List[PageInstance] = field(default_factory=list)
    variation_seed: Optional[int] = None
    metadata: Dict = field(default_factory=dict)
    
    @property
    def page_count(self) -> int:
        """Total number of pages."""
        return len(self.pages)
    
    @property
    def spread_count(self) -> int:
        """Total number of spreads."""
        if not self.pages:
            return 0
        return max(p.spread_index for p in self.pages) + 1
    
    def get_page(self, page_number: int) -> Optional[PageInstance]:
        """Get a page by its 1-based page number."""
        for page in self.pages:
            if page.page_number == page_number:
                return page
        return None
    
    def add_page(self, page: PageInstance) -> None:
        """Add a page to the document."""
        self.pages.append(page)
    
    def to_dict(self) -> Dict:
        """Serialize to dictionary."""
        return {
            "layout_id": self.layout_id,
            "template_id": self.template.template_id,
            "pages": [p.to_dict() for p in self.pages],
            "variation_seed": self.variation_seed,
            "metadata": self.metadata,
        }
    
    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)
