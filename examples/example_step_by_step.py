#!/usr/bin/env python3
"""
Example: Step-by-Step Generation with Debugging
================================================

This example demonstrates the step-by-step API for generation,
which allows inspection and debugging at each stage of the pipeline.

This is useful for:
- Understanding how the engine works
- Debugging issues with specific inputs
- Customizing behavior between stages
- Exporting intermediate data for analysis

Pipeline Stages:
1. parse_template() - Extract layout from reference IDML
2. parse_content() - Parse Word documents
3. assign_content() - Assign content to slots
4. apply_variations() - Apply layout variations
5. generate_output() - Create output IDML
"""

import sys
import json
import logging
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from idml_layout_engine import LayoutEngine, LayoutEngineConfig
from idml_layout_engine.utils import setup_logging, create_debug_report


def run_step_by_step(
    reference_idml: str,
    content_docs: list,
    output_path: str,
    debug_output_dir: str = "debug_output",
) -> None:
    """
    Run the generation pipeline step-by-step with debugging.
    
    Args:
        reference_idml: Path to reference IDML
        content_docs: List of Word document paths
        output_path: Path for output IDML
        debug_output_dir: Directory for debug output files
    """
    # Set up verbose logging
    setup_logging(level=logging.DEBUG)
    logger = logging.getLogger(__name__)
    
    # Create debug output directory
    debug_dir = Path(debug_output_dir)
    debug_dir.mkdir(parents=True, exist_ok=True)
    
    # Create engine with debug configuration
    config = LayoutEngineConfig(
        variation_seed=42,
        debug_mode=True,
        save_intermediate=True,
        intermediate_dir=str(debug_dir),
    )
    
    engine = LayoutEngine(
        reference_idml=reference_idml,
        content_docs=content_docs,
        config=config,
    )
    
    # =========================================================================
    # STAGE 1: Parse Template
    # =========================================================================
    print("\n" + "=" * 60)
    print("STAGE 1: Parsing Template")
    print("=" * 60)
    
    template = engine.parse_template()
    
    print(f"Template ID: {template.template_id}")
    print(f"Page dimensions: {template.page_dimensions.width} x {template.page_dimensions.height} pt")
    print(f"Columns: {template.page_dimensions.column_count}")
    print(f"Total slots: {len(template.slots)}")
    print(f"Slot groups: {len(template.slot_groups)}")
    
    # Export template data
    with open(debug_dir / "01_template.json", "w") as f:
        json.dump(template.to_dict(), f, indent=2)
    print(f"\nTemplate data exported to: {debug_dir / '01_template.json'}")
    
    # Print slot breakdown
    print("\nSlots by type:")
    for slot_type, slots in (template._slots_by_type or {}).items():
        print(f"  {slot_type.name}: {len(slots)}")
    
    input("\nPress Enter to continue to Stage 2...")
    
    # =========================================================================
    # STAGE 2: Parse Content
    # =========================================================================
    print("\n" + "=" * 60)
    print("STAGE 2: Parsing Content")
    print("=" * 60)
    
    sections = engine.parse_content()
    
    print(f"Parsed {len(sections)} sections:")
    for section in sections:
        print(f"\n  Section: {section.title.text[:50]}...")
        print(f"    Body blocks: {len(section.body_blocks)}")
        print(f"    Quotes: {len(section.get_quotes())}")
        print(f"    Images: {len(section.image_paths)}")
    
    # Export content data
    content_data = [s.to_dict() for s in sections]
    with open(debug_dir / "02_content.json", "w") as f:
        json.dump(content_data, f, indent=2)
    print(f"\nContent data exported to: {debug_dir / '02_content.json'}")
    
    input("\nPress Enter to continue to Stage 3...")
    
    # =========================================================================
    # STAGE 3: Assign Content to Slots
    # =========================================================================
    print("\n" + "=" * 60)
    print("STAGE 3: Assigning Content to Slots")
    print("=" * 60)
    
    assignments = engine.assign_content()
    
    print(f"Created {len(assignments)} assignments:")
    
    # Group by slot type
    by_type = {}
    for slot_id, assignment in assignments.items():
        type_name = assignment.slot.slot_type.name
        if type_name not in by_type:
            by_type[type_name] = []
        by_type[type_name].append((slot_id, assignment))
    
    for type_name, type_assignments in by_type.items():
        print(f"\n  {type_name} assignments ({len(type_assignments)}):")
        for slot_id, assignment in type_assignments[:3]:  # Show first 3
            content_preview = assignment.content.text[:40] + "..." if assignment.content.text else "[empty]"
            print(f"    {slot_id}: {content_preview}")
        if len(type_assignments) > 3:
            print(f"    ... and {len(type_assignments) - 3} more")
    
    # Export assignment data
    assignment_data = {
        slot_id: {
            "slot_id": a.slot.slot_id,
            "slot_type": a.slot.slot_type.name,
            "content_type": a.content.content_type.name,
            "content_preview": a.content.text[:100] if a.content.text else "",
        }
        for slot_id, a in assignments.items()
    }
    with open(debug_dir / "03_assignments.json", "w") as f:
        json.dump(assignment_data, f, indent=2)
    print(f"\nAssignment data exported to: {debug_dir / '03_assignments.json'}")
    
    input("\nPress Enter to continue to Stage 4...")
    
    # =========================================================================
    # STAGE 4: Apply Variations
    # =========================================================================
    print("\n" + "=" * 60)
    print("STAGE 4: Applying Variations")
    print("=" * 60)
    
    varied_assignments = engine.apply_variations()
    
    print(f"Variation seed: {engine.config.variation_seed}")
    print(f"Operations considered: {len(engine.variation_operations)}")
    
    applied = [op for op in engine.variation_operations if op.applied]
    skipped = [op for op in engine.variation_operations if not op.applied]
    
    print(f"Applied: {len(applied)}")
    print(f"Skipped: {len(skipped)}")
    
    if applied:
        print("\nApplied variations:")
        for op in applied:
            print(f"  [{op.rule_id}] {op.slot_a_id} <-> {op.slot_b_id}")
    
    # Export variation data
    variation_data = {
        "seed": engine.config.variation_seed,
        "operations": [
            {
                "id": op.operation_id,
                "rule": op.rule_id,
                "slot_a": op.slot_a_id,
                "slot_b": op.slot_b_id,
                "applied": op.applied,
            }
            for op in engine.variation_operations
        ]
    }
    with open(debug_dir / "04_variations.json", "w") as f:
        json.dump(variation_data, f, indent=2)
    print(f"\nVariation data exported to: {debug_dir / '04_variations.json'}")
    
    input("\nPress Enter to continue to Stage 5 (final generation)...")
    
    # =========================================================================
    # STAGE 5: Generate Output
    # =========================================================================
    print("\n" + "=" * 60)
    print("STAGE 5: Generating Output IDML")
    print("=" * 60)
    
    result_path = engine.generate_output(output_path)
    
    print(f"\nGenerated: {result_path}")
    print(f"File size: {result_path.stat().st_size:,} bytes")
    
    # Create final debug report
    report = create_debug_report(
        template=engine.template,
        content_sections=engine.content_sections,
        assignments=engine.assignments,
        output_path=debug_dir / "05_final_report.txt",
    )
    print(f"\nDebug report exported to: {debug_dir / '05_final_report.txt'}")
    
    print("\n" + "=" * 60)
    print("GENERATION COMPLETE")
    print("=" * 60)
    print(f"\nOutput file: {result_path}")
    print(f"Debug files: {debug_dir}/")


def main():
    """Main function with example paths."""
    
    # Example paths - update these for your files
    reference_idml = "template.idml"
    content_docs = ["section1.docx", "section2.docx"]
    output_path = "output_debug.idml"
    
    # Check if files exist
    if not Path(reference_idml).exists():
        print("This is an example script. Please update the file paths in main().")
        print("\nTo test without actual files, you can:")
        print("1. Create a simple IDML file in InDesign")
        print("2. Create Word documents with test content")
        print("3. Update the paths in this script")
        return
    
    run_step_by_step(
        reference_idml=reference_idml,
        content_docs=content_docs,
        output_path=output_path,
        debug_output_dir="debug_output",
    )


if __name__ == "__main__":
    main()
