"""
Tests for data models.
"""

import pytest
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
    PageInstance,
)


class TestFrameGeometry:
    """Tests for FrameGeometry class."""
    
    def test_create_valid_geometry(self):
        """Test creating a valid geometry."""
        geo = FrameGeometry(x=10.0, y=20.0, width=100.0, height=50.0)
        assert geo.x == 10.0
        assert geo.y == 20.0
        assert geo.width == 100.0
        assert geo.height == 50.0
    
    def test_computed_properties(self):
        """Test computed properties."""
        geo = FrameGeometry(x=10.0, y=20.0, width=100.0, height=50.0)
        assert geo.right == 110.0
        assert geo.bottom == 70.0
        assert geo.center_x == 60.0
        assert geo.center_y == 45.0
    
    def test_invalid_width_raises(self):
        """Test that invalid width raises ValueError."""
        with pytest.raises(ValueError, match="Width must be positive"):
            FrameGeometry(x=0, y=0, width=0, height=10)
    
    def test_invalid_height_raises(self):
        """Test that invalid height raises ValueError."""
        with pytest.raises(ValueError, match="Height must be positive"):
            FrameGeometry(x=0, y=0, width=10, height=-5)
    
    def test_contains_point(self):
        """Test point containment."""
        geo = FrameGeometry(x=10.0, y=20.0, width=100.0, height=50.0)
        assert geo.contains_point(50.0, 40.0)  # Inside
        assert geo.contains_point(10.0, 20.0)  # Corner
        assert not geo.contains_point(5.0, 40.0)  # Left of frame
        assert not geo.contains_point(50.0, 80.0)  # Below frame
    
    def test_intersects(self):
        """Test intersection detection."""
        geo1 = FrameGeometry(x=0, y=0, width=100, height=100)
        geo2 = FrameGeometry(x=50, y=50, width=100, height=100)  # Overlapping
        geo3 = FrameGeometry(x=200, y=200, width=50, height=50)  # Non-overlapping
        
        assert geo1.intersects(geo2)
        assert geo2.intersects(geo1)
        assert not geo1.intersects(geo3)
    
    def test_to_dict(self):
        """Test serialization."""
        geo = FrameGeometry(x=10.0, y=20.0, width=100.0, height=50.0)
        d = geo.to_dict()
        assert d == {"x": 10.0, "y": 20.0, "width": 100.0, "height": 50.0}
    
    def test_immutability(self):
        """Test that geometry is immutable (frozen dataclass)."""
        geo = FrameGeometry(x=10.0, y=20.0, width=100.0, height=50.0)
        with pytest.raises(AttributeError):
            geo.x = 50.0


class TestPageDimensions:
    """Tests for PageDimensions class."""
    
    def test_default_values(self):
        """Test default margin values."""
        dims = PageDimensions(width=612.0, height=792.0)
        assert dims.margin_top == 36.0
        assert dims.margin_bottom == 36.0
        assert dims.column_count == 2
    
    def test_content_dimensions(self):
        """Test content area calculations."""
        dims = PageDimensions(
            width=612.0,
            height=792.0,
            margin_top=36.0,
            margin_bottom=36.0,
            margin_inside=72.0,
            margin_outside=36.0,
        )
        assert dims.content_width == 612.0 - 72.0 - 36.0  # 504
        assert dims.content_height == 792.0 - 36.0 - 36.0  # 720
    
    def test_column_width(self):
        """Test column width calculation."""
        dims = PageDimensions(
            width=612.0,
            height=792.0,
            margin_inside=36.0,
            margin_outside=36.0,
            column_count=2,
            column_gutter=12.0,
        )
        # Content width = 612 - 36 - 36 = 540
        # Column width = (540 - 12) / 2 = 264
        assert dims.column_width == 264.0
    
    def test_get_column_x(self):
        """Test column X position calculation."""
        dims = PageDimensions(
            width=612.0,
            height=792.0,
            margin_inside=36.0,
            margin_outside=36.0,
            column_count=2,
            column_gutter=12.0,
        )
        # First column starts at inside margin
        assert dims.get_column_x(0, is_left_page=True) == 36.0
        # Second column starts after first column + gutter
        assert dims.get_column_x(1, is_left_page=True) == 36.0 + 264.0 + 12.0


class TestSlot:
    """Tests for Slot class."""
    
    def test_create_slot(self):
        """Test creating a valid slot."""
        geo = FrameGeometry(x=36.0, y=72.0, width=200.0, height=100.0)
        slot = Slot(
            slot_id="slot_1",
            slot_type=SlotType.PARAGRAPH,
            geometry=geo,
            column_index=0,
            vertical_position=VerticalPosition.TOP,
        )
        assert slot.slot_id == "slot_1"
        assert slot.slot_type == SlotType.PARAGRAPH
        assert slot.column_index == 0
    
    def test_invalid_column_index(self):
        """Test that negative column index raises."""
        geo = FrameGeometry(x=0, y=0, width=100, height=100)
        with pytest.raises(ValueError, match="Column index must be non-negative"):
            Slot(
                slot_id="test",
                slot_type=SlotType.PARAGRAPH,
                geometry=geo,
                column_index=-1,
                vertical_position=VerticalPosition.TOP,
            )
    
    def test_is_compatible_with(self):
        """Test slot compatibility."""
        geo = FrameGeometry(x=0, y=0, width=100, height=100)
        
        slot1 = Slot(
            slot_id="s1",
            slot_type=SlotType.IMAGE,
            geometry=geo,
            column_index=0,
            vertical_position=VerticalPosition.TOP,
            paragraph_units=1.0,
        )
        
        slot2 = Slot(
            slot_id="s2",
            slot_type=SlotType.IMAGE,
            geometry=geo,
            column_index=1,
            vertical_position=VerticalPosition.TOP,
            paragraph_units=1.1,  # Similar size
        )
        
        slot3 = Slot(
            slot_id="s3",
            slot_type=SlotType.IMAGE,
            geometry=geo,
            column_index=0,
            vertical_position=VerticalPosition.BOTTOM,  # Different position
            paragraph_units=1.0,
        )
        
        assert slot1.is_compatible_with(slot2)
        assert not slot1.is_compatible_with(slot3)  # Different vertical position
    
    def test_fixed_slot_not_compatible(self):
        """Test that fixed slots are not compatible."""
        geo = FrameGeometry(x=0, y=0, width=100, height=100)
        
        slot1 = Slot(
            slot_id="s1",
            slot_type=SlotType.IMAGE,
            geometry=geo,
            column_index=0,
            vertical_position=VerticalPosition.TOP,
            is_fixed=True,
        )
        
        slot2 = Slot(
            slot_id="s2",
            slot_type=SlotType.IMAGE,
            geometry=geo,
            column_index=1,
            vertical_position=VerticalPosition.TOP,
        )
        
        assert not slot1.is_compatible_with(slot2)


class TestLayoutTemplate:
    """Tests for LayoutTemplate class."""
    
    def test_create_template(self):
        """Test creating a template."""
        dims = PageDimensions(width=612.0, height=792.0)
        template = LayoutTemplate(
            template_id="test_template",
            page_dimensions=dims,
        )
        assert template.template_id == "test_template"
        assert len(template.slots) == 0
    
    def test_add_slot(self):
        """Test adding slots to template."""
        dims = PageDimensions(width=612.0, height=792.0)
        template = LayoutTemplate(
            template_id="test_template",
            page_dimensions=dims,
        )
        
        geo = FrameGeometry(x=0, y=0, width=100, height=100)
        slot = Slot(
            slot_id="slot_1",
            slot_type=SlotType.PARAGRAPH,
            geometry=geo,
            column_index=0,
            vertical_position=VerticalPosition.TOP,
        )
        
        template.add_slot(slot)
        assert len(template.slots) == 1
        assert template.get_slot("slot_1") == slot
    
    def test_get_slots_by_type(self):
        """Test filtering slots by type."""
        dims = PageDimensions(width=612.0, height=792.0)
        template = LayoutTemplate(
            template_id="test_template",
            page_dimensions=dims,
        )
        
        geo = FrameGeometry(x=0, y=0, width=100, height=100)
        
        template.add_slot(Slot(
            slot_id="para_1",
            slot_type=SlotType.PARAGRAPH,
            geometry=geo,
            column_index=0,
            vertical_position=VerticalPosition.TOP,
        ))
        template.add_slot(Slot(
            slot_id="image_1",
            slot_type=SlotType.IMAGE,
            geometry=geo,
            column_index=0,
            vertical_position=VerticalPosition.TOP,
        ))
        
        para_slots = template.get_slots_by_type(SlotType.PARAGRAPH)
        assert len(para_slots) == 1
        assert para_slots[0].slot_id == "para_1"


class TestContentBlock:
    """Tests for ContentBlock class."""
    
    def test_create_content_block(self):
        """Test creating a content block."""
        block = ContentBlock(
            content_id="block_1",
            content_type=ContentType.BODY,
            text="This is paragraph text.",
            section_title="Test Section",
            sequence_index=1,
        )
        assert block.content_id == "block_1"
        assert block.content_type == ContentType.BODY
        assert block.sequence_index == 1
    
    def test_invalid_sequence_index(self):
        """Test that negative sequence index raises."""
        with pytest.raises(ValueError, match="Sequence index must be non-negative"):
            ContentBlock(
                content_id="block_1",
                content_type=ContentType.BODY,
                text="Text",
                section_title="Title",
                sequence_index=-1,
            )


class TestContentSection:
    """Tests for ContentSection class."""
    
    def test_create_section(self):
        """Test creating a content section."""
        title = ContentBlock(
            content_id="title_1",
            content_type=ContentType.TITLE,
            text="Section Title",
            section_title="Section Title",
            sequence_index=0,
        )
        
        section = ContentSection(
            section_id="section_1",
            title=title,
        )
        
        assert section.section_id == "section_1"
        assert section.title.text == "Section Title"
    
    def test_get_quotes(self):
        """Test filtering quotes from body blocks."""
        title = ContentBlock(
            content_id="title",
            content_type=ContentType.TITLE,
            text="Title",
            section_title="Title",
            sequence_index=0,
        )
        
        body1 = ContentBlock(
            content_id="body_1",
            content_type=ContentType.BODY,
            text="Body text",
            section_title="Title",
            sequence_index=1,
        )
        
        quote1 = ContentBlock(
            content_id="quote_1",
            content_type=ContentType.QUOTE,
            text="Quote text",
            section_title="Title",
            sequence_index=2,
        )
        
        section = ContentSection(
            section_id="section_1",
            title=title,
            body_blocks=[body1, quote1],
        )
        
        quotes = section.get_quotes()
        assert len(quotes) == 1
        assert quotes[0].content_id == "quote_1"


class TestPageInstance:
    """Tests for PageInstance class."""
    
    def test_create_page(self):
        """Test creating a page instance."""
        page = PageInstance(
            page_id="page_1",
            page_number=1,
            spread_index=0,
            is_left_page=True,
        )
        assert page.page_number == 1
        assert page.is_left_page
    
    def test_invalid_page_number(self):
        """Test that page number < 1 raises."""
        with pytest.raises(ValueError, match="Page number must be >= 1"):
            PageInstance(
                page_id="page_0",
                page_number=0,
                spread_index=0,
                is_left_page=True,
            )
    
    def test_add_assignment(self):
        """Test adding slot assignments."""
        page = PageInstance(
            page_id="page_1",
            page_number=1,
            spread_index=0,
            is_left_page=True,
        )
        
        geo = FrameGeometry(x=0, y=0, width=100, height=100)
        slot = Slot(
            slot_id="slot_1",
            slot_type=SlotType.PARAGRAPH,
            geometry=geo,
            column_index=0,
            vertical_position=VerticalPosition.TOP,
        )
        
        content = ContentBlock(
            content_id="block_1",
            content_type=ContentType.BODY,
            text="Text",
            section_title="Title",
            sequence_index=1,
        )
        
        page.add_assignment(slot, content)
        assert len(page.assignments) == 1
        assert "slot_1" in page.get_slots_used()
