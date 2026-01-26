"""
Tests for variation engine.
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
    SlotAssignment,
)
from idml_layout_engine.variation import (
    VariationEngine,
    VariationRule,
    VariationOperation,
    SlotAssigner,
    DEFAULT_VARIATION_RULES,
)


class TestVariationRule:
    """Tests for VariationRule class."""
    
    def test_applies_to_matching_slot(self):
        """Test that rule applies to matching slot."""
        rule = VariationRule(
            rule_id="test",
            slot_type=SlotType.IMAGE,
            allowed_vertical_positions={VerticalPosition.TOP},
        )
        
        geo = FrameGeometry(x=0, y=0, width=100, height=100)
        slot = Slot(
            slot_id="test",
            slot_type=SlotType.IMAGE,
            geometry=geo,
            column_index=0,
            vertical_position=VerticalPosition.TOP,
        )
        
        assert rule.applies_to(slot)
    
    def test_not_applies_wrong_type(self):
        """Test that rule doesn't apply to wrong type."""
        rule = VariationRule(
            rule_id="test",
            slot_type=SlotType.IMAGE,
        )
        
        geo = FrameGeometry(x=0, y=0, width=100, height=100)
        slot = Slot(
            slot_id="test",
            slot_type=SlotType.PARAGRAPH,
            geometry=geo,
            column_index=0,
            vertical_position=VerticalPosition.TOP,
        )
        
        assert not rule.applies_to(slot)
    
    def test_not_applies_fixed_slot(self):
        """Test that rule doesn't apply to fixed slots."""
        rule = VariationRule(
            rule_id="test",
            slot_type=SlotType.IMAGE,
        )
        
        geo = FrameGeometry(x=0, y=0, width=100, height=100)
        slot = Slot(
            slot_id="test",
            slot_type=SlotType.IMAGE,
            geometry=geo,
            column_index=0,
            vertical_position=VerticalPosition.TOP,
            is_fixed=True,
        )
        
        assert not rule.applies_to(slot)
    
    def test_not_applies_wrong_position(self):
        """Test that rule doesn't apply to wrong vertical position."""
        rule = VariationRule(
            rule_id="test",
            slot_type=SlotType.IMAGE,
            allowed_vertical_positions={VerticalPosition.TOP},
        )
        
        geo = FrameGeometry(x=0, y=0, width=100, height=100)
        slot = Slot(
            slot_id="test",
            slot_type=SlotType.IMAGE,
            geometry=geo,
            column_index=0,
            vertical_position=VerticalPosition.BOTTOM,
        )
        
        assert not rule.applies_to(slot)


class TestVariationEngine:
    """Tests for VariationEngine class."""
    
    @pytest.fixture
    def template_with_swappable_images(self):
        """Create template with swappable image slots."""
        dims = PageDimensions(width=612.0, height=792.0)
        template = LayoutTemplate(template_id="test", page_dimensions=dims)
        
        geo = FrameGeometry(x=0, y=50, width=200, height=100)
        
        # Two image slots in different columns, same position
        template.add_slot(Slot(
            slot_id="img_left",
            slot_type=SlotType.IMAGE,
            geometry=geo,
            column_index=0,
            vertical_position=VerticalPosition.TOP,
            paragraph_units=1.0,
        ))
        
        template.add_slot(Slot(
            slot_id="img_right",
            slot_type=SlotType.IMAGE,
            geometry=FrameGeometry(x=300, y=50, width=200, height=100),
            column_index=1,
            vertical_position=VerticalPosition.TOP,
            paragraph_units=1.0,
        ))
        
        return template
    
    @pytest.fixture
    def sample_assignments(self, template_with_swappable_images):
        """Create sample assignments."""
        template = template_with_swappable_images
        
        content_left = ContentBlock(
            content_id="img_content_1",
            content_type=ContentType.BODY,
            text="",
            section_title="Section 1",
            sequence_index=0,
            image_path="image1.jpg",
        )
        
        content_right = ContentBlock(
            content_id="img_content_2",
            content_type=ContentType.BODY,
            text="",
            section_title="Section 2",
            sequence_index=0,
            image_path="image2.jpg",
        )
        
        return {
            "img_left": SlotAssignment(
                slot=template.get_slot("img_left"),
                content=content_left,
            ),
            "img_right": SlotAssignment(
                slot=template.get_slot("img_right"),
                content=content_right,
            ),
        }
    
    def test_engine_initialization_with_seed(self):
        """Test engine initializes with seed."""
        engine = VariationEngine(seed=42)
        assert engine.seed == 42
    
    def test_engine_reset(self):
        """Test engine reset functionality."""
        engine = VariationEngine(seed=42)
        engine.operations.append(VariationOperation(
            operation_id="test",
            rule_id="test",
            slot_a_id="a",
            slot_b_id="b",
            description="test",
        ))
        
        engine.reset()
        assert len(engine.operations) == 0
    
    def test_deterministic_with_same_seed(self, template_with_swappable_images, sample_assignments):
        """Test that same seed produces same results."""
        template = template_with_swappable_images
        
        # Create rules that will definitely apply
        rules = [
            VariationRule(
                rule_id="force_swap",
                slot_type=SlotType.IMAGE,
                allowed_vertical_positions={VerticalPosition.TOP},
                cross_column_only=True,
                probability=1.0,  # Always apply
            ),
        ]
        
        # Run twice with same seed
        engine1 = VariationEngine(seed=42, rules=rules)
        result1, ops1 = engine1.apply_variations(template, sample_assignments)
        
        engine2 = VariationEngine(seed=42, rules=rules)
        result2, ops2 = engine2.apply_variations(template, sample_assignments)
        
        # Should produce identical results
        assert len(ops1) == len(ops2)
        for op1, op2 in zip(ops1, ops2):
            assert op1.applied == op2.applied
            assert op1.slot_a_id == op2.slot_a_id
            assert op1.slot_b_id == op2.slot_b_id
    
    def test_different_seeds_can_produce_different_results(
        self, 
        template_with_swappable_images, 
        sample_assignments
    ):
        """Test that different seeds can produce different results."""
        template = template_with_swappable_images
        
        rules = [
            VariationRule(
                rule_id="maybe_swap",
                slot_type=SlotType.IMAGE,
                allowed_vertical_positions={VerticalPosition.TOP},
                cross_column_only=True,
                probability=0.5,  # 50% chance
            ),
        ]
        
        # Run with many different seeds and check for variation
        results = []
        for seed in range(100):
            engine = VariationEngine(seed=seed, rules=rules)
            _, ops = engine.apply_variations(template, sample_assignments)
            applied_count = len([op for op in ops if op.applied])
            results.append(applied_count)
        
        # Should have some variation (not all same)
        unique_results = set(results)
        assert len(unique_results) > 1
    
    def test_variation_report(self, template_with_swappable_images, sample_assignments):
        """Test variation report generation."""
        template = template_with_swappable_images
        engine = VariationEngine(seed=42)
        engine.apply_variations(template, sample_assignments)
        
        report = engine.get_variation_report()
        
        assert "seed=42" in report
        assert "Applied:" in report
    
    def test_no_variations_with_empty_template(self):
        """Test that empty template produces no variations."""
        dims = PageDimensions(width=612.0, height=792.0)
        template = LayoutTemplate(template_id="empty", page_dimensions=dims)
        
        engine = VariationEngine(seed=42)
        _, ops = engine.apply_variations(template, {})
        
        assert len(ops) == 0


class TestSlotAssigner:
    """Tests for SlotAssigner class."""
    
    @pytest.fixture
    def template(self):
        """Create a template for assignment testing."""
        dims = PageDimensions(width=612.0, height=792.0)
        template = LayoutTemplate(template_id="test", page_dimensions=dims)
        
        geo = FrameGeometry(x=0, y=0, width=200, height=50)
        
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
            geometry=FrameGeometry(x=0, y=100, width=200, height=200),
            column_index=0,
            vertical_position=VerticalPosition.MIDDLE,
        ))
        
        template.add_slot(Slot(
            slot_id="para_1",
            slot_type=SlotType.PARAGRAPH,
            geometry=FrameGeometry(x=300, y=100, width=200, height=200),
            column_index=1,
            vertical_position=VerticalPosition.MIDDLE,
        ))
        
        template.add_slot(Slot(
            slot_id="quote_0",
            slot_type=SlotType.QUOTE,
            geometry=FrameGeometry(x=300, y=350, width=200, height=100),
            column_index=1,
            vertical_position=VerticalPosition.BOTTOM,
        ))
        
        template.add_slot(Slot(
            slot_id="image_0",
            slot_type=SlotType.IMAGE,
            geometry=FrameGeometry(x=0, y=350, width=200, height=200),
            column_index=0,
            vertical_position=VerticalPosition.BOTTOM,
        ))
        
        return template
    
    @pytest.fixture
    def content_sections(self):
        """Create content sections for testing."""
        from idml_layout_engine.models import ContentSection
        
        title = ContentBlock(
            content_id="title_1",
            content_type=ContentType.TITLE,
            text="Test Section Title",
            section_title="Test Section Title",
            sequence_index=0,
        )
        
        body1 = ContentBlock(
            content_id="body_1",
            content_type=ContentType.BODY,
            text="First body paragraph with some text.",
            section_title="Test Section Title",
            sequence_index=1,
        )
        
        quote1 = ContentBlock(
            content_id="quote_1",
            content_type=ContentType.QUOTE,
            text="A meaningful quote.",
            section_title="Test Section Title",
            sequence_index=2,
        )
        
        body2 = ContentBlock(
            content_id="body_2",
            content_type=ContentType.BODY,
            text="Second body paragraph.",
            section_title="Test Section Title",
            sequence_index=3,
        )
        
        section = ContentSection(
            section_id="section_1",
            title=title,
            body_blocks=[body1, quote1, body2],
            image_paths=["test_image.jpg"],
        )
        
        return [section]
    
    def test_assign_content(self, template, content_sections):
        """Test basic content assignment."""
        assigner = SlotAssigner(template)
        assignments = assigner.assign_content(content_sections)
        
        # Should have assignments
        assert len(assignments) > 0
    
    def test_title_assigned_to_title_slot(self, template, content_sections):
        """Test that title content goes to title slot."""
        assigner = SlotAssigner(template)
        assignments = assigner.assign_content(content_sections)
        
        # Find the title assignment
        title_assignment = None
        for slot_id, assignment in assignments.items():
            if assignment.content.content_type == ContentType.TITLE:
                title_assignment = assignment
                break
        
        assert title_assignment is not None
        assert title_assignment.slot.slot_type == SlotType.TITLE
    
    def test_quote_assigned_to_quote_slot(self, template, content_sections):
        """Test that quote content goes to quote slot."""
        assigner = SlotAssigner(template)
        assignments = assigner.assign_content(content_sections)
        
        # Find quote assignments
        quote_assignments = [
            a for a in assignments.values()
            if a.content.content_type == ContentType.QUOTE
        ]
        
        assert len(quote_assignments) > 0
        assert quote_assignments[0].slot.slot_type == SlotType.QUOTE
    
    def test_image_assigned_to_image_slot(self, template, content_sections):
        """Test that image content goes to image slot."""
        assigner = SlotAssigner(template)
        assignments = assigner.assign_content(content_sections)
        
        # Find image assignments
        image_assignments = [
            a for a in assignments.values()
            if a.content.image_path
        ]
        
        assert len(image_assignments) > 0
        assert image_assignments[0].slot.slot_type == SlotType.IMAGE
    
    def test_no_duplicate_slot_assignments(self, template, content_sections):
        """Test that each slot is assigned at most once."""
        assigner = SlotAssigner(template)
        assignments = assigner.assign_content(content_sections)
        
        # Check for duplicate slot IDs
        slot_ids = list(assignments.keys())
        assert len(slot_ids) == len(set(slot_ids))
    
    def test_empty_content_produces_no_assignments(self, template):
        """Test that empty content produces no assignments."""
        assigner = SlotAssigner(template)
        assignments = assigner.assign_content([])
        
        assert len(assignments) == 0
