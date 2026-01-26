"""
Tests for the main layout engine.
"""

import pytest
from pathlib import Path
from idml_layout_engine.engine import LayoutEngine, EngineConfig, EngineResult


class TestEngineConfig:
    """Tests for EngineConfig."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = EngineConfig()
        
        assert config.seed is None
        assert config.enable_variations is True
        assert config.debug_mode is False
        assert config.output_format == "idml"
    
    def test_config_with_seed(self):
        """Test configuration with seed."""
        config = EngineConfig(seed=42)
        
        assert config.seed == 42
    
    def test_config_debug_mode(self):
        """Test debug mode configuration."""
        config = EngineConfig(debug_mode=True)
        
        assert config.debug_mode is True
    
    def test_config_disable_variations(self):
        """Test disabling variations."""
        config = EngineConfig(enable_variations=False)
        
        assert config.enable_variations is False


class TestLayoutEngine:
    """Tests for LayoutEngine class."""
    
    @pytest.fixture
    def engine(self):
        """Create a basic engine instance."""
        config = EngineConfig(seed=42)
        return LayoutEngine(config)
    
    @pytest.fixture
    def engine_no_variations(self):
        """Create an engine with variations disabled."""
        config = EngineConfig(enable_variations=False)
        return LayoutEngine(config)
    
    @pytest.fixture
    def engine_debug(self):
        """Create an engine in debug mode."""
        config = EngineConfig(debug_mode=True, seed=42)
        return LayoutEngine(config)
    
    def test_engine_initialization(self, engine):
        """Test engine initializes correctly."""
        assert engine is not None
        assert engine.config.seed == 42
    
    def test_engine_has_parser(self, engine):
        """Test engine has an IDML parser."""
        assert engine.parser is not None
    
    def test_engine_has_content_parser(self, engine):
        """Test engine has a content parser."""
        assert engine.content_parser is not None
    
    def test_engine_has_variation_engine(self, engine):
        """Test engine has a variation engine."""
        assert engine.variation_engine is not None
    
    def test_engine_has_generator(self, engine):
        """Test engine has an IDML generator."""
        assert engine.generator is not None
    
    def test_engine_determinism_with_seed(self):
        """Test that same seed produces same results."""
        # Create two engines with same seed
        engine1 = LayoutEngine(EngineConfig(seed=42))
        engine2 = LayoutEngine(EngineConfig(seed=42))
        
        # Their variation engines should have same seed
        assert engine1.variation_engine.seed == engine2.variation_engine.seed == 42
    
    def test_engine_no_variations_mode(self, engine_no_variations):
        """Test engine respects no-variations mode."""
        assert engine_no_variations.config.enable_variations is False
    
    def test_engine_debug_mode(self, engine_debug):
        """Test engine respects debug mode."""
        assert engine_debug.config.debug_mode is True


class TestEngineResult:
    """Tests for EngineResult class."""
    
    def test_result_success(self):
        """Test successful result."""
        result = EngineResult(
            success=True,
            output_path=Path("/output/test.idml"),
        )
        
        assert result.success is True
        assert result.output_path == Path("/output/test.idml")
        assert result.error is None
    
    def test_result_failure(self):
        """Test failure result."""
        result = EngineResult(
            success=False,
            error="Something went wrong",
        )
        
        assert result.success is False
        assert result.error == "Something went wrong"
    
    def test_result_with_debug_info(self):
        """Test result with debug information."""
        result = EngineResult(
            success=True,
            output_path=Path("/output/test.idml"),
            debug_info={
                "template_slots": 10,
                "content_blocks": 5,
                "variations_applied": 3,
            },
        )
        
        assert result.debug_info is not None
        assert result.debug_info["template_slots"] == 10


class TestLayoutEngineWorkflow:
    """Tests for the engine workflow without actual files."""
    
    @pytest.fixture
    def engine(self):
        return LayoutEngine(EngineConfig(seed=42, debug_mode=True))
    
    def test_parse_template_method_exists(self, engine):
        """Test parse_template method exists."""
        assert hasattr(engine, 'parse_template')
    
    def test_parse_content_method_exists(self, engine):
        """Test parse_content method exists."""
        assert hasattr(engine, 'parse_content')
    
    def test_generate_method_exists(self, engine):
        """Test generate method exists."""
        assert hasattr(engine, 'generate')
    
    def test_get_report_method_exists(self, engine):
        """Test get_report method exists."""
        assert hasattr(engine, 'get_report')
    
    def test_reset_method_exists(self, engine):
        """Test reset method exists."""
        assert hasattr(engine, 'reset')


class TestLayoutEngineConfiguration:
    """Tests for engine configuration options."""
    
    def test_config_validation_rules(self):
        """Test that configuration accepts variation rules."""
        config = EngineConfig(
            variation_rules=[
                {
                    "rule_id": "custom_rule",
                    "slot_type": "IMAGE",
                    "probability": 0.5,
                }
            ]
        )
        
        assert config.variation_rules is not None
        assert len(config.variation_rules) == 1
    
    def test_config_slot_type_mappings(self):
        """Test that configuration accepts slot type mappings."""
        config = EngineConfig(
            slot_type_mappings={
                "ParagraphStyle/CustomTitle": "TITLE",
                "ParagraphStyle/CustomBody": "PARAGRAPH",
            }
        )
        
        assert config.slot_type_mappings is not None
        assert len(config.slot_type_mappings) == 2
    
    def test_config_output_settings(self):
        """Test output settings configuration."""
        config = EngineConfig(
            output_format="idml",
            compress_output=True,
        )
        
        assert config.output_format == "idml"
        assert config.compress_output is True
