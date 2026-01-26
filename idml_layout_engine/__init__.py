"""
IDML Layout Engine
==================

A production-grade, deterministic layout generation system for Adobe InDesign IDML files.

This package provides:
- Layout template extraction from reference IDML files
- Content parsing from Word documents
- Rule-based layout variation
- Mechanical IDML generation

Key Design Principles:
- No AI/LLM involvement in layout decisions or XML generation
- Fully deterministic and reproducible (seedable randomness)
- Mechanically correct XML generation
- Heavy documentation and explicit assumptions

Usage:
    from idml_layout_engine import LayoutEngine
    
    engine = LayoutEngine(
        reference_idml="template.idml",
        content_docs=["section1.docx", "section2.docx"],
        image_mapping={"Section Title": "image.jpg"},
        variation_seed=42
    )
    engine.generate("output.idml")
"""

__version__ = "0.1.0"
__author__ = "IDML Layout Engine Team"

from .engine import LayoutEngine
from .models import (
    Slot,
    SlotType,
    VerticalPosition,
    LayoutTemplate,
    ContentBlock,
    ContentType,
    PageInstance,
    FrameGeometry,
)
from .parser import IDMLParser
from .content_parser import ContentParser
from .variation import VariationEngine
from .generator import IDMLGenerator

__all__ = [
    "LayoutEngine",
    "Slot",
    "SlotType",
    "VerticalPosition",
    "LayoutTemplate",
    "ContentBlock",
    "ContentType",
    "PageInstance",
    "FrameGeometry",
    "IDMLParser",
    "ContentParser",
    "VariationEngine",
    "IDMLGenerator",
]
