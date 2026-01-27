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
    add_break: bool = True,
) -> ET.Element:
    """
    Create a ParagraphStyleRange element with content.
    
    This is the standard way to add text content to a Story in IDML.
    
    Structure:
        <ParagraphStyleRange AppliedParagraphStyle="...">
            <CharacterStyleRange AppliedCharacterStyle="...">
                <Content>Text here</Content>
                <Br/>  <!-- paragraph break -->
            </CharacterStyleRange>
        </ParagraphStyleRange>
    
    Args:
        text: The text content to include
        paragraph_style: Applied paragraph style reference
        character_style: Applied character style reference
        add_break: Whether to add a paragraph break at the end
        
    Returns:
        ET.Element for the ParagraphStyleRange
    """
    para_elem = ET.Element('ParagraphStyleRange')
    para_elem.set('AppliedParagraphStyle', paragraph_style)
    
    char_elem = ET.SubElement(para_elem, 'CharacterStyleRange')
    char_elem.set('AppliedCharacterStyle', character_style)
    
    content = ET.SubElement(char_elem, 'Content')
    content.text = text
    
    # Add paragraph break to separate from next paragraph
    if add_break:
        ET.SubElement(char_elem, 'Br')
    
    return para_elem


def create_quote_element(text: str) -> ET.Element:
    """
    Create a styled quote element matching the reference design.
    
    Uses the styling from the reference IDML:
    - Center-aligned, no hyphenation
    - Medium Italic font at 22pt
    - Green color (c74m0y100k20)
    - Leading of 27pt
    
    Note: Decorative quotation mark graphics are added separately
    to the spread via _add_quote_decorations().
    
    Args:
        text: The quote text content
        
    Returns:
        ET.Element for the styled quote ParagraphStyleRange
    """
    para_elem = ET.Element('ParagraphStyleRange')
    para_elem.set('AppliedParagraphStyle', 'ParagraphStyle/$ID/NormalParagraphStyle')
    para_elem.set('Hyphenation', 'false')
    para_elem.set('Justification', 'CenterAlign')
    
    char_elem = ET.SubElement(para_elem, 'CharacterStyleRange')
    char_elem.set('AppliedCharacterStyle', 'CharacterStyle/$ID/[No character style]')
    char_elem.set('FillColor', 'Color/c74m0y100k20')
    char_elem.set('FontStyle', 'Medium Italic')
    char_elem.set('PointSize', '22')
    char_elem.set('Tracking', '10')
    char_elem.set('OTFContextualAlternate', 'false')
    
    # Add Leading property
    props = ET.SubElement(char_elem, 'Properties')
    leading = ET.SubElement(props, 'Leading')
    leading.set('type', 'unit')
    leading.text = '27'
    
    content = ET.SubElement(char_elem, 'Content')
    content.text = text
    
    # Add paragraph break
    ET.SubElement(char_elem, 'Br')
    
    return para_elem


# Quotation mark path data extracted from reference IDML
# These are the bezier paths for the decorative opening quotation marks
# Opening quotation mark paths (") - curves extracted from reference
OPENING_QUOTE_PATHS = [
    # First curve of opening quote
    [
        ("5.688573362932821 15.280667256452375", "8.937843943720319 11.44960708040175", "2.438492490229914 19.11253772441841"),
        ("0.8138571998361638 28.32879797027286", "0.8138571998361638 23.46218472633037", "0.8138571998361638 32.26438580341116"),
        ("4.2624595918141175 38.063645041988636", "1.9628511358852094 35.509604924621556", "6.561257755827619 40.61768515935572"),
        ("11.963473955855115 41.89470521803926", "9.128262543841284 41.89470521803926", "14.0378212593005 41.89470521803926"),
        ("17.356776944813117 39.63885252554245", "15.835048727676229 41.14275432054033", "18.8776948700346 38.13495073054457"),
        ("19.638558978603044 34.375196243049885", "19.638558978603044 36.38066873368552", "19.638558978603044 32.92315313063814"),
        ("18.134657183605135 30.433936366503723", "19.136988282965273 31.609669935761218", "17.40863562739925 29.57016518467843"),
        ("14.348973354817307 27.944719602369304", "16.146200823193034 28.740426263300293", "11.652321860338308 26.77303749268885"),
        ("10.303996113098806 22.928202354076276", "10.303996113098806 25.10059497928603", "10.303996113098806 21.41133588843187"),
        ("12.067191321027384 18.273075300055368", "10.891457751769863 19.859626870424897", "12.896930242405537 17.101393190374914"),
        ("16.52703802343496 14.446066583581786", "14.383005615264459 15.82518342360678", "17.771646405502192 13.618758537949871"),
        ("18.912537422397158 12.842498882988682", "18.566542774517792 13.083965873780368", "18.912537422397158 12.842498882988682"),
        ("19.01625478756943 12.428439714215024", "19.01625478756943 12.428439714215024", "19.01625478756943 11.773723846565085"),
        ("17.875363770674465 9.428739043373351", "18.635417587327503 10.773823622951195", "17.63308648796737 9.0154901665151"),
        ("16.890048801537905 8.601430997741438", "17.304918262226984 8.739180623360856", "12.671669089922016 9.222924896859633"),
    ],
    # Second curve of opening quote
    [
        ("33.484827229100986 13.177149444052327", "35.93920144087289 11.195175418963531", "31.029642725413677 15.159123469141123"),
        ("27.884089509798454 20.44060617377268", "29.162730152312832 17.580275712381244", "26.60463857536866 23.30093663516412"),
        ("25.965318254111473 29.17717360570539", "25.965318254111473 26.21312577914169", "25.965318254111473 32.79593729991903"),
        ("29.310203280917158 38.301870865118694", "27.080279929713367 35.83777315036193", "31.54012663212095 40.76677887179086"),
        ("36.80378291461362 41.99842258321153", "34.0374463154095 41.99842258321153", "39.05072239604097 41.99842258321153"),
        ("42.50823799908842 39.82035791459392", "40.95247752150438 41.272401027005664", "44.06399847667245 38.36831480218217"),
        ("44.841878715464475 34.945641751497355", "44.841878715464475 36.74367951178846", "44.841878715464475 32.21495799657125"),
        ("40.2264559652985 28.463306428230638", "43.303134368104025 30.05390945817721", "38.11726610949056 27.394531391807035"),
        ("36.18147872358 25.773947560990365", "36.768940362251044 26.498348533365416", "35.766609262890924 25.256981318959838"),
        ("35.55917453254638 23.44597888802221", "35.55917453254638 24.48072166399865", "35.55917453254638 21.72167769203326"),
        ("37.16679369271655 18.7130638101221", "36.094777488631294 20.14403933273322", "38.2379996048864 17.282088287510973"),
        ("44.32329188960313 13.100982004003944", "40.62349900384859 15.411934546748528", "44.32329188960313 13.100982004003944"),
        ("44.530726619947686 12.38549424269838", "44.530726619947686 12.38549424269838", "44.530726619947686 11.738071002287118"),
        ("43.33797692046659 9.931930322841929", "44.13287328948218 10.920486459640104", "42.749704989880115 9.216442561536367"),
        ("41.4192056647796 8.705148362913706", "42.11038466862291 8.807245144255155", "38.58399425276576 9.705048586527594"),
    ],
]

# Closing quotation mark paths (") - from reference, positioned at end of quote
CLOSING_QUOTE_PATHS = [
    # First curve of closing quote (from reference u17adb polygon)
    [
        ("72.64530116046907 32.821583039041705", "72.64530116046907 32.821583039041705", "73.06017062115815 33.3061376044559"),
        ("74.09734427288083 33.547604595247584", "73.54391489465694 33.547604595247584", "75.27226755022296 33.547604595247584"),
        ("79.02391911856363 31.73255070473288", "76.91472926275569 32.94312682635296", "82.27318969935112 29.86563813163204"),
        ("86.8027215064838 24.16118304715724", "84.86612382865786 27.342389107050433", "88.73850889239438 20.98078727917946"),
        ("89.70680773130736 13.63387048217193", "89.70680773130736 17.471412993545886", "89.70680773130736 9.831170523160536"),
        ("86.25820533932942 4.09187288632318", "88.55700350334293 6.650774755182753", "83.9585968834005 1.5337813093790118"),
        ("78.66090834046068 0.2543303749492239", "81.42643464774939 0.2543303749492239", "76.51687593229018 0.2543303749492239"),
        ("73.21574666891655 2.406465702273807", "74.70182204177546 0.9722490120010239", "71.72886100414222 3.841492684461998"),
        ("70.98582331771276 7.514545937008058", "70.98582331771276 5.5439159987349464", "70.98582331771276 9.036274154144943"),
        ("72.33414906495226 11.507664496140416", "71.43472503884898 10.366773479245456", "73.02532806879559 12.37224596988113"),
        ("77.36444127580731 14.878478864239161", "74.70182204177546 13.496120856552514", "79.23135384890819 15.881620255514703"),
        ("80.1648101354586 19.182749518888325", "80.1648101354586 17.31583694578748", "80.1648101354586 20.70447773602521"),
        ("78.29789756235775 24.005606999398836", "79.54250594442497 22.31209689619538", "77.05328918029052 25.6999273945177"),
        ("73.52689876443335 28.05058424111733", "75.46268615034393 27.0482531417572", "72.55859992552037 28.535138806531524"),
        ("71.50441014357409 29.60634471870137", "71.88443705190062 29.053725632392865", "71.7458771343658 31.128072935838254"),
        ("72.64530116046907 32.821583039041705", "72.12671433460771 32.19927884800809", "72.64530116046907 32.821583039041705"),
    ],
    # Second curve of closing quote
    [
        ("96.65587119784941 29.813779449045906", "96.65587119784941 29.813779449045906", "96.65587119784941 30.564109762714036"),
        ("97.90047957991663 32.57444400484216", "97.07074065853851 31.483791086702514", "98.31534904060574 33.15461301627454"),
        ("99.1450879619839 33.44388723007532", "98.7302185012948 33.44388723007532", "100.90828316991244 33.44388723007532"),
        ("105.36812987232004 30.95872192551791", "102.98263047335783 32.61576889252799", "108.5833681926604 28.74986616411474"),
        ("112.75799214084424 23.166144575035784", "111.04665561550179 26.15207028331556", "114.46932866618667 20.181029158671414"),
        ("115.32499692885789 13.872096305301985", "115.32499692885789 17.08247287414988", "115.32499692885789 10.041036129251298"),
        ("111.82453585429379 4.293635573259858", "114.15817657066984 6.847675690626984", "109.49089513791776 1.7395954558927331"),
        ("104.07166280766667 0.46176510529376213", "106.9060639277651 0.46176510529376213", "101.85875558668646 0.46176510529376213"),
        ("98.52278377095027 2.613900432618345", "100.00885914380919 1.1796837423455617", "97.03589810617594 4.048927414806536"),
        ("96.29286041974645 7.566404619594192", "96.29286041974645 5.69949204649335", "96.29286041974645 8.569546010869733"),
        ("96.91516461078008 10.314914796659323", "96.50029515009102 9.48517587528117", "97.33003407146919 11.144653718037473"),
        ("98.5746424535364 12.492979465276973", "97.88265315777767 11.870675274243357", "98.78207718388094 12.70041419562151"),
        ("100.75270712215404 13.7375878473442", "99.50809874008682 13.115283656310586", "102.79221187323685 14.77476149906689"),
        ("104.69396699870029 16.38238065923706", "104.10569506811383 15.656359103031178", "105.24658608500879 17.108402215442943"),
        ("105.52370592007846 19.23460820147446", "105.52370592007846 18.05968492413235", "105.52370592007846 20.894086044230765"),
        ("103.5012172992192 24.16118304715724", "104.84954304645868 22.536547756763497", "102.11804899961713 25.78662862946639"),
        ("98.36720772319184 28.309877654048005", "100.4067124742747 27.168986637153044", "97.71006097979567 28.65587230192737"),
        ("96.70772988043555 29.45076867094296", "97.15663160157179 29.035899210253884", "96.70772988043555 29.45076867094296"),
    ],
]


def create_quote_decoration_element(
    frame_id: str, 
    x_offset: float, 
    y_offset: float,
    quote_type: str = "opening"
) -> ET.Element:
    """
    Create a decorative quotation mark polygon element.
    
    This creates the green semi-transparent quotation mark graphic
    that appears behind quote text in the reference design.
    
    Args:
        frame_id: Unique ID for this element
        x_offset: X position offset
        y_offset: Y position offset
        quote_type: "opening" for " or "closing" for "
        
    Returns:
        ET.Element for the Polygon with quotation mark paths
    """
    polygon = ET.Element('Polygon')
    polygon.set('Self', frame_id)
    polygon.set('ContentType', 'Unassigned')
    polygon.set('StoryTitle', '$ID/')
    polygon.set('Visible', 'true')
    polygon.set('Name', '$ID/')
    polygon.set('FillColor', 'Color/c74m0y100k20')
    polygon.set('FillTint', '90')
    polygon.set('AppliedObjectStyle', 'ObjectStyle/$ID/[None]')
    polygon.set('ItemTransform', f'1 0 0 1 {x_offset} {y_offset}')
    
    # Add Properties with PathGeometry
    props = ET.SubElement(polygon, 'Properties')
    path_geom = ET.SubElement(props, 'PathGeometry')
    
    # Select opening or closing quote paths
    paths = OPENING_QUOTE_PATHS if quote_type == "opening" else CLOSING_QUOTE_PATHS
    
    # Add quotation mark paths
    for path_points in paths:
        geom_path = ET.SubElement(path_geom, 'GeometryPathType')
        geom_path.set('PathOpen', 'false')
        
        point_array = ET.SubElement(geom_path, 'PathPointArray')
        for anchor, left_dir, right_dir in path_points:
            point = ET.SubElement(point_array, 'PathPointType')
            point.set('Anchor', anchor)
            point.set('LeftDirection', left_dir)
            point.set('RightDirection', right_dir)
    
    # Add transparency (15% opacity like the reference)
    transparency = ET.SubElement(polygon, 'TransparencySetting')
    blending = ET.SubElement(transparency, 'BlendingSetting')
    blending.set('Opacity', '15')
    
    return polygon


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
            
            # Step 3.5: Enable auto-sizing on text frames to prevent overset
            self._enable_frame_auto_sizing(template, assignments)
            
            # Step 4: Add decorative quote marks to spreads for quote content
            self._add_quote_decorations(template, assignments)
            
            # Step 5: Update frame geometries in spreads
            self._update_frame_geometries(template, assignments)
            
            # Step 6: Update image links
            self._update_image_links(assignments, image_paths)
            
            # Step 6.5: Clear unassigned stories (remove old template content)
            self._clear_unassigned_stories(template, assignments)
            
            # Step 6.6: Remove unused spreads (pages without new content)
            self._remove_unused_spreads(template, assignments)
            
            # Step 7: Write modified XML files
            self._write_xml_files()
            
            # Step 8: Package into IDML ZIP
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
        
        # Group assignments by story, keeping track of slot ordering
        # Key: story_id, Value: list of (slot, content) tuples
        story_content: Dict[str, List[Tuple[Slot, ContentBlock]]] = defaultdict(list)
        
        for slot_id, assignment in assignments.items():
            slot = assignment.slot
            
            # Skip non-text slots
            if slot.slot_type == SlotType.IMAGE:
                continue
            
            # Find the story for this slot's original frame
            if slot.original_frame_id:
                story_id = self._frame_to_story.get(slot.original_frame_id)
                if story_id:
                    # Add all content blocks from this assignment to the story
                    for content_block in assignment.content_blocks:
                        story_content[story_id].append((slot, content_block))
        
        # Store original story styling templates before modifying
        # Key: story_id, Value: first ParagraphStyleRange element (as template)
        original_story_templates: Dict[str, ET.Element] = {}
        for story_id in story_content.keys():
            story_file = self._story_files.get(story_id)
            if story_file:
                tree = self._xml_trees.get(story_file)
                if tree is not None:
                    root = tree.getroot()
                    story_elem = root.find('.//Story')
                    if story_elem is not None:
                        first_para = story_elem.find('.//ParagraphStyleRange')
                        if first_para is not None:
                            # Deep copy the original element to preserve styling
                            import copy
                            original_story_templates[story_id] = copy.deepcopy(first_para)
        
        # Update each story file
        for story_id, slot_content_pairs in story_content.items():
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
            
            # Sort content by slot position (spread, y, x) for proper flow order
            sorted_pairs = sorted(
                slot_content_pairs,
                key=lambda pair: (pair[0].spread_index, pair[0].geometry.y, pair[0].geometry.x)
            )
            
            # Check if this story has custom styling we should preserve
            # (e.g., story u5a7 with 56pt P22 Chai Tea Pro)
            original_template = original_story_templates.get(story_id)
            has_custom_styling = False
            if original_template is not None:
                # Check if it has PointSize or AppliedFont in CharacterStyleRange
                for csr in original_template.iter('CharacterStyleRange'):
                    if csr.get('PointSize') or csr.find('.//AppliedFont') is not None:
                        has_custom_styling = True
                        break
                    # Also check Properties for AppliedFont
                    props = csr.find('Properties')
                    if props is not None and props.find('AppliedFont') is not None:
                        has_custom_styling = True
                        break
            
            # Build new content
            prev_content_type = None
            for idx, (slot, content_block) in enumerate(sorted_pairs):
                # Add spacing between headers/subheaders and body text
                # Only add spacing for these transitions:
                # - SUBHEADER → BODY (space after subheader before body)
                # - BODY → SUBHEADER (space before new section)
                # - After QUOTE (space after quote)
                if prev_content_type is not None:
                    should_add_spacing = False
                    # Space after subheader before body
                    if prev_content_type == ContentType.SUBHEADER and content_block.content_type == ContentType.BODY:
                        should_add_spacing = True
                    # Space before subheader (new section)
                    elif content_block.content_type == ContentType.SUBHEADER and prev_content_type in (ContentType.BODY, ContentType.QUOTE):
                        should_add_spacing = True
                    # Space after quote
                    elif prev_content_type == ContentType.QUOTE:
                        should_add_spacing = True
                    # Space before quote
                    elif content_block.content_type == ContentType.QUOTE:
                        should_add_spacing = True
                    
                    if should_add_spacing:
                        spacing_elem = create_paragraph_element(
                            text="",
                            paragraph_style="ParagraphStyle/$ID/NormalParagraphStyle",
                            add_break=True,
                        )
                        story_elem.append(spacing_elem)
                
                # Use special styling for quotes (center-aligned, green, italic)
                if content_block.content_type == ContentType.QUOTE:
                    para_elem = create_quote_element(content_block.text)
                elif content_block.content_type == ContentType.TITLE and has_custom_styling and original_template is not None:
                    # Preserve original story styling for title with custom fonts
                    import copy
                    para_elem = copy.deepcopy(original_template)
                    # Update the content text
                    for content_elem in para_elem.iter('Content'):
                        content_elem.text = content_block.text
                        break
                    # Ensure paragraph break at end
                    for csr in para_elem.iter('CharacterStyleRange'):
                        # Remove any existing Br elements
                        for br in list(csr.findall('Br')):
                            csr.remove(br)
                        # Add Br at the end
                        ET.SubElement(csr, 'Br')
                        break
                else:
                    # Determine style based on content type
                    if content_block.content_type == ContentType.TITLE:
                        para_style = "ParagraphStyle/A4 V%3aColumn Title"
                    elif content_block.content_type == ContentType.SUBHEADER:
                        para_style = "ParagraphStyle/A4 V%3aSubheading"
                    else:
                        # Default to body text style
                        para_style = "ParagraphStyle/A4 V%3aBody Text"
                    
                    para_elem = create_paragraph_element(
                        text=content_block.text,
                        paragraph_style=para_style,
                    )
                story_elem.append(para_elem)
                prev_content_type = content_block.content_type
        
        logger.debug(f"Updated {len(story_content)} stories")
    
    def _enable_frame_auto_sizing(
        self,
        template: LayoutTemplate,
        assignments: Dict[str, SlotAssignment],
    ) -> None:
        """
        Enable auto-sizing on text frames to prevent overset text.
        
        Text frames in the template may be sized for specific content.
        When we replace the content, it may not fit. Enabling auto-sizing
        allows the frame to grow to accommodate the new content.
        """
        # Collect frame IDs that have assigned content
        assigned_frame_ids = set()
        for slot_id, assignment in assignments.items():
            if assignment.slot.original_frame_id:
                assigned_frame_ids.add(assignment.slot.original_frame_id)
        
        if not assigned_frame_ids:
            return
        
        # Process each spread file
        spreads_dir = self.temp_dir / "Spreads"
        if not spreads_dir.exists():
            return
        
        modified_count = 0
        for spread_file in spreads_dir.glob("*.xml"):
            tree = self._xml_trees.get(str(spread_file))
            if tree is None:
                continue
            
            root = tree.getroot()
            
            # Find text frames with assigned content
            for text_frame in root.findall('.//TextFrame'):
                frame_id = text_frame.get('Self', '')
                if frame_id not in assigned_frame_ids:
                    continue
                
                # Find or create TextFramePreference element
                tfp = text_frame.find('.//TextFramePreference')
                if tfp is None:
                    # Create TextFramePreference
                    tfp = ET.SubElement(text_frame, 'TextFramePreference')
                
                # Enable auto-sizing (grow height to fit content)
                # AutoSizingType options: Off, HeightOnly, WidthOnly, HeightAndWidth, HeightAndWidthProportionally
                tfp.set('AutoSizingType', 'HeightOnly')
                tfp.set('AutoSizingReferencePoint', 'TopCenterPoint')
                tfp.set('UseMinimumHeightForAutoSizing', 'false')
                tfp.set('UseMinimumWidthForAutoSizing', 'false')
                
                modified_count += 1
        
        logger.debug(f"Enabled auto-sizing on {modified_count} text frames")
    
    def _add_quote_decorations(
        self,
        template: LayoutTemplate,
        assignments: Dict[str, SlotAssignment],
    ) -> None:
        """
        Add decorative quotation mark graphics to spreads for quote content.
        
        For each text frame that contains quote content, add opening quote marks
        at the start (top-left) and closing quote marks at the end (bottom-right).
        """
        from .models import ContentType
        import uuid
        
        # Find assignments with quote content
        quote_frame_ids = []
        for slot_id, assignment in assignments.items():
            # Check all content blocks for quote type
            has_quote = any(
                block.content_type == ContentType.QUOTE 
                for block in assignment.content_blocks
            )
            if has_quote and assignment.slot.original_frame_id:
                quote_frame_ids.append(assignment.slot.original_frame_id)
        
        if not quote_frame_ids:
            return
        
        # Process each spread file to find and decorate quote frames
        spreads_dir = self.temp_dir / "Spreads"
        if not spreads_dir.exists():
            return
        
        decoration_count = 0
        for spread_file in spreads_dir.glob("*.xml"):
            tree = self._xml_trees.get(str(spread_file))
            if tree is None:
                continue
            
            root = tree.getroot()
            spread_elem = root.find('.//Spread')
            if spread_elem is None:
                continue
            
            # Find text frames that contain quote content
            for text_frame in root.findall('.//TextFrame'):
                frame_id = text_frame.get('Self', '')
                if frame_id not in quote_frame_ids:
                    continue
                
                # Get the frame's position from ItemTransform
                item_transform = text_frame.get('ItemTransform', '1 0 0 1 0 0')
                transform_parts = item_transform.split()
                if len(transform_parts) >= 6:
                    x_pos = float(transform_parts[4])
                    y_pos = float(transform_parts[5])
                else:
                    x_pos, y_pos = 0, 0
                
                # Try to get frame dimensions from PathGeometry
                frame_width = 200  # Default width
                frame_height = 50  # Default height
                path_geom = text_frame.find('.//PathGeometry//PathPointArray')
                if path_geom is not None:
                    points = path_geom.findall('PathPointType')
                    if len(points) >= 4:
                        # Extract bounding box from path points
                        x_coords = []
                        y_coords = []
                        for pt in points:
                            anchor = pt.get('Anchor', '0 0').split()
                            if len(anchor) >= 2:
                                x_coords.append(float(anchor[0]))
                                y_coords.append(float(anchor[1]))
                        if x_coords and y_coords:
                            frame_width = max(x_coords) - min(x_coords)
                            frame_height = max(y_coords) - min(y_coords)
                
                # Find the parent of the text frame
                parent = None
                for potential_parent in root.iter():
                    if text_frame in list(potential_parent):
                        parent = potential_parent
                        break
                
                if parent is None:
                    continue
                
                # Get index of text_frame in parent
                idx = list(parent).index(text_frame)
                
                # Create opening quote at top-left of frame
                open_id = f"uquote_open_{uuid.uuid4().hex[:8]}"
                open_x = x_pos - 50  # Position to the left of frame
                open_y = y_pos - 25  # Position above frame
                open_decoration = create_quote_decoration_element(open_id, open_x, open_y, "opening")
                parent.insert(idx, open_decoration)
                decoration_count += 1
                
                # Create closing quote at bottom-right of frame
                close_id = f"uquote_close_{uuid.uuid4().hex[:8]}"
                close_x = x_pos + frame_width - 50  # Position near right side
                close_y = y_pos + frame_height - 20  # Position near bottom
                close_decoration = create_quote_decoration_element(close_id, close_x, close_y, "closing")
                parent.insert(idx + 2, close_decoration)  # Insert after text frame
                decoration_count += 1
                
                logger.debug(f"Added quote decorations for frame {frame_id}")
        
        logger.debug(f"Added {decoration_count} quote decorations")
    
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
    
    def _clear_unassigned_stories(
        self,
        template: LayoutTemplate,
        assignments: Dict[str, SlotAssignment],
    ) -> None:
        """
        Clear content from stories that don't have assigned content.
        
        This removes old template content from text frames that won't
        receive new content, preventing "Editor's Words" etc. from appearing.
        """
        # Get stories that have assigned content
        assigned_story_ids = set()
        for slot_id, assignment in assignments.items():
            if assignment.slot.parent_story_id:
                assigned_story_ids.add(assignment.slot.parent_story_id)
        
        # Get all story IDs from slots on kept spreads
        spreads_with_content = set()
        for slot_id, assignment in assignments.items():
            spreads_with_content.add(assignment.slot.spread_index)
        
        # Collect story IDs from unassigned slots on spreads with content
        stories_to_clear = set()
        for slot in template.slots:
            if slot.spread_index in spreads_with_content:
                if slot.parent_story_id and slot.parent_story_id not in assigned_story_ids:
                    stories_to_clear.add(slot.parent_story_id)
        
        if not stories_to_clear:
            return
        
        # Clear content from these stories
        stories_dir = self.temp_dir / "Stories"
        if not stories_dir.exists():
            return
        
        cleared_count = 0
        for story_id in stories_to_clear:
            story_file = self._story_files.get(story_id)
            if not story_file:
                continue
            
            tree = self._xml_trees.get(story_file)
            if tree is None:
                continue
            
            root = tree.getroot()
            story_elem = root.find('.//Story')
            if story_elem is None:
                continue
            
            # Remove all ParagraphStyleRange elements (the content)
            for para_range in story_elem.findall('.//ParagraphStyleRange'):
                story_elem.remove(para_range)
            
            cleared_count += 1
            logger.debug(f"Cleared unassigned story: {story_id}")
        
        logger.info(f"Cleared {cleared_count} unassigned stories")
    
    def _remove_unused_spreads(
        self,
        template: LayoutTemplate,
        assignments: Dict[str, SlotAssignment],
    ) -> None:
        """
        Remove spreads that don't have any assigned content.
        
        This prevents old template content from appearing in the output
        when there isn't enough new content to fill all template pages.
        Also handles breaking threaded frame chains that span removed spreads.
        """
        # Determine which spread indices have content assigned
        spreads_with_content = set()
        for slot_id, assignment in assignments.items():
            spreads_with_content.add(assignment.slot.spread_index)
        
        if not spreads_with_content:
            logger.warning("No spreads have content - keeping all spreads")
            return
        
        # Get list of spread files
        spreads_dir = self.temp_dir / "Spreads"
        if not spreads_dir.exists():
            return
        
        # Map spread files to their indices based on template slot info
        # Build spread file to index mapping from template slots
        spread_file_to_index = {}
        for slot in template.slots:
            if slot.original_frame_id:
                # Find which spread file contains this frame
                for spread_file in spreads_dir.glob("*.xml"):
                    tree = self._xml_trees.get(str(spread_file))
                    if tree is None:
                        continue
                    root = tree.getroot()
                    for tf in root.findall('.//TextFrame'):
                        if tf.get('Self') == slot.original_frame_id:
                            spread_file_to_index[str(spread_file)] = slot.spread_index
                            break
        
        # Find spreads to remove (those not in spreads_with_content)
        spreads_to_remove = []
        spread_ids_to_remove = []
        frames_on_removed_spreads = set()
        
        for spread_file in spreads_dir.glob("*.xml"):
            file_path = str(spread_file)
            spread_index = spread_file_to_index.get(file_path)
            
            if spread_index is not None and spread_index not in spreads_with_content:
                spreads_to_remove.append(spread_file)
                
                # Get the spread ID and all frame IDs from the XML
                tree = self._xml_trees.get(file_path)
                if tree:
                    root = tree.getroot()
                    spread_elem = root.find('.//Spread')
                    if spread_elem is not None:
                        spread_id = spread_elem.get('Self')
                        if spread_id:
                            spread_ids_to_remove.append(spread_id)
                    
                    # Collect all frame IDs on this spread
                    for tf in root.findall('.//TextFrame'):
                        frame_id = tf.get('Self')
                        if frame_id:
                            frames_on_removed_spreads.add(frame_id)
        
        if not spreads_to_remove:
            logger.debug("No unused spreads to remove")
            return
        
        # Break threaded frame chains that point to removed frames
        # Check remaining spreads for frames that link to removed frames
        for spread_file in spreads_dir.glob("*.xml"):
            file_path = str(spread_file)
            if spread_file in spreads_to_remove:
                continue
            
            tree = self._xml_trees.get(file_path)
            if tree is None:
                continue
            
            root = tree.getroot()
            for tf in root.findall('.//TextFrame'):
                next_frame = tf.get('NextTextFrame', 'n')
                if next_frame != 'n' and next_frame in frames_on_removed_spreads:
                    # Break the chain by setting NextTextFrame to "n"
                    tf.set('NextTextFrame', 'n')
                    logger.debug(f"Broke thread chain at frame {tf.get('Self')} -> {next_frame}")
        
        # Remove spread files
        spread_filenames_to_remove = []
        for spread_file in spreads_to_remove:
            file_path = str(spread_file)
            # Store the relative path as it appears in designmap.xml
            spread_filenames_to_remove.append(f"Spreads/{spread_file.name}")
            # Remove from XML trees cache
            if file_path in self._xml_trees:
                del self._xml_trees[file_path]
            # Delete the file
            spread_file.unlink()
            logger.debug(f"Removed unused spread: {spread_file.name}")
        
        # Update designmap.xml to remove references to deleted spreads
        # Use raw text manipulation to preserve InDesign processing instructions
        designmap_path = self.temp_dir / "designmap.xml"
        if designmap_path.exists() and spread_filenames_to_remove:
            # Read the raw content
            with open(designmap_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Remove spread references using regex
            import re
            for spread_filename in spread_filenames_to_remove:
                # Match the entire idPkg:Spread element for this spread
                # Pattern matches: <idPkg:Spread src="Spreads/Spread_xxx.xml" />
                pattern = rf'\s*<idPkg:Spread[^>]*src="{re.escape(spread_filename)}"[^>]*/>'
                content = re.sub(pattern, '', content)
                logger.debug(f"Removed designmap reference: {spread_filename}")
            
            # Write back the modified content
            with open(designmap_path, 'w', encoding='utf-8') as f:
                f.write(content)
        
        logger.info(f"Removed {len(spreads_to_remove)} unused spreads")
    
    def _write_xml_files(self) -> None:
        """Write modified XML trees back to files, preserving InDesign headers."""
        import re
        
        for file_path, tree in self._xml_trees.items():
            # Read the original file to preserve processing instructions and XML declaration
            original_header = ''
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    original_content = f.read()
                    # Extract everything before the root element (first tag that's not <? or <!)
                    # This preserves <?xml?> and <?aid?> processing instructions
                    match = re.match(r'^(.*?)(<[^?!])', original_content, re.DOTALL)
                    if match:
                        original_header = match.group(1)
            except Exception:
                pass
            
            # Write the tree to a string
            import io
            output = io.BytesIO()
            tree.write(output, encoding='UTF-8', xml_declaration=False)  # No declaration, we'll add original
            new_content = output.getvalue().decode('utf-8')
            
            # Use the original header (preserves <?xml...?> and <?aid...?> exactly)
            if original_header:
                new_content = original_header + new_content
            else:
                # Fallback: add standard XML declaration
                new_content = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + new_content
            
            # Write the final content
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
        
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
