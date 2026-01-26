"""
Tests for algorithms module.
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
)
from idml_layout_engine.algorithms import (
    detect_column,
    detect_column_with_overlap,
    compute_vertical_position,
    compute_normalized_y,
    sort_frames_vertically,
    group_interchangeable_slots,
    compute_content_size,
    find_best_slot,
    assign_content_to_slots,
    estimate_text_flow,
    will_text_fit,
)


class TestColumnDetection:
    """Tests for column detection algorithms."""
    
    @pytest.fixture
    def page_dims(self):
        """Standard two-column page dimensions."""
        return PageDimensions(
            width=612.0,  # US Letter width
            height=792.0,
            margin_inside=36.0,
            margin_outside=36.0,
            margin_top=36.0,
            margin_bottom=36.0,
            column_count=2,
            column_gutter=12.0,
        )
    
    def test_detect_left_column(self, page_dims):
        """Test detecting frame in left column."""
        # Frame clearly in left column
        geo = FrameGeometry(x=50.0, y=100.0, width=200.0, height=100.0)
        column = detect_column(geo, page_dims)
        assert column == 0
    
    def test_detect_right_column(self, page_dims):
        """Test detecting frame in right column."""
        # Frame clearly in right column (right side of page)
        geo = FrameGeometry(x=350.0, y=100.0, width=200.0, height=100.0)
        column = detect_column(geo, page_dims)
        assert column == 1
    
    def test_detect_column_with_overlap_high(self, page_dims):
        """Test column detection with high overlap."""
        # Frame fully in first column
        geo = FrameGeometry(x=40.0, y=100.0, width=200.0, height=100.0)
        column, overlap = detect_column_with_overlap(geo, page_dims)
        assert column == 0
        assert overlap > 0.8  # High overlap
    
    def test_detect_column_spanning(self, page_dims):
        """Test frame spanning multiple columns."""
        # Frame spanning center of page
        geo = FrameGeometry(x=200.0, y=100.0, width=200.0, height=100.0)
        column, overlap = detect_column_with_overlap(geo, page_dims)
        # Should return the column with more overlap
        assert column in [0, 1]
        assert overlap < 1.0  # Not fully in one column


class TestVerticalPosition:
    """Tests for vertical position algorithms."""
    
    @pytest.fixture
    def page_dims(self):
        return PageDimensions(width=612.0, height=792.0)
    
    def test_top_position(self, page_dims):
        """Test detecting top position."""
        geo = FrameGeometry(x=50.0, y=50.0, width=100.0, height=50.0)
        pos = compute_vertical_position(geo, page_dims)
        assert pos == VerticalPosition.TOP
    
    def test_middle_position(self, page_dims):
        """Test detecting middle position."""
        geo = FrameGeometry(x=50.0, y=350.0, width=100.0, height=50.0)
        pos = compute_vertical_position(geo, page_dims)
        assert pos == VerticalPosition.MIDDLE
    
    def test_bottom_position(self, page_dims):
        """Test detecting bottom position."""
        geo = FrameGeometry(x=50.0, y=650.0, width=100.0, height=50.0)
        pos = compute_vertical_position(geo, page_dims)
        assert pos == VerticalPosition.BOTTOM
    
    def test_normalized_y(self, page_dims):
        """Test normalized Y computation."""
        geo = FrameGeometry(x=50.0, y=396.0, width=100.0, height=50.0)
        normalized = compute_normalized_y(geo, page_dims)
        assert 0.4 < normalized < 0.6  # Middle of page
    
    def test_sort_frames_vertically(self, page_dims):
        """Test vertical sorting of frames."""
        frames = [
            FrameGeometry(x=50.0, y=500.0, width=100.0, height=50.0),
            FrameGeometry(x=50.0, y=100.0, width=100.0, height=50.0),
            FrameGeometry(x=50.0, y=300.0, width=100.0, height=50.0),
        ]
        
        sorted_frames = sort_frames_vertically(frames, page_dims)
        
        # Should be sorted by Y: 100, 300, 500
        assert sorted_frames[0][0] == 1  # Original index 1 (y=100) first
        assert sorted_frames[1][0] == 2  # Original index 2 (y=300) second
        assert sorted_frames[2][0] == 0  # Original index 0 (y=500) last


class TestSlotGrouping:
    """Tests for slot grouping algorithms."""
    
    def test_group_compatible_slots(self):
        """Test grouping compatible slots."""
        geo = FrameGeometry(x=0, y=0, width=100, height=100)
        
        slots = [
            Slot(
                slot_id="img_0",
                slot_type=SlotType.IMAGE,
                geometry=geo,
                column_index=0,
                vertical_position=VerticalPosition.TOP,
                paragraph_units=1.0,
            ),
            Slot(
                slot_id="img_1",
                slot_type=SlotType.IMAGE,
                geometry=geo,
                column_index=1,
                vertical_position=VerticalPosition.TOP,
                paragraph_units=1.0,
            ),
        ]
        
        groups = group_interchangeable_slots(slots)
        
        # Should create one group with both image slots
        assert len(groups) == 1
        group_slots = list(groups.values())[0]
        assert "img_0" in group_slots
        assert "img_1" in group_slots
    
    def test_no_group_different_types(self):
        """Test that different types don't group."""
        geo = FrameGeometry(x=0, y=0, width=100, height=100)
        
        slots = [
            Slot(
                slot_id="img_0",
                slot_type=SlotType.IMAGE,
                geometry=geo,
                column_index=0,
                vertical_position=VerticalPosition.TOP,
            ),
            Slot(
                slot_id="para_0",
                slot_type=SlotType.PARAGRAPH,
                geometry=geo,
                column_index=1,
                vertical_position=VerticalPosition.TOP,
            ),
        ]
        
        groups = group_interchangeable_slots(slots)
        
        # Should not create any groups (different types)
        assert len(groups) == 0
    
    def test_no_group_fixed_slots(self):
        """Test that fixed slots don't group."""
        geo = FrameGeometry(x=0, y=0, width=100, height=100)
        
        slots = [
            Slot(
                slot_id="img_0",
                slot_type=SlotType.IMAGE,
                geometry=geo,
                column_index=0,
                vertical_position=VerticalPosition.TOP,
                is_fixed=True,
            ),
            Slot(
                slot_id="img_1",
                slot_type=SlotType.IMAGE,
                geometry=geo,
                column_index=1,
                vertical_position=VerticalPosition.TOP,
            ),
        ]
        
        groups = group_interchangeable_slots(slots)
        
        # Should not create groups (one is fixed)
        assert len(groups) == 0


class TestContentSizing:
    """Tests for content size estimation."""
    
    def test_compute_content_size_short(self):
        """Test size of short content."""
        content = ContentBlock(
            content_id="test",
            content_type=ContentType.BODY,
            text="Short text",
            section_title="Title",
            sequence_index=1,
        )
        
        size = compute_content_size(content)
        assert size == 1.0  # Minimum size
    
    def test_compute_content_size_long(self):
        """Test size of long content."""
        content = ContentBlock(
            content_id="test",
            content_type=ContentType.BODY,
            text="A" * 1500,  # 1500 characters
            section_title="Title",
            sequence_index=1,
        )
        
        size = compute_content_size(content, chars_per_unit=500)
        assert size == 3.0  # 1500 / 500 = 3
    
    def test_will_text_fit(self):
        """Test text fitting check."""
        geo = FrameGeometry(x=0, y=0, width=100, height=100)
        
        small_slot = Slot(
            slot_id="small",
            slot_type=SlotType.PARAGRAPH,
            geometry=geo,
            column_index=0,
            vertical_position=VerticalPosition.TOP,
            paragraph_units=1.0,
        )
        
        small_content = ContentBlock(
            content_id="test",
            content_type=ContentType.BODY,
            text="Short text",
            section_title="Title",
            sequence_index=1,
        )
        
        large_content = ContentBlock(
            content_id="test",
            content_type=ContentType.BODY,
            text="A" * 2000,  # Very long
            section_title="Title",
            sequence_index=1,
        )
        
        assert will_text_fit(small_content, small_slot)
        assert not will_text_fit(large_content, small_slot)


class TestSlotAssignment:
    """Tests for content-to-slot assignment."""
    
    @pytest.fixture
    def template(self):
        """Create a simple template with various slots."""
        dims = PageDimensions(width=612.0, height=792.0)
        template = LayoutTemplate(template_id="test", page_dimensions=dims)
        
        geo = FrameGeometry(x=0, y=0, width=200, height=100)
        
        template.add_slot(Slot(
            slot_id="title_0",
            slot_type=SlotType.TITLE,
            geometry=geo,
            column_index=0,
            vertical_position=VerticalPosition.TOP,
        ))
        
        template.add_slot(Slot(
            slot_id="para_0",
            slot_type=SlotType.PARAGRAPH,
            geometry=geo,
            column_index=0,
            vertical_position=VerticalPosition.MIDDLE,
        ))
        
        template.add_slot(Slot(
            slot_id="quote_0",
            slot_type=SlotType.QUOTE,
            geometry=geo,
            column_index=1,
            vertical_position=VerticalPosition.MIDDLE,
        ))
        
        return template
    
    def test_find_best_slot_by_type(self, template):
        """Test finding slot matching content type."""
        content = ContentBlock(
            content_id="test",
            content_type=ContentType.TITLE,
            text="Title Text",
            section_title="Title",
            sequence_index=0,
        )
        
        available = template.slots
        slot = find_best_slot(content, available)
        
        assert slot is not None
        assert slot.slot_type == SlotType.TITLE
    
    def test_find_best_slot_respects_preference(self, template):
        """Test slot finding with column preference."""
        # Add second paragraph slot in column 1
        geo = FrameGeometry(x=0, y=0, width=200, height=100)
        template.add_slot(Slot(
            slot_id="para_1",
            slot_type=SlotType.PARAGRAPH,
            geometry=geo,
            column_index=1,
            vertical_position=VerticalPosition.MIDDLE,
        ))
        
        content = ContentBlock(
            content_id="test",
            content_type=ContentType.BODY,
            text="Body text",
            section_title="Title",
            sequence_index=1,
        )
        
        available = template.slots
        slot = find_best_slot(content, available, prefer_column=1)
        
        assert slot is not None
        assert slot.column_index == 1


class TestTextFlowEstimation:
    """Tests for text flow estimation."""
    
    def test_estimate_flow_fits(self):
        """Test flow estimation when content fits."""
        dims = PageDimensions(width=612.0, height=792.0)
        template = LayoutTemplate(template_id="test", page_dimensions=dims)
        
        geo = FrameGeometry(x=0, y=0, width=200, height=100)
        template.add_slot(Slot(
            slot_id="para_0",
            slot_type=SlotType.PARAGRAPH,
            geometry=geo,
            column_index=0,
            vertical_position=VerticalPosition.MIDDLE,
            paragraph_units=5.0,
        ))
        
        content = [
            ContentBlock(
                content_id="test",
                content_type=ContentType.BODY,
                text="Short content",
                section_title="Title",
                sequence_index=1,
            )
        ]
        
        estimate = estimate_text_flow(content, template)
        
        assert estimate.overflow_units == 0
        assert estimate.fill_ratio < 1.0
        assert estimate.pages_needed == 1
    
    def test_estimate_flow_overflow(self):
        """Test flow estimation with overflow."""
        dims = PageDimensions(width=612.0, height=792.0)
        template = LayoutTemplate(template_id="test", page_dimensions=dims)
        
        geo = FrameGeometry(x=0, y=0, width=200, height=100)
        template.add_slot(Slot(
            slot_id="para_0",
            slot_type=SlotType.PARAGRAPH,
            geometry=geo,
            column_index=0,
            vertical_position=VerticalPosition.MIDDLE,
            paragraph_units=1.0,  # Small slot
        ))
        
        content = [
            ContentBlock(
                content_id="test",
                content_type=ContentType.BODY,
                text="A" * 3000,  # Large content
                section_title="Title",
                sequence_index=1,
            )
        ]
        
        estimate = estimate_text_flow(content, template)
        
        assert estimate.overflow_units > 0
        assert estimate.fill_ratio > 1.0
        assert estimate.pages_needed > 1
