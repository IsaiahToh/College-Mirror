#!/usr/bin/env python3
"""
Example: IDML Parsing and Inspection
====================================

This example demonstrates how to parse an IDML file and inspect
its structure, which is useful for:

- Understanding the layout structure of an existing IDML
- Debugging template extraction issues
- Exploring IDML structure for development
- Extracting style names and frame configurations

The example shows:
1. Parsing an IDML file
2. Extracting page dimensions
3. Listing all frames and their properties
4. Identifying styles used
5. Exporting the extracted template
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from idml_layout_engine.parser import IDMLParser
from idml_layout_engine.models import SlotType, VerticalPosition
from idml_layout_engine.utils import setup_logging, format_geometry

import logging


def inspect_idml(idml_path: str) -> None:
    """
    Parse and inspect an IDML file.
    
    Args:
        idml_path: Path to the IDML file to inspect
    """
    setup_logging(level=logging.INFO)
    
    print("=" * 60)
    print(f"IDML Inspector: {idml_path}")
    print("=" * 60)
    
    # Create parser
    parser = IDMLParser(idml_path)
    
    # List files in IDML
    print("\n1. IDML ARCHIVE CONTENTS")
    print("-" * 40)
    files = parser.get_all_files()
    
    file_categories = {
        'Spreads': [],
        'Stories': [],
        'Resources': [],
        'MasterSpreads': [],
        'Other': [],
    }
    
    for f in files:
        categorized = False
        for cat in file_categories:
            if f.startswith(cat):
                file_categories[cat].append(f)
                categorized = True
                break
        if not categorized:
            file_categories['Other'].append(f)
    
    for category, category_files in file_categories.items():
        if category_files:
            print(f"\n{category}/ ({len(category_files)} files)")
            for cf in category_files[:5]:
                print(f"  {cf}")
            if len(category_files) > 5:
                print(f"  ... and {len(category_files) - 5} more")
    
    # Parse template
    print("\n2. PARSING TEMPLATE")
    print("-" * 40)
    
    template = parser.parse()
    
    print(f"Template ID: {template.template_id}")
    
    # Page dimensions
    print("\n3. PAGE DIMENSIONS")
    print("-" * 40)
    dims = template.page_dimensions
    print(f"Width:  {dims.width:.2f} pt ({dims.width/72:.2f} in)")
    print(f"Height: {dims.height:.2f} pt ({dims.height/72:.2f} in)")
    print(f"\nMargins:")
    print(f"  Top:     {dims.margin_top:.2f} pt")
    print(f"  Bottom:  {dims.margin_bottom:.2f} pt")
    print(f"  Inside:  {dims.margin_inside:.2f} pt")
    print(f"  Outside: {dims.margin_outside:.2f} pt")
    print(f"\nColumns: {dims.column_count}")
    print(f"Gutter:  {dims.column_gutter:.2f} pt")
    print(f"Column width: {dims.column_width:.2f} pt")
    
    # Slots summary
    print("\n4. EXTRACTED SLOTS")
    print("-" * 40)
    print(f"Total slots: {len(template.slots)}")
    
    # Group by type
    by_type = {}
    for slot in template.slots:
        type_name = slot.slot_type.name
        if type_name not in by_type:
            by_type[type_name] = []
        by_type[type_name].append(slot)
    
    for type_name, slots in sorted(by_type.items()):
        print(f"\n{type_name} ({len(slots)} slots):")
        for slot in slots[:5]:
            geo = slot.geometry
            print(f"  [{slot.slot_id}]")
            print(f"    Position: {format_geometry(geo.x, geo.y, geo.width, geo.height)}")
            print(f"    Column: {slot.column_index}, Vertical: {slot.vertical_position.name}")
            print(f"    Size: {slot.paragraph_units:.1f} paragraph units")
            if slot.style_name:
                print(f"    Style: {slot.style_name}")
        if len(slots) > 5:
            print(f"  ... and {len(slots) - 5} more")
    
    # Slot groups
    print("\n5. SLOT GROUPS (Interchangeable)")
    print("-" * 40)
    if template.slot_groups:
        for group_id, slot_ids in template.slot_groups.items():
            print(f"\n{group_id}:")
            for sid in slot_ids:
                slot = template.get_slot(sid)
                if slot:
                    print(f"  - {sid} (col={slot.column_index})")
    else:
        print("No interchangeable slot groups found")
    
    # Collect unique styles
    print("\n6. STYLES DETECTED")
    print("-" * 40)
    styles = set()
    for slot in template.slots:
        if slot.style_name:
            styles.add(slot.style_name)
    
    if styles:
        print("Paragraph/Object styles found:")
        for style in sorted(styles):
            print(f"  - {style}")
    else:
        print("No styles detected (check style configuration)")
    
    # Export template
    print("\n7. EXPORT TEMPLATE")
    print("-" * 40)
    
    output_file = Path(idml_path).stem + "_template.json"
    with open(output_file, 'w') as f:
        json.dump(template.to_dict(), f, indent=2)
    print(f"Template exported to: {output_file}")
    
    print("\n" + "=" * 60)
    print("INSPECTION COMPLETE")
    print("=" * 60)


def extract_to_folder(idml_path: str, output_dir: str) -> None:
    """
    Extract IDML contents to a folder for manual inspection.
    
    Args:
        idml_path: Path to the IDML file
        output_dir: Directory to extract to
    """
    parser = IDMLParser(idml_path)
    parser.extract_to_directory(output_dir)
    print(f"Extracted IDML contents to: {output_dir}")


def main():
    """Main function."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Inspect an IDML file and extract its layout template"
    )
    parser.add_argument(
        "idml_path",
        nargs="?",
        default=None,
        help="Path to the IDML file to inspect"
    )
    parser.add_argument(
        "--extract",
        "-e",
        metavar="DIR",
        help="Extract IDML contents to a directory"
    )
    
    args = parser.parse_args()
    
    if args.idml_path is None:
        print("IDML Inspector")
        print("-" * 40)
        print("\nUsage:")
        print("  python example_inspect_idml.py <path_to_file.idml>")
        print("  python example_inspect_idml.py <path_to_file.idml> --extract <output_dir>")
        print("\nThis tool inspects an IDML file and shows:")
        print("  - Archive contents")
        print("  - Page dimensions and margins")
        print("  - Extracted slots and their properties")
        print("  - Detected styles")
        print("  - Interchangeable slot groups")
        return
    
    if not Path(args.idml_path).exists():
        print(f"Error: File not found: {args.idml_path}")
        return
    
    if args.extract:
        extract_to_folder(args.idml_path, args.extract)
    
    inspect_idml(args.idml_path)


if __name__ == "__main__":
    main()
