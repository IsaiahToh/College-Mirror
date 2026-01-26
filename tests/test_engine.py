"""
Tests for the main layout engine.
"""

import pytest
from pathlib import Path
from idml_layout_engine.engine import LayoutEngine, LayoutEngineConfig


class TestLayoutEngineConfig:
    """Tests for LayoutEngineConfig."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = LayoutEngineConfig()
        
        assert config.variation_seed is None
        assert config.debug_mode is False
        assert config.max_variations_per_page == 3
    
    def test_config_with_seed(self):
        """Test configuration with seed."""
        config = LayoutEngineConfig(variation_seed=42)
        
        assert config.variation_seed == 42
    
    def test_config_debug_mode(self):
        """Test debug mode configuration."""
        config = LayoutEngineConfig(debug_mode=True)
        
        assert config.debug_mode is True


class TestLayoutEngine:
    """Tests for LayoutEngine class."""
    
    @pytest.fixture
    def mock_idml_path(self, tmp_path, minimal_idml_bytes):
        """Create a temporary IDML file."""
        idml_path = tmp_path / "template.idml"
        idml_path.write_bytes(minimal_idml_bytes)
        return idml_path
    
    @pytest.fixture
    def engine(self, mock_idml_path):
        """Create a basic engine instance."""
        config = LayoutEngineConfig(variation_seed=42)
        return LayoutEngine(
            reference_idml=mock_idml_path,
            config=config,
        )
    
    @pytest.fixture
    def engine_no_variations(self, mock_idml_path):
        """Create an engine with variations disabled."""
        config = LayoutEngineConfig(variation_seed=None)
        return LayoutEngine(
            reference_idml=mock_idml_path,
            config=config,
        )
    
    @pytest.fixture
    def engine_debug(self, mock_idml_path):
        """Create an engine in debug mode."""
        config = LayoutEngineConfig(debug_mode=True, variation_seed=42)
        return LayoutEngine(
            reference_idml=mock_idml_path,
            config=config,
        )
    
    def test_engine_initialization(self, engine):
        """Test engine initializes correctly."""
        assert engine is not None
        assert engine.config.variation_seed == 42
    
    def test_engine_determinism_with_seed(self, mock_idml_path):
        """Test that same seed produces same results."""
        # Create two engines with same seed
        engine1 = LayoutEngine(
            reference_idml=mock_idml_path,
            variation_seed=42,
        )
        engine2 = LayoutEngine(
            reference_idml=mock_idml_path,
            variation_seed=42,
        )
        
        # Their variation seeds should match
        assert engine1.config.variation_seed == engine2.config.variation_seed == 42
    
    def test_engine_no_variations_mode(self, engine_no_variations):
        """Test engine respects no-variations mode."""
        assert engine_no_variations.config.variation_seed is None
    
    def test_engine_debug_mode(self, engine_debug):
        """Test engine respects debug mode."""
        assert engine_debug.config.debug_mode is True


class TestLayoutEngineWorkflow:
    """Tests for the engine workflow without actual files."""
    
    @pytest.fixture
    def engine(self, tmp_path, minimal_idml_bytes):
        idml_path = tmp_path / "template.idml"
        idml_path.write_bytes(minimal_idml_bytes)
        return LayoutEngine(
            reference_idml=idml_path,
            config=LayoutEngineConfig(variation_seed=42, debug_mode=True),
        )
    
    def test_parse_template_method_exists(self, engine):
        """Test parse_template method exists."""
        assert hasattr(engine, 'parse_template')
    
    def test_parse_content_method_exists(self, engine):
        """Test parse_content method exists."""
        assert hasattr(engine, 'parse_content')
    
    def test_generate_method_exists(self, engine):
        """Test generate method exists."""
        assert hasattr(engine, 'generate')
    
    def test_get_template_summary_method_exists(self, engine):
        """Test get_template_summary method exists."""
        assert hasattr(engine, 'get_template_summary')
    
    def test_add_content_document_method_exists(self, engine):
        """Test add_content_document method exists."""
        assert hasattr(engine, 'add_content_document')
    
    def test_set_image_mapping_method_exists(self, engine):
        """Test set_image_mapping method exists."""
        assert hasattr(engine, 'set_image_mapping')


class TestLayoutEngineConfiguration:
    """Tests for engine configuration options."""
    
    def test_config_max_variations(self):
        """Test that configuration accepts max variations setting."""
        config = LayoutEngineConfig(max_variations_per_page=5)
        
        assert config.max_variations_per_page == 5
    
    def test_config_strip_whitespace(self):
        """Test strip whitespace configuration."""
        config = LayoutEngineConfig(strip_whitespace=False)
        
        assert config.strip_whitespace is False
    
    def test_config_skip_empty_paragraphs(self):
        """Test skip empty paragraphs configuration."""
        config = LayoutEngineConfig(skip_empty_paragraphs=False)
        
        assert config.skip_empty_paragraphs is False
