"""
Layout Engine - Main Orchestration
===================================

This module provides the main LayoutEngine class that orchestrates
the complete pipeline from input documents to output IDML.

The engine combines:
- IDML parsing (reference template extraction)
- Content parsing (Word document processing)
- Variation (rule-based layout variation)
- IDML generation (output production)

Usage:
    engine = LayoutEngine(
        reference_idml="template.idml",
        content_docs=["section1.docx", "section2.docx"],
        image_mapping={"Section Title": "image.jpg"},
        variation_seed=42
    )
    
    # Generate output
    output_path = engine.generate("output.idml")
    
    # Or step-by-step for debugging
    engine.parse_template()
    engine.parse_content()
    engine.assign_content()
    engine.apply_variations()
    engine.generate_output("output.idml")
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

from .models import (
    LayoutTemplate,
    ContentSection,
    SlotAssignment,
    DocumentLayout,
    PageInstance,
)
from .parser import IDMLParser
from .content_parser import ContentParser, QuoteDetectionConfig
from .variation import VariationEngine, SlotAssigner
from .generator import IDMLGenerator


logger = logging.getLogger(__name__)


@dataclass
class LayoutEngineConfig:
    """
    Configuration for the layout engine.
    
    Centralizes all configurable options for the generation pipeline.
    """
    # Variation settings
    variation_seed: Optional[int] = None
    max_variations_per_page: int = 3
    
    # Content parsing settings
    strip_whitespace: bool = True
    skip_empty_paragraphs: bool = True
    
    # Quote detection
    quote_detection: Optional[QuoteDetectionConfig] = None
    
    # Debug settings
    debug_mode: bool = False
    save_intermediate: bool = False
    intermediate_dir: Optional[str] = None


class LayoutEngine:
    """
    Main orchestration class for the IDML layout generation pipeline.
    
    The LayoutEngine provides both:
    1. A high-level generate() method for one-shot generation
    2. Step-by-step methods for debugging and customization
    
    Pipeline Stages:
    1. parse_template() - Extract layout template from reference IDML
    2. parse_content() - Parse Word documents into content sections
    3. assign_content() - Assign content to slots
    4. apply_variations() - Apply rule-based variations
    5. generate_output() - Generate the output IDML file
    
    Each stage produces results that can be inspected before
    continuing to the next stage.
    """
    
    def __init__(
        self,
        reference_idml: str | Path,
        content_docs: Optional[List[str | Path]] = None,
        image_mapping: Optional[Dict[str, str | List[str]]] = None,
        variation_seed: Optional[int] = None,
        config: Optional[LayoutEngineConfig] = None,
    ):
        """
        Initialize the layout engine.
        
        Args:
            reference_idml: Path to the reference IDML file
            content_docs: List of paths to Word documents
            image_mapping: Mapping of section titles to image paths
            variation_seed: Random seed for variations (overrides config)
            config: Configuration object (optional)
        """
        self.reference_idml = Path(reference_idml)
        self.content_docs = [Path(p) for p in (content_docs or [])]
        self.image_mapping = image_mapping or {}
        
        # Configuration
        self.config = config or LayoutEngineConfig()
        if variation_seed is not None:
            self.config.variation_seed = variation_seed
        
        # Pipeline state
        self.template: Optional[LayoutTemplate] = None
        self.content_sections: List[ContentSection] = []
        self.assignments: Dict[str, SlotAssignment] = {}
        self.variation_operations: List[Any] = []
        self.output_path: Optional[Path] = None
        
        # Component instances
        self._parser: Optional[IDMLParser] = None
        self._content_parser: Optional[ContentParser] = None
        self._assigner: Optional[SlotAssigner] = None
        self._variation_engine: Optional[VariationEngine] = None
        self._generator: Optional[IDMLGenerator] = None
        
        logger.info(f"LayoutEngine initialized with reference: {self.reference_idml}")
    
    # =========================================================================
    # High-Level API
    # =========================================================================
    
    def generate(self, output_path: str | Path) -> Path:
        """
        Run the complete generation pipeline.
        
        This is the main entry point for generating an IDML file.
        It runs all pipeline stages in sequence.
        
        Args:
            output_path: Path for the output IDML file
            
        Returns:
            Path to the generated IDML file
        """
        logger.info("Starting generation pipeline")
        
        # Run all stages
        self.parse_template()
        self.parse_content()
        self.assign_content()
        self.apply_variations()
        return self.generate_output(output_path)
    
    # =========================================================================
    # Step-by-Step API
    # =========================================================================
    
    def parse_template(self) -> LayoutTemplate:
        """
        Stage 1: Parse the reference IDML to extract the layout template.
        
        This extracts:
        - Page dimensions and margins
        - All text frames and image frames
        - Frame geometries
        - Slot types and positions
        
        Returns:
            The extracted LayoutTemplate
        """
        logger.info("Stage 1: Parsing template from reference IDML")
        
        self._parser = IDMLParser(self.reference_idml)
        self.template = self._parser.parse()
        
        logger.info(
            f"Extracted template with {len(self.template.slots)} slots, "
            f"{len(self.template.slot_groups)} groups"
        )
        
        if self.config.debug_mode:
            self._log_template_summary()
        
        return self.template
    
    def parse_content(self) -> List[ContentSection]:
        """
        Stage 2: Parse Word documents into structured content sections.
        
        Each document becomes a ContentSection with:
        - Title (first paragraph)
        - Body blocks (remaining paragraphs)
        - Associated images
        
        Returns:
            List of ContentSection objects
        """
        logger.info("Stage 2: Parsing content from Word documents")
        
        if not self.content_docs:
            logger.warning("No content documents provided")
            self.content_sections = []
            return self.content_sections
        
        self._content_parser = ContentParser(
            quote_config=self.config.quote_detection,
            strip_whitespace=self.config.strip_whitespace,
            skip_empty_paragraphs=self.config.skip_empty_paragraphs,
        )
        
        self.content_sections = self._content_parser.parse_documents(
            docx_paths=self.content_docs,
            image_mapping=self.image_mapping,
        )
        
        total_blocks = sum(
            1 + len(s.body_blocks) for s in self.content_sections
        )
        logger.info(
            f"Parsed {len(self.content_sections)} sections, "
            f"{total_blocks} total blocks"
        )
        
        if self.config.debug_mode:
            self._log_content_summary()
        
        return self.content_sections
    
    def assign_content(self) -> Dict[str, SlotAssignment]:
        """
        Stage 3: Assign content blocks to layout slots.
        
        Uses the SlotAssigner to map content to appropriate slots
        based on content type and slot availability.
        
        Returns:
            Dictionary mapping slot_id to SlotAssignment
        """
        logger.info("Stage 3: Assigning content to slots")
        
        if self.template is None:
            raise RuntimeError("Template not parsed. Call parse_template() first.")
        
        self._assigner = SlotAssigner(self.template)
        self.assignments = self._assigner.assign_content(self.content_sections)
        
        logger.info(f"Created {len(self.assignments)} slot assignments")
        
        if self.config.debug_mode:
            self._log_assignment_summary()
        
        return self.assignments
    
    def apply_variations(self) -> Dict[str, SlotAssignment]:
        """
        Stage 4: Apply rule-based layout variations.
        
        Uses the VariationEngine to swap compatible slots
        for visual variety while maintaining layout correctness.
        
        Returns:
            Modified assignments dictionary
        """
        logger.info("Stage 4: Applying variations")
        
        if self.template is None:
            raise RuntimeError("Template not parsed. Call parse_template() first.")
        
        if self.config.variation_seed is None:
            logger.info("No variation seed provided, skipping variations")
            return self.assignments
        
        self._variation_engine = VariationEngine(
            seed=self.config.variation_seed,
            max_variations_per_page=self.config.max_variations_per_page,
        )
        
        self.assignments, self.variation_operations = (
            self._variation_engine.apply_variations(
                template=self.template,
                assignments=self.assignments,
            )
        )
        
        applied_count = len([op for op in self.variation_operations if op.applied])
        logger.info(f"Applied {applied_count} variations")
        
        if self.config.debug_mode:
            logger.debug(self._variation_engine.get_variation_report())
        
        return self.assignments
    
    def generate_output(self, output_path: str | Path) -> Path:
        """
        Stage 5: Generate the output IDML file.
        
        Creates a new IDML file with:
        - Structure from reference IDML
        - Content from Word documents
        - Applied variations
        
        Args:
            output_path: Path for the output file
            
        Returns:
            Path to the generated file
        """
        logger.info("Stage 5: Generating output IDML")
        
        if self.template is None:
            raise RuntimeError("Template not parsed. Call parse_template() first.")
        
        self._generator = IDMLGenerator(self.reference_idml)
        self.output_path = self._generator.generate(
            output_path=output_path,
            template=self.template,
            assignments=self.assignments,
            content_sections=self.content_sections,
            image_paths=dict(self.image_mapping),
        )
        
        logger.info(f"Generated: {self.output_path}")
        return self.output_path
    
    # =========================================================================
    # Configuration Methods
    # =========================================================================
    
    def add_content_document(self, docx_path: str | Path) -> None:
        """Add a content document to the processing list."""
        self.content_docs.append(Path(docx_path))
    
    def set_image_mapping(
        self, 
        section_title: str, 
        image_path: str | List[str]
    ) -> None:
        """Set an image mapping for a section title."""
        self.image_mapping[section_title] = image_path
    
    def set_variation_seed(self, seed: int) -> None:
        """Set the random seed for variations."""
        self.config.variation_seed = seed
    
    # =========================================================================
    # Inspection Methods
    # =========================================================================
    
    def get_template_summary(self) -> Dict[str, Any]:
        """Get a summary of the parsed template."""
        if self.template is None:
            return {"status": "not_parsed"}
        
        return {
            "template_id": self.template.template_id,
            "page_dimensions": self.template.page_dimensions.to_dict(),
            "slot_count": len(self.template.slots),
            "slots_by_type": {
                slot_type.name: len(slots)
                for slot_type, slots in (self.template._slots_by_type or {}).items()
            },
            "group_count": len(self.template.slot_groups),
        }
    
    def get_content_summary(self) -> Dict[str, Any]:
        """Get a summary of the parsed content."""
        return {
            "section_count": len(self.content_sections),
            "sections": [
                {
                    "title": s.title.text[:50] + "..." if len(s.title.text) > 50 else s.title.text,
                    "body_block_count": len(s.body_blocks),
                    "quote_count": len(s.get_quotes()),
                    "image_count": len(s.image_paths),
                }
                for s in self.content_sections
            ],
        }
    
    def get_assignment_summary(self) -> Dict[str, Any]:
        """Get a summary of slot assignments."""
        return {
            "assignment_count": len(self.assignments),
            "by_slot_type": self._count_assignments_by_type(),
        }
    
    def get_variation_summary(self) -> Dict[str, Any]:
        """Get a summary of applied variations."""
        return {
            "seed": self.config.variation_seed,
            "total_operations": len(self.variation_operations),
            "applied": len([op for op in self.variation_operations if op.applied]),
            "skipped": len([op for op in self.variation_operations if not op.applied]),
        }
    
    # =========================================================================
    # Debug Methods
    # =========================================================================
    
    def _log_template_summary(self) -> None:
        """Log a summary of the parsed template."""
        summary = self.get_template_summary()
        logger.debug(f"Template summary: {summary}")
    
    def _log_content_summary(self) -> None:
        """Log a summary of the parsed content."""
        summary = self.get_content_summary()
        logger.debug(f"Content summary: {summary}")
    
    def _log_assignment_summary(self) -> None:
        """Log a summary of assignments."""
        summary = self.get_assignment_summary()
        logger.debug(f"Assignment summary: {summary}")
    
    def _count_assignments_by_type(self) -> Dict[str, int]:
        """Count assignments by slot type."""
        from collections import Counter
        counts = Counter(
            assignment.slot.slot_type.name 
            for assignment in self.assignments.values()
        )
        return dict(counts)
    
    def export_debug_info(self, output_dir: str | Path) -> None:
        """
        Export debugging information to a directory.
        
        Creates JSON files with:
        - template.json: Parsed template details
        - content.json: Parsed content summary
        - assignments.json: Slot assignments
        - variations.json: Applied variations
        """
        import json
        
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Export template
        if self.template:
            with open(output_path / "template.json", "w") as f:
                json.dump(self.template.to_dict(), f, indent=2)
        
        # Export content
        with open(output_path / "content.json", "w") as f:
            content_data = [s.to_dict() for s in self.content_sections]
            json.dump(content_data, f, indent=2)
        
        # Export assignments
        with open(output_path / "assignments.json", "w") as f:
            assignment_data = {
                slot_id: assignment.to_dict()
                for slot_id, assignment in self.assignments.items()
            }
            json.dump(assignment_data, f, indent=2)
        
        # Export variations
        with open(output_path / "variations.json", "w") as f:
            variation_data = {
                "seed": self.config.variation_seed,
                "operations": [
                    {
                        "id": op.operation_id,
                        "rule": op.rule_id,
                        "slot_a": op.slot_a_id,
                        "slot_b": op.slot_b_id,
                        "applied": op.applied,
                        "description": op.description,
                    }
                    for op in self.variation_operations
                ],
            }
            json.dump(variation_data, f, indent=2)
        
        logger.info(f"Debug info exported to {output_path}")


# =============================================================================
# Convenience Functions
# =============================================================================


def create_engine(
    reference_idml: str | Path,
    content_docs: List[str | Path],
    image_mapping: Optional[Dict[str, str]] = None,
    variation_seed: Optional[int] = None,
) -> LayoutEngine:
    """
    Create a LayoutEngine with common defaults.
    
    Convenience function for simple use cases.
    
    Args:
        reference_idml: Path to reference IDML
        content_docs: List of Word document paths
        image_mapping: Optional image mapping
        variation_seed: Optional variation seed
        
    Returns:
        Configured LayoutEngine
    """
    return LayoutEngine(
        reference_idml=reference_idml,
        content_docs=content_docs,
        image_mapping=image_mapping,
        variation_seed=variation_seed,
    )


def generate_from_files(
    reference_idml: str | Path,
    content_docs: List[str | Path],
    output_path: str | Path,
    image_mapping: Optional[Dict[str, str]] = None,
    variation_seed: Optional[int] = None,
) -> Path:
    """
    One-liner to generate an IDML file from inputs.
    
    Args:
        reference_idml: Path to reference IDML
        content_docs: List of Word document paths
        output_path: Path for output IDML
        image_mapping: Optional image mapping
        variation_seed: Optional variation seed
        
    Returns:
        Path to generated IDML file
    """
    engine = create_engine(
        reference_idml=reference_idml,
        content_docs=content_docs,
        image_mapping=image_mapping,
        variation_seed=variation_seed,
    )
    return engine.generate(output_path)
