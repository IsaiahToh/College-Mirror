"""
Tests for content parser (Word document parsing).
"""

import pytest
from idml_layout_engine.content_parser import ContentParser
from idml_layout_engine.models import ContentType


class TestContentParser:
    """Tests for ContentParser class."""
    
    @pytest.fixture
    def parser(self):
        """Create a parser instance."""
        return ContentParser()
    
    def test_parser_initialization(self, parser):
        """Test parser initializes correctly."""
        assert parser is not None
    
    def test_detect_quote_paragraph_quotes(self, parser):
        """Test quote detection with actual quotes."""
        # Text with quotation marks
        assert parser._is_quote_paragraph('"This is a quote."') is True
        assert parser._is_quote_paragraph("'This is a quote.'") is True
        assert parser._is_quote_paragraph('"Smart quotes here"') is True
        assert parser._is_quote_paragraph("'Smart single quotes'") is True
    
    def test_detect_quote_paragraph_attribution(self, parser):
        """Test quote detection with attribution."""
        # Text with em dash attribution
        assert parser._is_quote_paragraph("— John Smith") is True
        assert parser._is_quote_paragraph("-- Jane Doe") is True
        assert parser._is_quote_paragraph("-Anonymous") is False  # Single dash not enough
    
    def test_detect_quote_paragraph_short_italic(self, parser):
        """Test quote detection for short text (often styled as italic in Word)."""
        # Short text under threshold (may be a quote)
        short_text = "Words of wisdom."
        # This depends on implementation - may need additional context
        assert parser._is_potential_quote_by_length(short_text, max_words=10) is True
    
    def test_detect_quote_paragraph_normal_text(self, parser):
        """Test that normal paragraphs are not detected as quotes."""
        normal = "This is a normal paragraph with regular text content."
        assert parser._is_quote_paragraph(normal) is False
    
    def test_classify_content_type_title(self, parser):
        """Test title classification by style."""
        # Heading styles
        assert parser._classify_by_style("Heading 1") == ContentType.TITLE
        assert parser._classify_by_style("Heading 2") == ContentType.TITLE
        assert parser._classify_by_style("Title") == ContentType.TITLE
    
    def test_classify_content_type_body(self, parser):
        """Test body classification by style."""
        # Normal body styles
        assert parser._classify_by_style("Normal") == ContentType.BODY
        assert parser._classify_by_style("Body Text") == ContentType.BODY
        assert parser._classify_by_style("First Paragraph") == ContentType.BODY
    
    def test_classify_content_type_quote(self, parser):
        """Test quote classification by style."""
        # Quote styles
        assert parser._classify_by_style("Quote") == ContentType.QUOTE
        assert parser._classify_by_style("Block Quote") == ContentType.QUOTE
        assert parser._classify_by_style("Intense Quote") == ContentType.QUOTE


class TestContentParserTextProcessing:
    """Tests for text processing in ContentParser."""
    
    @pytest.fixture
    def parser(self):
        return ContentParser()
    
    def test_normalize_whitespace(self, parser):
        """Test whitespace normalization."""
        text = "  Multiple   spaces   here  "
        normalized = parser._normalize_whitespace(text)
        
        assert normalized == "Multiple spaces here"
    
    def test_strip_control_characters(self, parser):
        """Test control character removal."""
        text = "Text\x00with\x01control\x02chars"
        cleaned = parser._strip_control_characters(text)
        
        assert "\x00" not in cleaned
        assert "\x01" not in cleaned
        assert "\x02" not in cleaned
    
    def test_preserve_paragraph_breaks(self, parser):
        """Test that paragraph breaks are preserved."""
        text = "Paragraph one.\n\nParagraph two."
        processed = parser._process_text(text)
        
        # Should preserve meaningful line breaks
        assert "Paragraph one" in processed
        assert "Paragraph two" in processed
    
    def test_handle_empty_text(self, parser):
        """Test handling of empty text."""
        assert parser._process_text("") == ""
        assert parser._process_text("   ") == ""
        assert parser._process_text("\n\n\n") == ""


class TestContentParserSectionDetection:
    """Tests for section detection in ContentParser."""
    
    @pytest.fixture
    def parser(self):
        return ContentParser()
    
    def test_detect_section_break_by_heading(self, parser):
        """Test section break detection by heading style."""
        assert parser._is_section_break("Heading 1", "Any text") is True
        assert parser._is_section_break("Heading 2", "Any text") is True
    
    def test_no_section_break_for_body(self, parser):
        """Test no section break for body paragraphs."""
        assert parser._is_section_break("Normal", "Body text") is False
        assert parser._is_section_break("Body Text", "More text") is False
    
    def test_section_grouping(self, parser):
        """Test that content is grouped by section."""
        # This would need actual paragraph data
        # Just verify the method exists
        assert hasattr(parser, '_group_by_sections')


class TestContentParserImageHandling:
    """Tests for image handling in ContentParser."""
    
    @pytest.fixture
    def parser(self):
        return ContentParser()
    
    def test_extract_image_paths(self, parser):
        """Test image path extraction method exists."""
        assert hasattr(parser, '_extract_images')
    
    def test_associate_images_with_sections(self, parser):
        """Test image-section association method exists."""
        assert hasattr(parser, '_associate_images_with_sections')
    
    def test_supported_image_formats(self, parser):
        """Test supported image format detection."""
        assert parser._is_supported_image("image.jpg") is True
        assert parser._is_supported_image("image.jpeg") is True
        assert parser._is_supported_image("image.png") is True
        assert parser._is_supported_image("image.tif") is True
        assert parser._is_supported_image("image.tiff") is True
        assert parser._is_supported_image("image.gif") is False  # Not typically supported in IDML
        assert parser._is_supported_image("document.pdf") is False


class TestContentParserOutput:
    """Tests for ContentParser output structure."""
    
    @pytest.fixture
    def parser(self):
        return ContentParser()
    
    def test_output_has_sections(self, parser):
        """Test that output contains sections."""
        # Verify the output structure method exists
        assert hasattr(parser, 'parse_docx')
    
    def test_content_block_structure(self, parser):
        """Test ContentBlock creation."""
        from idml_layout_engine.models import ContentBlock, ContentType
        
        block = ContentBlock(
            content_id="test_1",
            content_type=ContentType.BODY,
            text="Test content",
            section_title="Test Section",
            sequence_index=0,
        )
        
        assert block.content_id == "test_1"
        assert block.content_type == ContentType.BODY
        assert block.text == "Test content"
        assert block.section_title == "Test Section"
        assert block.sequence_index == 0
    
    def test_content_section_structure(self, parser):
        """Test ContentSection creation."""
        from idml_layout_engine.models import ContentBlock, ContentSection, ContentType
        
        title = ContentBlock(
            content_id="title_1",
            content_type=ContentType.TITLE,
            text="Section Title",
            section_title="Section Title",
            sequence_index=0,
        )
        
        body = ContentBlock(
            content_id="body_1",
            content_type=ContentType.BODY,
            text="Body text",
            section_title="Section Title",
            sequence_index=1,
        )
        
        section = ContentSection(
            section_id="section_1",
            title=title,
            body_blocks=[body],
            image_paths=["image.jpg"],
        )
        
        assert section.section_id == "section_1"
        assert section.title.text == "Section Title"
        assert len(section.body_blocks) == 1
        assert len(section.image_paths) == 1
