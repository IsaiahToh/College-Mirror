"""
IDML Generator - Mechanical IDML Production
============================================

This module generates valid IDML files from layout templates and
content assignments. All XML generation is mechanical - no AI or
heuristic XML generation.

IDML Structure (What We Generate):
- designmap.xml: Master index pointing to all resources
- Spreads/Spread_*.xml: Spread definitions with frames
- Stories/Story_*.xml: Text content for each story
- Resources/: Fonts, graphics, styles (copied from reference)
- MasterSpreads/: Master page definitions (copied from reference)
- META-INF/container.xml: Standard container metadata
- mimetype: MIME type declaration

Generation Strategy:
1. Clone the reference IDML structure
2. Replace story content with new text
3. Update frame geometries based on slot assignments
4. Replace image links in graphic frames
5. Add pages as needed for overflow
6. Write valid ZIP with proper structure

Critical Requirements:
- Output must open correctly in InDesign
- Preserve all styles and formatting from reference
- Maintain XML structure validity
- Handle Unicode text correctly
"""

from __future__ import annotations

import os
import re
import shutil
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict, Tuple, Set, Any
from copy import deepcopy
import tempfile
import logging
from collections import defaultdict

from .models import (
    Slot,
    SlotType,
    LayoutTemplate,
    ContentBlock,
    ContentSection,
    SlotAssignment,
    PageInstance,
    DocumentLayout,
    FrameGeometry,
)


logger = logging.getLogger(__name__)


# =============================================================================
# XML Namespace Registration
# =============================================================================

# IDML uses a default namespace
IDML_NS = "http://ns.adobe.com/AdobeInDesign/idml/1.0/"
IDPKG_NS = "http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging"

# Register namespaces to preserve prefixes
ET.register_namespace('', IDML_NS)
ET.register_namespace('idPkg', IDPKG_NS)


# =============================================================================
# Helper Functions
# =============================================================================


def escape_xml_text(text: str) -> str:
    """
    Escape text for XML content.
    
    Handles special characters that need escaping in XML text nodes.
    """
    # Basic XML escaping
    text = text.replace('&', '&amp;')
    text = text.replace('<', '&lt;')
    text = text.replace('>', '&gt;')
    return text


def create_paragraph_element(
    text: str,
    paragraph_style: str = "ParagraphStyle/$ID/NormalParagraphStyle",
    character_style: str = "CharacterStyle/$ID/[No character style]",
) -> ET.Element:
    """
    Create a ParagraphStyleRange element with content.
    
    This is the standard way to add text content to a Story in IDML.
    
    Structure:
        <ParagraphStyleRange AppliedParagraphStyle="...">
            <CharacterStyleRange AppliedCharacterStyle="...">
                <Content>Text here</Content>
            </CharacterStyleRange>
        </ParagraphStyleRange>
    
    Args:
        text: The text content to include
        paragraph_style: Applied paragraph style reference
        character_style: Applied character style reference
        
    Returns:
        ET.Element for the ParagraphStyleRange
    """
    para_elem = ET.Element('ParagraphStyleRange')
    para_elem.set('AppliedParagraphStyle', paragraph_style)
    
    char_elem = ET.SubElement(para_elem, 'CharacterStyleRange')
    char_elem.set('AppliedCharacterStyle', character_style)
    
    content = ET.SubElement(char_elem, 'Content')
    content.text = text
    
    return para_elem


def create_break_element(break_type: str = "Br") -> ET.Element:
    """
    Create a break element (paragraph break, column break, etc.)
    
    Args:
        break_type: Type of break - "Br" for paragraph/line break
        
    Returns:
        ET.Element for the break
    """
    return ET.Element(break_type)


# =============================================================================
# Story Builder
# =============================================================================


class StoryBuilder:
    """
    Builds Story XML elements from content blocks.
    
    A Story in IDML represents a thread of text that can flow through
    multiple text frames. Each Story has:
    - A unique Self ID
    - ParagraphStyleRange elements for styled paragraphs
    - Content elements with actual text
    
    Usage:
        builder = StoryBuilder(story_id="uc1")
        story_elem = builder.build_story([
            ContentBlock(...),
            ContentBlock(...),
        ])
    """
    
    def __init__(
        self,
        story_id: str,
        default_paragraph_style: str = "ParagraphStyle/$ID/NormalParagraphStyle",
        default_character_style: str = "CharacterStyle/$ID/[No character style]",
    ):
        """
        Initialize the story builder.
        
        Args:
            story_id: Unique ID for this story (e.g., "u123")
            default_paragraph_style: Default paragraph style to apply
            default_character_style: Default character style to apply
        """
        self.story_id = story_id
        self.default_paragraph_style = default_paragraph_style
        self.default_character_style = default_character_style
        
        # Style mappings (content type -> style)
        # Using actual style names from reference IDML template
        # Note: %3a is URL-encoded colon (:) used in InDesign style references
        self.style_map = {
            ContentType.TITLE: "ParagraphStyle/A4 V%3aColumn Title",
            ContentType.SUBHEADER: "ParagraphStyle/A4 V%3aSubheading",
            ContentType.BODY: "ParagraphStyle/A4 V%3aBody Text",
            ContentType.QUOTE: "ParagraphStyle/A4 V%3aPull Quote",
        }
    
    def set_style_mapping(
        self,
        content_type: "ContentType",
        paragraph_style: str,
    ) -> None:
        """Set the paragraph style for a content type."""
        from .models import ContentType
        self.style_map[content_type] = paragraph_style
    
    def build_story(
        self,
        content_blocks: List[ContentBlock],
    ) -> ET.Element:
        """
        Build a Story XML element from content blocks.
        
        Args:
            content_blocks: List of content blocks to include
            
        Returns:
            ET.Element representing the complete Story
        """
        from .models import ContentType
        
        # Create Story root element
        story = ET.Element('Story')
        story.set('Self', self.story_id)
        story.set('AppliedTOCStyle', 'n')
        story.set('TrackChanges', 'false')
        story.set('StoryTitle', '$ID/')
        story.set('AppliedNamedGrid', 'n')
        
        # Add story preference (required)
        story_prefs = ET.SubElement(story, 'StoryPreference')
        story_prefs.set('OpticalMarginAlignment', 'false')
        story_prefs.set('OpticalMarginSize', '12')
        story_prefs.set('FrameType', 'TextFrameType')
        story_prefs.set('StoryOrientation', 'Horizontal')
        story_prefs.set('StoryDirection', 'LeftToRightDirection')
        
        # Add inCopy export options (required for compatibility)
        incopy = ET.SubElement(story, 'InCopyExportOption')
        incopy.set('IncludeGraphicProxies', 'true')
        incopy.set('IncludeAllResources', 'false')
        
        # Add content paragraphs
        for idx, block in enumerate(content_blocks):
            para_style = self.style_map.get(block.content_type, self.default_paragraph_style)
            
            para_elem = create_paragraph_element(
                text=block.text,
                paragraph_style=para_style,
                character_style=self.default_character_style,
            )
            story.append(para_elem)
            
            # Add paragraph break after each paragraph (except last)
            if idx < len(content_blocks) - 1:
                # Add a Content element with the paragraph break character
                # In IDML, this is typically represented by a new line in Content
                # or by having separate ParagraphStyleRange elements
                pass  # Separate ParagraphStyleRange elements naturally create breaks
        
        return story
    
    def build_empty_story(self) -> ET.Element:
        """Build an empty story (placeholder)."""
        story = ET.Element('Story')
        story.set('Self', self.story_id)
        story.set('AppliedTOCStyle', 'n')
        story.set('TrackChanges', 'false')
        story.set('StoryTitle', '$ID/')
        story.set('AppliedNamedGrid', 'n')
        
        story_prefs = ET.SubElement(story, 'StoryPreference')
        story_prefs.set('OpticalMarginAlignment', 'false')
        story_prefs.set('OpticalMarginSize', '12')
        story_prefs.set('FrameType', 'TextFrameType')
        story_prefs.set('StoryOrientation', 'Horizontal')
        story_prefs.set('StoryDirection', 'LeftToRightDirection')
        
        return story


# =============================================================================
# IDML Generator
# =============================================================================


class IDMLGenerator:
    """
    Generates IDML files from layout templates and content.
    
    The generator:
    1. Reads the reference IDML as a template
    2. Clones the structure
    3. Replaces text content in stories
    4. Updates frame geometries
    5. Replaces image links
    6. Writes a valid IDML ZIP
    
    Usage:
        generator = IDMLGenerator(reference_idml="template.idml")
        generator.generate(
            output_path="output.idml",
            layout=document_layout,
            assignments=slot_assignments,
            image_mapping={"title": "image.jpg"},
        )
    """
    
    def __init__(self, reference_idml: str | Path):
        """
        Initialize the generator with a reference IDML.
        
        Args:
            reference_idml: Path to the reference IDML file
        """
        self.reference_path = Path(reference_idml)
        if not self.reference_path.exists():
            raise FileNotFoundError(f"Reference IDML not found: {reference_idml}")
        
        self.temp_dir: Optional[Path] = None
        self._extracted_files: Dict[str, bytes] = {}
        self._xml_trees: Dict[str, ET.ElementTree] = {}
        
        # Track story ID to file mapping
        self._story_files: Dict[str, str] = {}
        
        # Track frame ID to story ID mapping
        self._frame_to_story: Dict[str, str] = {}
    
    def generate(
        self,
        output_path: str | Path,
        template: LayoutTemplate,
        assignments: Dict[str, SlotAssignment],
        content_sections: List[ContentSection],
        image_paths: Optional[Dict[str, str]] = None,
    ) -> Path:
        """
        Generate a new IDML file.
        
        Args:
            output_path: Path for the output IDML file
            template: The layout template
            assignments: Slot-to-content assignments
            content_sections: All content sections
            image_paths: Optional mapping of image identifiers to paths
            
        Returns:
            Path to the generated IDML file
        """
        output = Path(output_path)
        image_paths = image_paths or {}
        
        logger.info(f"Generating IDML: {output}")
        
        # Create temporary directory for working
        self.temp_dir = Path(tempfile.mkdtemp(prefix="idml_gen_"))
        
        try:
            # Step 1: Extract reference IDML
            self._extract_reference()
            
            # Step 2: Parse structure to understand story/frame relationships
            self._parse_structure()
            
            # Step 3: Replace text content in stories
            self._update_stories(template, assignments, content_sections)
            
            # Step 4: Update frame geometries in spreads
            self._update_frame_geometries(template, assignments)
            
            # Step 5: Update image links
            self._update_image_links(assignments, image_paths)
            
            # Step 6: Write modified XML files
            self._write_xml_files()
            
            # Step 7: Package into IDML ZIP
            self._package_idml(output)
            
            logger.info(f"Successfully generated: {output}")
            return output
            
        finally:
            # Clean up temporary directory
            if self.temp_dir and self.temp_dir.exists():
                shutil.rmtree(self.temp_dir)
                self.temp_dir = None
    
    def _extract_reference(self) -> None:
        """Extract the reference IDML to the temporary directory."""
        with zipfile.ZipFile(self.reference_path, 'r') as zf:
            zf.extractall(self.temp_dir)
            
            # Also cache binary content for non-XML files
            for name in zf.namelist():
                if not name.endswith('.xml'):
                    self._extracted_files[name] = zf.read(name)
        
        logger.debug(f"Extracted reference IDML to {self.temp_dir}")
    
    def _parse_structure(self) -> None:
        """
        Parse the IDML structure to understand relationships.
        
        Builds mappings:
        - Story ID to story file path
        - Frame ID to story ID
        """
        # Find all story files
        stories_dir = self.temp_dir / "Stories"
        if stories_dir.exists():
            for story_file in stories_dir.glob("*.xml"):
                tree = ET.parse(story_file)
                root = tree.getroot()
                story_elem = root.find('.//Story')
                if story_elem is not None:
                    story_id = story_elem.get('Self', '')
                    if story_id:
                        self._story_files[story_id] = str(story_file)
                        self._xml_trees[str(story_file)] = tree
        
        # Find text frames and their stories
        spreads_dir = self.temp_dir / "Spreads"
        if spreads_dir.exists():
            for spread_file in spreads_dir.glob("*.xml"):
                tree = ET.parse(spread_file)
                self._xml_trees[str(spread_file)] = tree
                root = tree.getroot()
                
                for text_frame in root.findall('.//TextFrame'):
                    frame_id = text_frame.get('Self', '')
                    parent_story = text_frame.get('ParentStory', '')
                    if frame_id and parent_story:
                        self._frame_to_story[frame_id] = parent_story
        
        logger.debug(f"Found {len(self._story_files)} stories, {len(self._frame_to_story)} text frames")
    
    def _update_stories(
        self,
        template: LayoutTemplate,
        assignments: Dict[str, SlotAssignment],
        content_sections: List[ContentSection],
    ) -> None:
        """
        Update story content based on assignments.
        
        For each text slot assignment, find the corresponding story
        and replace its content with the assigned content block.
        """
        from .models import ContentType
        
        # Group assignments by story
        story_content: Dict[str, List[ContentBlock]] = defaultdict(list)
        
        for slot_id, assignment in assignments.items():
            slot = assignment.slot
            content = assignment.content
            
            # Skip non-text slots
            if slot.slot_type == SlotType.IMAGE:
                continue
            
            # Find the story for this slot's original frame
            if slot.original_frame_id:
                story_id = self._frame_to_story.get(slot.original_frame_id)
                if story_id:
                    story_content[story_id].append(content)
        
        # Update each story file
        for story_id, content_blocks in story_content.items():
            story_file = self._story_files.get(story_id)
            if not story_file:
                logger.warning(f"Story file not found for story {story_id}")
                continue
            
            tree = self._xml_trees.get(story_file)
            if tree is None:
                logger.warning(f"XML tree not loaded for {story_file}")
                continue
            
            root = tree.getroot()
            story_elem = root.find('.//Story')
            if story_elem is None:
                continue
            
            # Remove existing content (ParagraphStyleRange elements)
            for para_range in story_elem.findall('.//ParagraphStyleRange'):
                story_elem.remove(para_range)
            
            # Build new content using actual InDesign styles from template
            # Note: %3a is URL-encoded colon (:) used in InDesign style references
            for content_block in content_blocks:
                # Determine style based on content type
                if content_block.content_type == ContentType.TITLE:
                    para_style = "ParagraphStyle/A4 V%3aColumn Title"
                elif content_block.content_type == ContentType.SUBHEADER:
                    para_style = "ParagraphStyle/A4 V%3aSubheading"
                elif content_block.content_type == ContentType.QUOTE:
                    para_style = "ParagraphStyle/A4 V%3aPull Quote"
                else:
                    # Default to body text style
                    para_style = "ParagraphStyle/A4 V%3aBody Text"
                
                para_elem = create_paragraph_element(
                    text=content_block.text,
                    paragraph_style=para_style,
                )
                story_elem.append(para_elem)
        
        logger.debug(f"Updated {len(story_content)} stories")
    
    def _update_frame_geometries(
        self,
        template: LayoutTemplate,
        assignments: Dict[str, SlotAssignment],
    ) -> None:
        """
        Update frame geometries in spread files.
        
        When slots are swapped or relocated, their corresponding
        frames need updated GeometricBounds attributes.
        """
        # For now, we keep original geometries since we're replacing
        # content in place rather than moving frames.
        # 
        # If variation requires actual frame movement, we would:
        # 1. Find the frame element by original_frame_id
        # 2. Update its GeometricBounds attribute
        # 3. Handle any transform matrix updates
        #
        # This is left as a placeholder for advanced variation support.
        
        logger.debug("Frame geometry updates (placeholder - using original positions)")
    
    def _update_image_links(
        self,
        assignments: Dict[str, SlotAssignment],
        image_paths: Dict[str, str | List[str]],
    ) -> None:
        """
        Update image links in graphic frames.
        
        For IMAGE slot assignments, update the Link element to
        point to the new image file.
        
        IDML Structure for images:
        <Rectangle Self="..." ContentType="GraphicType">
            <Image Self="...">
                <Link Self="..." LinkResourceURI="file:///path/to/image.jpg"/>
            </Image>
        </Rectangle>
        """
        from urllib.parse import quote
        import os
        
        if not image_paths:
            logger.debug("No image paths provided, skipping image updates")
            return
        
        # Flatten image_paths to a list of all image paths with their section titles
        # image_paths is Dict[section_title, str | List[str]]
        all_images: List[Tuple[str, str]] = []  # (section_title, image_path)
        for section_title, paths in image_paths.items():
            if isinstance(paths, list):
                for p in paths:
                    all_images.append((section_title, p))
            else:
                all_images.append((section_title, paths))
        
        if not all_images:
            logger.debug("No images to update")
            return
        
        # Find all Rectangle elements with ContentType="GraphicType" in spreads
        image_frames = []
        for file_path, tree in self._xml_trees.items():
            if "Spread" not in file_path:
                continue
            
            root = tree.getroot()
            # Find all Rectangles that contain images (have Image/Link children)
            for rect in root.findall('.//Rectangle[@ContentType="GraphicType"]'):
                frame_id = rect.get('Self', '')
                # Find the Link element inside
                link = rect.find('.//Link')
                if link is not None and frame_id:
                    image_frames.append({
                        'frame_id': frame_id,
                        'element': rect,
                        'link': link,
                        'file_path': file_path,
                    })
        
        logger.debug(f"Found {len(image_frames)} image frames in spreads")
        
        # Assign images to frames
        # For now, simple sequential assignment - images go to frames in order
        for idx, frame_info in enumerate(image_frames):
            if idx >= len(all_images):
                break
            
            section_title, image_path = all_images[idx]
            
            # Convert to file:// URI format
            # IDML uses file:/ URLs with URL-encoded paths
            abs_path = os.path.abspath(image_path)
            # URL-encode the path (but keep / and :)
            encoded_path = quote(abs_path, safe='/:')
            file_uri = f"file:{encoded_path}"
            
            # Determine format from extension
            ext = os.path.splitext(image_path)[1].lower()
            format_map = {
                '.jpg': '$ID/JPEG',
                '.jpeg': '$ID/JPEG',
                '.png': '$ID/Portable Network Graphics (PNG)',
                '.tif': '$ID/TIFF',
                '.tiff': '$ID/TIFF',
                '.psd': '$ID/Photoshop',
                '.eps': '$ID/EPS',
                '.pdf': '$ID/Adobe Portable Document Format (PDF)',
            }
            link_format = format_map.get(ext, '$ID/JPEG')
            
            # Update the Link element
            link = frame_info['link']
            link.set('LinkResourceURI', file_uri)
            link.set('LinkResourceFormat', link_format)
            
            logger.debug(f"Updated image frame {frame_info['frame_id']} -> {image_path}")
        
        logger.info(f"Updated {min(len(image_frames), len(all_images))} image links")
    
    def _write_xml_files(self) -> None:
        """Write modified XML trees back to files."""
        for file_path, tree in self._xml_trees.items():
            # Write with XML declaration
            tree.write(
                file_path,
                encoding='UTF-8',
                xml_declaration=True,
            )
        
        logger.debug(f"Wrote {len(self._xml_trees)} XML files")
    
    def _package_idml(self, output_path: Path) -> None:
        """
        Package the temporary directory into an IDML ZIP file.
        
        IDML files are ZIP archives with:
        - No compression on mimetype file (for compatibility)
        - Standard ZIP compression on other files
        - Proper file ordering (mimetype first)
        """
        # Ensure parent directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Remove existing file if present
        if output_path.exists():
            output_path.unlink()
        
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Write mimetype first, uncompressed (per OPC spec)
            mimetype_path = self.temp_dir / "mimetype"
            if mimetype_path.exists():
                zf.write(
                    mimetype_path,
                    "mimetype",
                    compress_type=zipfile.ZIP_STORED,
                )
            else:
                # Create mimetype if missing
                zf.writestr(
                    "mimetype",
                    "application/vnd.adobe.indesign-idml-package",
                    compress_type=zipfile.ZIP_STORED,
                )
            
            # Write all other files
            for root, dirs, files in os.walk(self.temp_dir):
                for file in files:
                    if file == "mimetype":
                        continue  # Already written
                    
                    file_path = Path(root) / file
                    arc_name = file_path.relative_to(self.temp_dir)
                    zf.write(file_path, str(arc_name))
        
        logger.info(f"Packaged IDML: {output_path}")


# =============================================================================
# High-Level Generation Function
# =============================================================================


def generate_idml(
    reference_idml: str | Path,
    output_path: str | Path,
    content_sections: List[ContentSection],
    template: Optional[LayoutTemplate] = None,
    variation_seed: Optional[int] = None,
    image_mapping: Optional[Dict[str, str]] = None,
) -> Path:
    """
    High-level function to generate an IDML file.
    
    This is the main entry point for IDML generation. It:
    1. Parses the reference IDML to extract template (if not provided)
    2. Assigns content to slots
    3. Applies variations (if seed provided)
    4. Generates the output IDML
    
    Args:
        reference_idml: Path to the reference IDML file
        output_path: Path for the output IDML file
        content_sections: List of content sections to include
        template: Pre-parsed layout template (optional - will parse if None)
        variation_seed: Random seed for variations (optional)
        image_mapping: Mapping of image identifiers to file paths
        
    Returns:
        Path to the generated IDML file
    """
    from .parser import IDMLParser
    from .variation import VariationEngine, SlotAssigner
    
    # Parse template if not provided
    if template is None:
        parser = IDMLParser(reference_idml)
        template = parser.parse()
    
    # Assign content to slots
    assigner = SlotAssigner(template)
    assignments = assigner.assign_content(content_sections)
    
    # Apply variations if seed provided
    if variation_seed is not None:
        engine = VariationEngine(seed=variation_seed)
        assignments, operations = engine.apply_variations(template, assignments)
        logger.info(f"Applied {len([o for o in operations if o.applied])} variations")
    
    # Generate IDML
    generator = IDMLGenerator(reference_idml)
    return generator.generate(
        output_path=output_path,
        template=template,
        assignments=assignments,
        content_sections=content_sections,
        image_paths=image_mapping,
    )
