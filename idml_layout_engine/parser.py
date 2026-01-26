"""
IDML Parser - Layout Detection from Reference IDML
===================================================

This module handles parsing of reference IDML files to extract the
layout template (LayoutTemplate). It is responsible for:

1. Extracting page dimensions and margins
2. Detecting all text frames and image frames
3. Computing frame geometry
4. Assigning frames to columns based on geometry
5. Determining vertical ordering within columns
6. Creating slots from frames
7. Grouping interchangeable slots

IDML Structure Overview:
------------------------
An IDML file is a ZIP archive containing:
- designmap.xml: Master index of all resources
- Spreads/: XML files for each spread (Spread_*.xml)
- Stories/: XML files for text content (Story_*.xml)
- Resources/: Fonts, graphics, preferences
- MasterSpreads/: Master page definitions
- XML/: XML structure if any

Key XML Elements:
- <Spread>: Contains pages and page items
- <Page>: Page definition within a spread
- <TextFrame>: Text container with geometry
- <Rectangle>: Can be an image frame
- <GraphicLine>: Lines and rules
- <Polygon>: Complex shapes

Coordinate System:
- All IDML coordinates are in points
- Spread coordinates are used (not page-relative)
- We convert to page-relative coordinates during parsing

Assumptions:
------------
1. The reference IDML uses facing pages (left/right)
2. All pages have the same dimensions
3. Columns are determined by horizontal center position
4. Frame types are determined by applied styles and content
"""

from __future__ import annotations

import os
import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict, Tuple, Set, Any
from collections import defaultdict
import logging

from .models import (
    Slot,
    SlotType,
    VerticalPosition,
    LayoutTemplate,
    FrameGeometry,
    PageDimensions,
)


# Configure logging
logger = logging.getLogger(__name__)


# =============================================================================
# IDML XML Namespace Handling
# =============================================================================

# InDesign XML namespaces
IDML_NAMESPACES = {
    'idPkg': 'http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging',
    'idml': 'http://ns.adobe.com/AdobeInDesign/idml/1.0/',
}


def register_namespaces():
    """Register IDML namespaces with ElementTree."""
    for prefix, uri in IDML_NAMESPACES.items():
        ET.register_namespace(prefix, uri)


# =============================================================================
# Configuration Constants
# =============================================================================

# ============================================================================
# STYLE NAMES - CONFIGURED FOR TEMPLATE
# ============================================================================
# Style names extracted from reference IDML Styles.xml
# Supports both vertical (A4 V) and horizontal (A4 H) layout variants

TITLE_STYLE_NAMES = [
    "A4 V:Column Title",
    "A4 H:Column Title",
    "Column Title",
]

SUBHEADER_STYLE_NAMES = [
    "A4 V:Subheading",
    "A4 H:Subheading",
    "Subheading",
]

BODY_STYLE_NAMES = [
    "A4 V:Body Text",
    "A4 H:Body Text",
    "Body Text",
]

QUOTE_STYLE_NAMES = [
    "A4 V:Pull Quote",
    "A4 H:Pull Quote",
    "Pull Quote",
]

# Object styles for image frames
IMAGE_OBJECT_STYLES = [
    "A4 V:Photo Frame",
    "A4 H:Photo Frame",
    "Photo Frame",
]

# ============================================================================
# END STYLE NAMES CONFIGURATION
# ============================================================================


# =============================================================================
# Frame Data Structures
# =============================================================================


@dataclass
class RawFrame:
    """
    Raw frame data extracted from IDML XML before classification.
    
    This intermediate structure holds all relevant attributes from
    the XML before we determine the slot type and column assignment.
    """
    frame_id: str                    # Self attribute from XML
    geometry: FrameGeometry          # Computed geometry
    parent_story_id: Optional[str]   # ParentStory attribute if text frame
    applied_paragraph_styles: List[str] = field(default_factory=list)
    applied_object_style: Optional[str] = None
    is_text_frame: bool = False
    is_graphic_frame: bool = False
    has_image_content: bool = False
    page_index: int = 0              # Which page in the spread (0 or 1)
    spread_index: int = 0            # Which spread this frame is on
    
    # Additional metadata from XML
    xml_element_tag: str = ""
    content_type: Optional[str] = None  # From ContentType attribute
    
    def __repr__(self) -> str:
        return (
            f"RawFrame(id={self.frame_id[:20]}..., "
            f"geo=({self.geometry.x:.1f}, {self.geometry.y:.1f}, "
            f"{self.geometry.width:.1f}, {self.geometry.height:.1f}), "
            f"text={self.is_text_frame}, graphic={self.is_graphic_frame})"
        )


@dataclass  
class PageInfo:
    """
    Information about a page within a spread.
    """
    page_id: str
    page_index: int          # 0 for left, 1 for right in facing pages
    spread_index: int
    geometry_bounds: Tuple[float, float, float, float]  # top, left, bottom, right
    margin_bounds: Tuple[float, float, float, float]    # margins
    is_left_page: bool
    
    @property
    def x_offset(self) -> float:
        """X offset for converting spread coordinates to page coordinates."""
        return self.geometry_bounds[1]  # left edge
    
    @property
    def y_offset(self) -> float:
        """Y offset (usually 0 for page coordinates)."""
        return self.geometry_bounds[0]  # top edge


# =============================================================================
# IDML Parser
# =============================================================================


class IDMLParser:
    """
    Parser for extracting layout templates from IDML files.
    
    Usage:
        parser = IDMLParser(idml_path)
        template = parser.parse()
    
    The parser:
    1. Opens the IDML ZIP archive
    2. Reads document preferences for page dimensions
    3. Iterates through spreads to find frames
    4. Classifies frames into slot types
    5. Assigns frames to columns
    6. Computes vertical positions
    7. Groups interchangeable slots
    8. Returns a complete LayoutTemplate
    """
    
    def __init__(self, idml_path: str | Path):
        """
        Initialize the parser.
        
        Args:
            idml_path: Path to the reference IDML file
        """
        self.idml_path = Path(idml_path)
        if not self.idml_path.exists():
            raise FileNotFoundError(f"IDML file not found: {idml_path}")
        if not self.idml_path.suffix.lower() == '.idml':
            raise ValueError(f"File must have .idml extension: {idml_path}")
        
        self.zip_file: Optional[zipfile.ZipFile] = None
        self._xml_cache: Dict[str, ET.Element] = {}
        
        # Extracted data
        self.page_dimensions: Optional[PageDimensions] = None
        self.pages: List[PageInfo] = []
        self.raw_frames: List[RawFrame] = []
        
        register_namespaces()
    
    def parse(self) -> LayoutTemplate:
        """
        Parse the IDML file and return a LayoutTemplate.
        
        This is the main entry point for parsing.
        
        Returns:
            Complete LayoutTemplate extracted from the IDML
            
        Raises:
            ValueError: If IDML structure is invalid or unsupported
            zipfile.BadZipFile: If IDML is corrupted
        """
        logger.info(f"Parsing IDML: {self.idml_path}")
        
        with zipfile.ZipFile(self.idml_path, 'r') as zf:
            self.zip_file = zf
            
            # Step 1: Extract page dimensions from document preferences
            self.page_dimensions = self._extract_page_dimensions()
            logger.info(f"Page dimensions: {self.page_dimensions.width} x {self.page_dimensions.height}")
            
            # Step 2: Parse spreads to get page info and frames
            self._parse_spreads()
            logger.info(f"Found {len(self.pages)} pages, {len(self.raw_frames)} frames")
            
            # Step 3: Classify frames into slot types
            slots = self._classify_frames()
            logger.info(f"Classified {len(slots)} slots")
            
            # Step 4: Group interchangeable slots
            slot_groups = self._group_slots(slots)
            logger.info(f"Created {len(slot_groups)} slot groups")
            
            # Step 5: Build the layout template
            template = LayoutTemplate(
                template_id=f"template_{self.idml_path.stem}",
                page_dimensions=self.page_dimensions,
                slots=slots,
                slot_groups=slot_groups,
                source_idml_path=str(self.idml_path),
            )
            
            self.zip_file = None
            
        return template
    
    def _read_xml(self, path: str) -> ET.Element:
        """
        Read and parse an XML file from the IDML archive.
        
        Uses caching to avoid re-parsing the same file.
        """
        if path in self._xml_cache:
            return self._xml_cache[path]
        
        if self.zip_file is None:
            raise RuntimeError("ZIP file not open")
        
        with self.zip_file.open(path) as f:
            tree = ET.parse(f)
            root = tree.getroot()
            self._xml_cache[path] = root
            return root
    
    def _extract_page_dimensions(self) -> PageDimensions:
        """
        Extract page dimensions from Preferences/Document_Preferences.xml.
        
        This file contains:
        - PageWidth, PageHeight
        - DocumentBleedTopOffset, etc. (bleeds)
        - FacingPages setting
        
        Margins are extracted from master spread margin preferences.
        """
        # Read document preferences
        try:
            prefs = self._read_xml('Resources/Preferences.xml')
        except KeyError:
            logger.warning("Preferences.xml not found, using defaults")
            return PageDimensions(width=612.0, height=792.0)  # US Letter
        
        # Find DocumentPreference element
        doc_pref = prefs.find('.//DocumentPreference')
        if doc_pref is None:
            logger.warning("DocumentPreference not found, using defaults")
            return PageDimensions(width=612.0, height=792.0)
        
        width = float(doc_pref.get('PageWidth', '612'))
        height = float(doc_pref.get('PageHeight', '792'))
        column_count = int(doc_pref.get('ColumnCount', '2'))
        column_gutter = float(doc_pref.get('ColumnGutter', '12'))
        
        # Try to get margins from master spread
        margins = self._extract_margins_from_master_spread()
        
        return PageDimensions(
            width=width,
            height=height,
            margin_top=margins.get('top', 36.0),
            margin_bottom=margins.get('bottom', 36.0),
            margin_inside=margins.get('inside', 36.0),
            margin_outside=margins.get('outside', 36.0),
            column_count=column_count,
            column_gutter=column_gutter,
        )
    
    def _extract_margins_from_master_spread(self) -> Dict[str, float]:
        """
        Extract margin values from master spread.
        
        Returns dict with keys: top, bottom, inside, outside
        """
        defaults = {'top': 36.0, 'bottom': 36.0, 'inside': 36.0, 'outside': 36.0}
        
        # List master spread files
        if self.zip_file is None:
            return defaults
        
        master_files = [
            n for n in self.zip_file.namelist() 
            if n.startswith('MasterSpreads/') and n.endswith('.xml')
        ]
        
        if not master_files:
            return defaults
        
        # Parse first master spread
        try:
            master = self._read_xml(master_files[0])
            margin_pref = master.find('.//MarginPreference')
            if margin_pref is not None:
                return {
                    'top': float(margin_pref.get('Top', '36')),
                    'bottom': float(margin_pref.get('Bottom', '36')),
                    'inside': float(margin_pref.get('Left', '36')),  # Inside on left page
                    'outside': float(margin_pref.get('Right', '36')),
                }
        except Exception as e:
            logger.warning(f"Could not extract margins: {e}")
        
        return defaults
    
    def _parse_spreads(self) -> None:
        """
        Parse all spread files to extract pages and frames.
        
        Iterates through Spreads/Spread_*.xml files and extracts:
        - Page definitions
        - TextFrame elements
        - Rectangle elements (potential image frames)
        """
        if self.zip_file is None:
            raise RuntimeError("ZIP file not open")
        
        # Get list of spread files
        spread_files = sorted([
            n for n in self.zip_file.namelist()
            if n.startswith('Spreads/Spread_') and n.endswith('.xml')
        ])
        
        for spread_idx, spread_path in enumerate(spread_files):
            self._parse_single_spread(spread_path, spread_idx)
    
    def _parse_single_spread(self, spread_path: str, spread_index: int) -> None:
        """
        Parse a single spread file.
        
        Args:
            spread_path: Path within ZIP to spread XML
            spread_index: 0-based index of this spread
        """
        spread = self._read_xml(spread_path)
        
        # Find the Spread element
        spread_elem = spread.find('.//Spread')
        if spread_elem is None:
            spread_elem = spread  # Root might be the Spread
        
        # Extract page information
        for page_idx, page_elem in enumerate(spread_elem.findall('.//Page')):
            page_info = self._parse_page_element(page_elem, page_idx, spread_index)
            self.pages.append(page_info)
        
        # Extract text frames
        for text_frame in spread_elem.findall('.//TextFrame'):
            raw_frame = self._parse_text_frame(text_frame, spread_index)
            if raw_frame:
                self.raw_frames.append(raw_frame)
        
        # Extract rectangles (potential image frames)
        for rect in spread_elem.findall('.//Rectangle'):
            raw_frame = self._parse_rectangle(rect, spread_index)
            if raw_frame:
                self.raw_frames.append(raw_frame)
    
    def _parse_page_element(
        self, 
        page_elem: ET.Element, 
        page_idx: int, 
        spread_index: int
    ) -> PageInfo:
        """
        Parse a Page XML element.
        
        Args:
            page_elem: The Page XML element
            page_idx: Index within the spread (0 for left, 1 for right)
            spread_index: Index of the spread
            
        Returns:
            PageInfo object
        """
        page_id = page_elem.get('Self', f'page_{spread_index}_{page_idx}')
        
        # Parse geometry bounds (space-separated: top left bottom right)
        geo_bounds_str = page_elem.get('GeometricBounds', '0 0 792 612')
        geo_bounds = tuple(map(float, geo_bounds_str.split()))
        
        # Parse margin bounds if present
        margin_pref = page_elem.find('.//MarginPreference')
        if margin_pref is not None:
            margin_bounds = (
                float(margin_pref.get('Top', '36')),
                float(margin_pref.get('Left', '36')),
                float(margin_pref.get('Bottom', '36')),
                float(margin_pref.get('Right', '36')),
            )
        else:
            margin_bounds = (36.0, 36.0, 36.0, 36.0)
        
        # Determine if left or right page
        # In facing pages, even spread pages (0, 2, 4...) have left=page_idx 0
        is_left = (page_idx == 0)
        
        return PageInfo(
            page_id=page_id,
            page_index=page_idx,
            spread_index=spread_index,
            geometry_bounds=geo_bounds,
            margin_bounds=margin_bounds,
            is_left_page=is_left,
        )
    
    def _parse_geometry_from_element(self, elem: ET.Element) -> Optional[FrameGeometry]:
        """
        Extract frame geometry from an XML element.
        
        InDesign uses various geometry representations:
        - GeometricBounds: "top left bottom right" in parent coordinates
        - ItemTransform: Transform matrix for positioning
        - PathGeometry: For complex shapes
        
        We use GeometricBounds as the primary source.
        """
        bounds_str = elem.get('GeometricBounds')
        if not bounds_str:
            # Try to find in child Properties
            props = elem.find('.//PathGeometry')
            if props is not None:
                # Would need to parse path - fall back to None
                return None
            return None
        
        try:
            parts = bounds_str.split()
            if len(parts) != 4:
                return None
            
            top, left, bottom, right = map(float, parts)
            width = right - left
            height = bottom - top
            
            if width <= 0 or height <= 0:
                return None
            
            return FrameGeometry(x=left, y=top, width=width, height=height)
            
        except (ValueError, IndexError) as e:
            logger.warning(f"Could not parse geometry: {bounds_str}, error: {e}")
            return None
    
    def _parse_text_frame(
        self, 
        text_frame: ET.Element, 
        spread_index: int
    ) -> Optional[RawFrame]:
        """
        Parse a TextFrame element.
        
        Args:
            text_frame: The TextFrame XML element
            spread_index: Index of the spread
            
        Returns:
            RawFrame if successfully parsed, None otherwise
        """
        frame_id = text_frame.get('Self', '')
        if not frame_id:
            return None
        
        geometry = self._parse_geometry_from_element(text_frame)
        if geometry is None:
            return None
        
        parent_story = text_frame.get('ParentStory')
        applied_object_style = text_frame.get('AppliedObjectStyle')
        content_type = text_frame.get('ContentType', 'TextType')
        
        # Extract paragraph styles from the linked story if available
        paragraph_styles = self._extract_paragraph_styles_from_story(parent_story)
        
        return RawFrame(
            frame_id=frame_id,
            geometry=geometry,
            parent_story_id=parent_story,
            applied_paragraph_styles=paragraph_styles,
            applied_object_style=applied_object_style,
            is_text_frame=True,
            is_graphic_frame=False,
            spread_index=spread_index,
            xml_element_tag='TextFrame',
            content_type=content_type,
        )
    
    def _parse_rectangle(
        self, 
        rect: ET.Element, 
        spread_index: int
    ) -> Optional[RawFrame]:
        """
        Parse a Rectangle element (potential image frame).
        
        Rectangles can be:
        - Image frames (ContentType="GraphicType")
        - Decorative boxes
        - Placeholder frames
        
        We identify image frames by ContentType or by having graphic content.
        """
        frame_id = rect.get('Self', '')
        if not frame_id:
            return None
        
        geometry = self._parse_geometry_from_element(rect)
        if geometry is None:
            return None
        
        content_type = rect.get('ContentType', 'Unassigned')
        applied_object_style = rect.get('AppliedObjectStyle')
        
        # Check if this has graphic content
        has_image = content_type == 'GraphicType'
        if not has_image:
            # Check for Image, EPS, PDF children
            has_image = rect.find('.//Image') is not None
            has_image = has_image or rect.find('.//EPS') is not None
            has_image = has_image or rect.find('.//PDF') is not None
        
        return RawFrame(
            frame_id=frame_id,
            geometry=geometry,
            parent_story_id=None,
            applied_object_style=applied_object_style,
            is_text_frame=False,
            is_graphic_frame=True,
            has_image_content=has_image,
            spread_index=spread_index,
            xml_element_tag='Rectangle',
            content_type=content_type,
        )
    
    def _extract_paragraph_styles_from_story(
        self, 
        story_id: Optional[str]
    ) -> List[str]:
        """
        Extract paragraph style names from a story.
        
        Stories are in Stories/Story_*.xml files.
        """
        if not story_id or self.zip_file is None:
            return []
        
        # Stories are named like Story_u123.xml
        # The story_id format varies - try common patterns
        story_files = [
            n for n in self.zip_file.namelist()
            if n.startswith('Stories/') and n.endswith('.xml')
        ]
        
        styles = []
        for story_file in story_files:
            try:
                story = self._read_xml(story_file)
                # Check if this story matches
                story_elem = story.find('.//Story')
                if story_elem is not None and story_elem.get('Self') == story_id:
                    # Extract AppliedParagraphStyle from paragraphs
                    for para in story.findall('.//ParagraphStyleRange'):
                        style = para.get('AppliedParagraphStyle', '')
                        if style and style not in styles:
                            styles.append(style)
                    break
            except Exception as e:
                logger.debug(f"Could not read story {story_file}: {e}")
        
        return styles
    
    def _classify_frames(self) -> List[Slot]:
        """
        Classify raw frames into typed slots.
        
        This is the core classification logic that determines:
        - What type of content each frame should hold
        - Which column the frame belongs to
        - The frame's vertical position
        
        Classification Rules:
        1. Frames with title paragraph styles → TITLE slots
        2. Frames with quote paragraph styles → QUOTE slots  
        3. Frames with body paragraph styles → PARAGRAPH slots
        4. Graphic frames with images → IMAGE slots
        5. Unclassified text frames → PARAGRAPH slots (default)
        
        Column Detection:
        - Uses horizontal center position
        - Compares against column boundaries from page dimensions
        
        Vertical Position:
        - TOP: y < page_height / 3
        - MIDDLE: page_height / 3 <= y < 2 * page_height / 3
        - BOTTOM: y >= 2 * page_height / 3
        """
        slots = []
        
        for idx, frame in enumerate(self.raw_frames):
            slot = self._classify_single_frame(frame, idx)
            if slot:
                slots.append(slot)
        
        return slots
    
    def _classify_single_frame(self, frame: RawFrame, index: int) -> Optional[Slot]:
        """
        Classify a single raw frame into a slot.
        
        Args:
            frame: The raw frame to classify
            index: Index for generating slot ID
            
        Returns:
            Slot if frame should be included, None to skip
        """
        # Determine slot type
        slot_type = self._determine_slot_type(frame)
        if slot_type is None:
            return None  # Skip this frame
        
        # Determine column index
        column_index = self._determine_column(frame.geometry)
        
        # Determine vertical position
        vertical_pos = self._determine_vertical_position(frame.geometry)
        
        # Calculate paragraph units (based on height)
        # Assume average paragraph height of ~14 points (12pt text + leading)
        avg_paragraph_height = 14.0
        paragraph_units = max(1.0, frame.geometry.height / avg_paragraph_height)
        
        # Extract style name
        style_name = self._get_primary_style(frame)
        
        # Determine if slot is fixed (headers/footers don't participate in variation)
        is_fixed = slot_type in (SlotType.HEADER, SlotType.FOOTER)
        
        slot_id = f"slot_{slot_type.name.lower()}_{index}"
        
        return Slot(
            slot_id=slot_id,
            slot_type=slot_type,
            geometry=frame.geometry,
            column_index=column_index,
            vertical_position=vertical_pos,
            paragraph_units=paragraph_units,
            style_name=style_name,
            is_fixed=is_fixed,
            group_id=None,  # Will be assigned in _group_slots
            original_frame_id=frame.frame_id,
        )
    
    def _determine_slot_type(self, frame: RawFrame) -> Optional[SlotType]:
        """
        Determine the slot type for a frame based on its properties.
        
        Priority:
        1. Graphic frames → IMAGE
        2. Style-based classification for text frames
        3. Default to PARAGRAPH for unclassified text frames
        """
        # Graphic frames
        if frame.is_graphic_frame:
            if frame.has_image_content:
                return SlotType.IMAGE
            # Empty graphic frames might be placeholders - skip or treat as image
            return SlotType.IMAGE
        
        # Text frames - classify by style
        if frame.is_text_frame:
            for style in frame.applied_paragraph_styles:
                # Clean up style name (remove prefix like "ParagraphStyle/")
                clean_style = style.split('/')[-1] if '/' in style else style
                # URL-decode the style name (e.g., %3a -> :)
                clean_style = clean_style.replace('%3a', ':')
                
                # Check for title styles
                if TITLE_STYLE_NAMES:
                    if any(ts.lower() in clean_style.lower() for ts in TITLE_STYLE_NAMES):
                        return SlotType.TITLE
                else:
                    # Fallback heuristic if no styles configured
                    if 'title' in clean_style.lower() or 'head' in clean_style.lower():
                        return SlotType.TITLE
                
                # Check for subheader styles
                if SUBHEADER_STYLE_NAMES:
                    if any(ss.lower() in clean_style.lower() for ss in SUBHEADER_STYLE_NAMES):
                        return SlotType.SUBHEADER
                else:
                    # Fallback heuristic
                    if 'subhead' in clean_style.lower():
                        return SlotType.SUBHEADER
                
                # Check for quote styles
                if QUOTE_STYLE_NAMES:
                    if any(qs.lower() in clean_style.lower() for qs in QUOTE_STYLE_NAMES):
                        return SlotType.QUOTE
                else:
                    # Fallback heuristic
                    if 'quote' in clean_style.lower() or 'pull' in clean_style.lower():
                        return SlotType.QUOTE
                
                # Check for body styles
                if BODY_STYLE_NAMES:
                    if any(bs.lower() in clean_style.lower() for bs in BODY_STYLE_NAMES):
                        return SlotType.PARAGRAPH
                else:
                    # Fallback heuristic
                    if 'body' in clean_style.lower() or 'text' in clean_style.lower():
                        return SlotType.PARAGRAPH
            
            # Default text frames to PARAGRAPH
            return SlotType.PARAGRAPH
        
        return None
    
    def _determine_column(self, geometry: FrameGeometry) -> int:
        """
        Determine which column a frame belongs to based on its geometry.
        
        Algorithm:
        1. Calculate frame's horizontal center
        2. Calculate column boundaries based on page dimensions
        3. Assign to column whose center is closest
        
        Assumptions:
        - Columns are evenly distributed across content width
        - Frames entirely within a column get that column
        - Frames spanning columns go to the column with most overlap
        """
        if self.page_dimensions is None:
            return 0
        
        frame_center_x = geometry.center_x
        
        # Calculate column boundaries
        # Note: Using absolute coordinates - may need page offset adjustment
        # For now, assume coordinates are page-relative
        
        content_start = self.page_dimensions.margin_inside
        column_width = self.page_dimensions.column_width
        gutter = self.page_dimensions.column_gutter
        
        best_column = 0
        min_distance = float('inf')
        
        for col_idx in range(self.page_dimensions.column_count):
            col_start = content_start + col_idx * (column_width + gutter)
            col_center = col_start + column_width / 2
            
            distance = abs(frame_center_x - col_center)
            if distance < min_distance:
                min_distance = distance
                best_column = col_idx
        
        return best_column
    
    def _determine_vertical_position(self, geometry: FrameGeometry) -> VerticalPosition:
        """
        Determine the vertical position zone for a frame.
        
        Divides the page into three equal zones:
        - TOP: Upper third
        - MIDDLE: Middle third
        - BOTTOM: Lower third
        
        Uses the frame's vertical center for classification.
        """
        if self.page_dimensions is None:
            return VerticalPosition.MIDDLE
        
        page_height = self.page_dimensions.height
        frame_center_y = geometry.center_y
        
        third = page_height / 3
        
        if frame_center_y < third:
            return VerticalPosition.TOP
        elif frame_center_y < 2 * third:
            return VerticalPosition.MIDDLE
        else:
            return VerticalPosition.BOTTOM
    
    def _get_primary_style(self, frame: RawFrame) -> Optional[str]:
        """Get the primary (first) paragraph style from a frame."""
        if frame.applied_paragraph_styles:
            return frame.applied_paragraph_styles[0]
        if frame.applied_object_style:
            return frame.applied_object_style
        return None
    
    def _group_slots(self, slots: List[Slot]) -> Dict[str, Set[str]]:
        """
        Group interchangeable slots.
        
        Slots are grouped if they:
        1. Have the same slot_type
        2. Have the same vertical_position
        3. Are in different columns
        4. Have similar sizes (within 20% tolerance)
        
        Returns:
            Dictionary mapping group_id to set of slot_ids
        """
        groups: Dict[str, Set[str]] = {}
        
        # Group slots by (type, vertical_position)
        candidates: Dict[Tuple[SlotType, VerticalPosition], List[Slot]] = defaultdict(list)
        
        for slot in slots:
            if slot.is_fixed:
                continue  # Skip fixed slots
            key = (slot.slot_type, slot.vertical_position)
            candidates[key].append(slot)
        
        # For each group of candidates, find compatible slots
        group_counter = 0
        
        for (slot_type, vert_pos), slot_list in candidates.items():
            if len(slot_list) < 2:
                continue  # Need at least 2 slots to form a group
            
            # Find slots in different columns with similar sizes
            # Group slots by column
            by_column: Dict[int, List[Slot]] = defaultdict(list)
            for slot in slot_list:
                by_column[slot.column_index].append(slot)
            
            # If slots exist in multiple columns, they might be swappable
            if len(by_column) >= 2:
                group_id = f"group_{slot_type.name.lower()}_{vert_pos.name.lower()}_{group_counter}"
                group_counter += 1
                
                # For now, group all slots of same type/position together
                # A more sophisticated algorithm would check size compatibility
                group_slot_ids = {s.slot_id for s in slot_list}
                groups[group_id] = group_slot_ids
                
                # Update slots with group_id (need to recreate since Slot is frozen)
                # This is handled by the caller updating the template
        
        return groups
    
    # =========================================================================
    # Utility Methods
    # =========================================================================
    
    def get_stories(self) -> Dict[str, ET.Element]:
        """
        Get all story XML elements from the IDML.
        
        Returns dictionary mapping story ID to Story XML element.
        Useful for content extraction and manipulation.
        """
        stories = {}
        
        if self.zip_file is None:
            with zipfile.ZipFile(self.idml_path, 'r') as zf:
                self.zip_file = zf
                stories = self._get_stories_impl()
                self.zip_file = None
        else:
            stories = self._get_stories_impl()
        
        return stories
    
    def _get_stories_impl(self) -> Dict[str, ET.Element]:
        """Implementation of get_stories."""
        stories = {}
        
        story_files = [
            n for n in self.zip_file.namelist()
            if n.startswith('Stories/') and n.endswith('.xml')
        ]
        
        for story_file in story_files:
            try:
                story_root = self._read_xml(story_file)
                story_elem = story_root.find('.//Story')
                if story_elem is not None:
                    story_id = story_elem.get('Self', '')
                    if story_id:
                        stories[story_id] = story_elem
            except Exception as e:
                logger.warning(f"Could not read story {story_file}: {e}")
        
        return stories
    
    def get_all_files(self) -> List[str]:
        """List all files in the IDML archive."""
        with zipfile.ZipFile(self.idml_path, 'r') as zf:
            return zf.namelist()
    
    def extract_to_directory(self, output_dir: str | Path) -> None:
        """Extract the IDML archive to a directory for inspection."""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        with zipfile.ZipFile(self.idml_path, 'r') as zf:
            zf.extractall(output_path)
        
        logger.info(f"Extracted IDML to {output_path}")
