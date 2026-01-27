"""
Pytest configuration and shared fixtures.
"""

import pytest
import io
import zipfile
from pathlib import Path

from idml_layout_engine.models import (
    FrameGeometry,
    PageDimensions,
    Slot,
    SlotType,
    VerticalPosition,
    LayoutTemplate,
    ContentBlock,
    ContentType,
    ContentSection,
    SlotAssignment,
)


# ============================================================================
# Common Geometry Fixtures
# ============================================================================

@pytest.fixture
def standard_page_dimensions():
    """US Letter page dimensions in points."""
    return PageDimensions(width=612.0, height=792.0)


@pytest.fixture
def a4_page_dimensions():
    """A4 page dimensions in points."""
    return PageDimensions(width=595.28, height=841.89)


@pytest.fixture
def simple_geometry():
    """A simple frame geometry for testing."""
    return FrameGeometry(x=36.0, y=36.0, width=200.0, height=100.0)


# ============================================================================
# Template Fixtures
# ============================================================================

@pytest.fixture
def empty_template(standard_page_dimensions):
    """An empty layout template."""
    return LayoutTemplate(
        template_id="empty_template",
        page_dimensions=standard_page_dimensions,
    )


@pytest.fixture
def single_column_template(standard_page_dimensions):
    """A single-column layout template."""
    template = LayoutTemplate(
        template_id="single_column",
        page_dimensions=standard_page_dimensions,
    )
    
    # Title at top
    template.add_slot(Slot(
        slot_id="title_0",
        slot_type=SlotType.TITLE,
        geometry=FrameGeometry(x=36, y=36, width=540, height=50),
        column_index=0,
        vertical_position=VerticalPosition.TOP,
    ))
    
    # Body in middle
    template.add_slot(Slot(
        slot_id="body_0",
        slot_type=SlotType.PARAGRAPH,
        geometry=FrameGeometry(x=36, y=100, width=540, height=500),
        column_index=0,
        vertical_position=VerticalPosition.MIDDLE,
    ))
    
    # Quote at bottom
    template.add_slot(Slot(
        slot_id="quote_0",
        slot_type=SlotType.QUOTE,
        geometry=FrameGeometry(x=36, y=620, width=540, height=100),
        column_index=0,
        vertical_position=VerticalPosition.BOTTOM,
    ))
    
    return template


@pytest.fixture
def two_column_template(standard_page_dimensions):
    """A two-column layout template."""
    template = LayoutTemplate(
        template_id="two_column",
        page_dimensions=standard_page_dimensions,
    )
    
    # Title spanning both columns
    template.add_slot(Slot(
        slot_id="title_0",
        slot_type=SlotType.TITLE,
        geometry=FrameGeometry(x=36, y=36, width=540, height=50),
        column_index=0,
        vertical_position=VerticalPosition.TOP,
        spans_columns=True,
    ))
    
    # Left column body
    template.add_slot(Slot(
        slot_id="body_left",
        slot_type=SlotType.PARAGRAPH,
        geometry=FrameGeometry(x=36, y=100, width=260, height=400),
        column_index=0,
        vertical_position=VerticalPosition.MIDDLE,
    ))
    
    # Right column body
    template.add_slot(Slot(
        slot_id="body_right",
        slot_type=SlotType.PARAGRAPH,
        geometry=FrameGeometry(x=316, y=100, width=260, height=400),
        column_index=1,
        vertical_position=VerticalPosition.MIDDLE,
    ))
    
    # Left column image
    template.add_slot(Slot(
        slot_id="image_left",
        slot_type=SlotType.IMAGE,
        geometry=FrameGeometry(x=36, y=520, width=260, height=200),
        column_index=0,
        vertical_position=VerticalPosition.BOTTOM,
    ))
    
    # Right column quote
    template.add_slot(Slot(
        slot_id="quote_right",
        slot_type=SlotType.QUOTE,
        geometry=FrameGeometry(x=316, y=520, width=260, height=200),
        column_index=1,
        vertical_position=VerticalPosition.BOTTOM,
    ))
    
    return template


# ============================================================================
# Content Fixtures
# ============================================================================

@pytest.fixture
def sample_content_blocks():
    """A set of sample content blocks."""
    return [
        ContentBlock(
            content_id="title_1",
            content_type=ContentType.TITLE,
            text="The Main Article Title",
            section_title="The Main Article Title",
            sequence_index=0,
        ),
        ContentBlock(
            content_id="body_1",
            content_type=ContentType.BODY,
            text="This is the first paragraph of body text. It contains "
                 "information about the topic at hand.",
            section_title="The Main Article Title",
            sequence_index=1,
        ),
        ContentBlock(
            content_id="body_2",
            content_type=ContentType.BODY,
            text="This is the second paragraph with more details and "
                 "supporting information for the reader.",
            section_title="The Main Article Title",
            sequence_index=2,
        ),
        ContentBlock(
            content_id="quote_1",
            content_type=ContentType.QUOTE,
            text="Design is not just what it looks like. Design is how it works.",
            section_title="The Main Article Title",
            sequence_index=3,
        ),
    ]


@pytest.fixture
def sample_content_section(sample_content_blocks):
    """A sample content section with title, body, and quote."""
    title = sample_content_blocks[0]
    body_blocks = sample_content_blocks[1:3]
    quote = sample_content_blocks[3]
    
    return ContentSection(
        section_id="section_1",
        title=title,
        body_blocks=[*body_blocks, quote],
        image_paths=["images/hero.jpg", "images/sidebar.png"],
    )


@pytest.fixture
def multiple_content_sections():
    """Multiple content sections for complex layouts."""
    sections = []
    
    for i in range(3):
        title = ContentBlock(
            content_id=f"title_{i}",
            content_type=ContentType.TITLE,
            text=f"Section {i + 1} Title",
            section_title=f"Section {i + 1} Title",
            sequence_index=0,
        )
        
        body = ContentBlock(
            content_id=f"body_{i}",
            content_type=ContentType.BODY,
            text=f"Body text for section {i + 1}.",
            section_title=f"Section {i + 1} Title",
            sequence_index=1,
        )
        
        section = ContentSection(
            section_id=f"section_{i}",
            title=title,
            body_blocks=[body],
            image_paths=[f"images/section_{i}.jpg"],
        )
        
        sections.append(section)
    
    return sections


# ============================================================================
# Mock IDML Fixtures
# ============================================================================

@pytest.fixture
def minimal_idml_bytes():
    """Create minimal valid IDML file bytes."""
    buffer = io.BytesIO()
    
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Mimetype (first file, uncompressed by convention)
        zf.writestr('mimetype', 'application/vnd.adobe.indesign-idml-package')
        
        # Design map
        designmap = '''<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging"
          xmlns:idPkg="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging"
          DOMVersion="15.0">
    <idPkg:Spread src="Spreads/Spread_uc3.xml"/>
    <idPkg:Story src="Stories/Story_uc5.xml"/>
</Document>'''
        zf.writestr('designmap.xml', designmap)
        
        # Empty preferences
        prefs = '''<?xml version="1.0" encoding="UTF-8"?>
<idPkg:Preferences xmlns:idPkg="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging"
                   DOMVersion="15.0">
</idPkg:Preferences>'''
        zf.writestr('Resources/Preferences.xml', prefs)
        
        # Spread with a single text frame
        spread = '''<?xml version="1.0" encoding="UTF-8"?>
<idPkg:Spread xmlns:idPkg="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging"
              DOMVersion="15.0">
    <Spread Self="uc3" FlattenerOverride="Default"
            PageCount="1" BindingLocation="0"
            AllowPageShuffle="true">
        <Page Self="uc4" GeometricBounds="0 0 792 612"
              ItemTransform="1 0 0 1 0 0"/>
        <TextFrame Self="uc5" ParentStory="uc6"
                   ItemTransform="1 0 0 1 36 36"
                   ContentType="TextType">
            <Properties>
                <PathGeometry>
                    <GeometryPathType PathOpen="false">
                        <PathPointArray>
                            <PathPointType Anchor="0 0"/>
                            <PathPointType Anchor="0 100"/>
                            <PathPointType Anchor="200 100"/>
                            <PathPointType Anchor="200 0"/>
                        </PathPointArray>
                    </GeometryPathType>
                </PathGeometry>
            </Properties>
        </TextFrame>
    </Spread>
</idPkg:Spread>'''
        zf.writestr('Spreads/Spread_uc3.xml', spread)
        
        # Story
        story = '''<?xml version="1.0" encoding="UTF-8"?>
<idPkg:Story xmlns:idPkg="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging"
             DOMVersion="15.0">
    <Story Self="uc6" AppliedTOCStyle="n"
           UserText="true" IsEndnoteStory="false"
           TrackChanges="false" StoryTitle="$ID/">
        <ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/$ID/NormalParagraphStyle">
            <CharacterStyleRange AppliedCharacterStyle="CharacterStyle/$ID/[No character style]">
                <Content>Sample text content</Content>
            </CharacterStyleRange>
        </ParagraphStyleRange>
    </Story>
</idPkg:Story>'''
        zf.writestr('Stories/Story_uc5.xml', story)
    
    buffer.seek(0)
    return buffer.getvalue()


@pytest.fixture
def complex_idml_bytes():
    """Create more complex IDML with multiple frames."""
    buffer = io.BytesIO()
    
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('mimetype', 'application/vnd.adobe.indesign-idml-package')
        
        designmap = '''<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging"
          xmlns:idPkg="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging">
    <idPkg:Spread src="Spreads/Spread_u1.xml"/>
    <idPkg:Story src="Stories/Story_title.xml"/>
    <idPkg:Story src="Stories/Story_body.xml"/>
</Document>'''
        zf.writestr('designmap.xml', designmap)
        
        spread = '''<?xml version="1.0" encoding="UTF-8"?>
<idPkg:Spread xmlns:idPkg="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging">
    <Spread Self="u1">
        <Page Self="page_u1" GeometricBounds="0 0 792 612"/>
        <TextFrame Self="tf_title" ParentStory="story_title"
                   ItemTransform="1 0 0 1 36 36">
            <Properties>
                <PathGeometry>
                    <GeometryPathType PathOpen="false">
                        <PathPointArray>
                            <PathPointType Anchor="0 0"/>
                            <PathPointType Anchor="0 50"/>
                            <PathPointType Anchor="540 50"/>
                            <PathPointType Anchor="540 0"/>
                        </PathPointArray>
                    </GeometryPathType>
                </PathGeometry>
            </Properties>
        </TextFrame>
        <TextFrame Self="tf_body" ParentStory="story_body"
                   ItemTransform="1 0 0 1 36 100">
            <Properties>
                <PathGeometry>
                    <GeometryPathType PathOpen="false">
                        <PathPointArray>
                            <PathPointType Anchor="0 0"/>
                            <PathPointType Anchor="0 400"/>
                            <PathPointType Anchor="260 400"/>
                            <PathPointType Anchor="260 0"/>
                        </PathPointArray>
                    </GeometryPathType>
                </PathGeometry>
            </Properties>
        </TextFrame>
        <Rectangle Self="rect_img" ItemTransform="1 0 0 1 316 100">
            <Properties>
                <PathGeometry>
                    <GeometryPathType PathOpen="false">
                        <PathPointArray>
                            <PathPointType Anchor="0 0"/>
                            <PathPointType Anchor="0 300"/>
                            <PathPointType Anchor="260 300"/>
                            <PathPointType Anchor="260 0"/>
                        </PathPointArray>
                    </GeometryPathType>
                </PathGeometry>
            </Properties>
            <Image Self="img_content"/>
        </Rectangle>
    </Spread>
</idPkg:Spread>'''
        zf.writestr('Spreads/Spread_u1.xml', spread)
        
        story_title = '''<?xml version="1.0" encoding="UTF-8"?>
<idPkg:Story xmlns:idPkg="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging">
    <Story Self="story_title">
        <ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/Title">
            <CharacterStyleRange>
                <Content>Article Title</Content>
            </CharacterStyleRange>
        </ParagraphStyleRange>
    </Story>
</idPkg:Story>'''
        zf.writestr('Stories/Story_title.xml', story_title)
        
        story_body = '''<?xml version="1.0" encoding="UTF-8"?>
<idPkg:Story xmlns:idPkg="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging">
    <Story Self="story_body">
        <ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/Body">
            <CharacterStyleRange>
                <Content>Body text paragraph one.</Content>
            </CharacterStyleRange>
        </ParagraphStyleRange>
        <ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/Body">
            <CharacterStyleRange>
                <Content>Body text paragraph two.</Content>
            </CharacterStyleRange>
        </ParagraphStyleRange>
    </Story>
</idPkg:Story>'''
        zf.writestr('Stories/Story_body.xml', story_body)
    
    buffer.seek(0)
    return buffer.getvalue()


# ============================================================================
# Utility Fixtures
# ============================================================================

@pytest.fixture
def temp_output_dir(tmp_path):
    """Provide a temporary directory for output files."""
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    return output_dir


@pytest.fixture
def temp_input_dir(tmp_path):
    """Provide a temporary directory for input files."""
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    return input_dir


# ============================================================================
# Test Configuration
# ============================================================================

def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
