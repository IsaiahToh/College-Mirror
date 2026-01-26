#!/usr/bin/env python3
"""
Example: Basic IDML Generation
==============================

This example demonstrates the basic usage of the IDML Layout Engine
to generate an IDML file from Word documents and a reference template.

Prerequisites:
- python-docx installed: pip install python-docx
- A reference IDML file
- One or more Word documents with content

Usage:
    python example_basic.py
    
Or import and use programmatically:
    from examples.example_basic import generate_example
    generate_example("template.idml", ["content.docx"], "output.idml")
"""

import sys
import logging
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from idml_layout_engine import LayoutEngine
from idml_layout_engine.utils import setup_logging


def generate_example(
    reference_idml: str,
    content_docs: list,
    output_path: str,
    image_mapping: dict = None,
    variation_seed: int = None,
) -> str:
    """
    Generate an IDML file using the layout engine.
    
    Args:
        reference_idml: Path to the reference IDML template
        content_docs: List of paths to Word documents
        output_path: Path for the output IDML file
        image_mapping: Optional mapping of section titles to image paths
        variation_seed: Optional seed for layout variations
        
    Returns:
        Path to the generated IDML file
    """
    # Set up logging
    setup_logging(level=logging.INFO)
    
    # Create the engine
    engine = LayoutEngine(
        reference_idml=reference_idml,
        content_docs=content_docs,
        image_mapping=image_mapping or {},
        variation_seed=variation_seed,
    )
    
    # Generate the output
    result_path = engine.generate(output_path)
    
    print(f"Successfully generated: {result_path}")
    return str(result_path)


def main():
    """
    Main function demonstrating example usage.
    
    This example uses placeholder paths. Replace with actual file paths
    to run the example.
    """
    # =========================================================================
    # CONFIGURE THESE PATHS FOR YOUR FILES
    # =========================================================================
    
    # Path to your reference IDML file (the template)
    reference_idml = "template.idml"
    
    # Paths to your Word documents (one per section)
    content_docs = [
        "section1.docx",
        "section2.docx",
        "section3.docx",
    ]
    
    # Output path for the generated IDML
    output_path = "output.idml"
    
    # Image mapping: section title -> image file path
    image_mapping = {
        "First Section Title": "images/section1.jpg",
        "Second Section Title": "images/section2.jpg",
    }
    
    # Variation seed (set to None for no variations, or an integer for reproducible variations)
    variation_seed = 42
    
    # =========================================================================
    
    # Check if files exist
    if not Path(reference_idml).exists():
        print(f"Error: Reference IDML not found: {reference_idml}")
        print("\nThis is an example script. Please update the file paths")
        print("at the top of main() to point to your actual files.")
        return
    
    # Run generation
    try:
        result = generate_example(
            reference_idml=reference_idml,
            content_docs=content_docs,
            output_path=output_path,
            image_mapping=image_mapping,
            variation_seed=variation_seed,
        )
        print(f"\nGeneration complete: {result}")
        
    except Exception as e:
        print(f"Error during generation: {e}")
        raise


if __name__ == "__main__":
    main()
