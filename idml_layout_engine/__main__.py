#!/usr/bin/env python3
"""
Command-Line Interface for IDML Layout Engine
==============================================

This CLI provides access to the layout engine functionality from
the command line.

Commands:
- generate: Generate an IDML file from Word documents
- inspect: Inspect an IDML file structure
- validate: Validate input files

Usage:
    python -m idml_layout_engine generate --help
    python -m idml_layout_engine inspect template.idml
    python -m idml_layout_engine validate --reference template.idml --content doc1.docx doc2.docx
"""

import sys
import argparse
import logging
from pathlib import Path
from typing import List, Optional


def setup_logging(verbose: bool = False) -> None:
    """Configure logging based on verbosity."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )


def cmd_generate(args: argparse.Namespace) -> int:
    """Generate an IDML file."""
    from idml_layout_engine import LayoutEngine
    
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)
    
    logger.info(f"Reference IDML: {args.reference}")
    logger.info(f"Content documents: {len(args.content)}")
    logger.info(f"Output: {args.output}")
    
    # Build image mapping
    image_mapping = {}
    if args.images:
        for img_spec in args.images:
            if '=' in img_spec:
                title, path = img_spec.split('=', 1)
                image_mapping[title] = path
            else:
                logger.warning(f"Invalid image mapping (expected TITLE=PATH): {img_spec}")
    
    # Create engine
    engine = LayoutEngine(
        reference_idml=args.reference,
        content_docs=args.content,
        image_mapping=image_mapping,
        variation_seed=args.seed,
    )
    
    # Generate
    try:
        output_path = engine.generate(args.output)
        logger.info(f"Successfully generated: {output_path}")
        return 0
    except Exception as e:
        logger.error(f"Generation failed: {e}")
        if args.verbose:
            raise
        return 1


def cmd_inspect(args: argparse.Namespace) -> int:
    """Inspect an IDML file."""
    from idml_layout_engine.parser import IDMLParser
    import json
    
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)
    
    idml_path = Path(args.idml)
    if not idml_path.exists():
        logger.error(f"File not found: {args.idml}")
        return 1
    
    logger.info(f"Inspecting: {idml_path}")
    
    parser = IDMLParser(idml_path)
    
    # Extract if requested
    if args.extract:
        parser.extract_to_directory(args.extract)
        logger.info(f"Extracted to: {args.extract}")
    
    # Parse template
    template = parser.parse()
    
    # Print summary
    print("\n" + "=" * 50)
    print("IDML Template Summary")
    print("=" * 50)
    print(f"Template ID: {template.template_id}")
    print(f"Page: {template.page_dimensions.width:.1f} x {template.page_dimensions.height:.1f} pt")
    print(f"Columns: {template.page_dimensions.column_count}")
    print(f"Slots: {len(template.slots)}")
    print(f"Groups: {len(template.slot_groups)}")
    
    # Slot breakdown
    print("\nSlots by type:")
    for slot_type, slots in (template._slots_by_type or {}).items():
        print(f"  {slot_type.name}: {len(slots)}")
    
    # Export if requested
    if args.json:
        with open(args.json, 'w') as f:
            json.dump(template.to_dict(), f, indent=2)
        logger.info(f"Template exported to: {args.json}")
    
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    """Validate input files."""
    from idml_layout_engine.utils import validate_inputs, ValidationError
    from idml_layout_engine.content_parser import validate_docx_structure
    
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)
    
    print("Validating inputs...")
    print("-" * 40)
    
    errors = []
    warnings = []
    
    # Validate IDML
    if args.reference:
        print(f"\nReference IDML: {args.reference}")
        if Path(args.reference).exists():
            if Path(args.reference).suffix.lower() == '.idml':
                print("  ✓ File exists and has .idml extension")
            else:
                errors.append(f"Not an IDML file: {args.reference}")
        else:
            errors.append(f"File not found: {args.reference}")
    
    # Validate content documents
    if args.content:
        print(f"\nContent documents ({len(args.content)}):")
        for doc_path in args.content:
            print(f"\n  {doc_path}")
            if not Path(doc_path).exists():
                errors.append(f"File not found: {doc_path}")
                print("    ✗ File not found")
                continue
            
            if Path(doc_path).suffix.lower() != '.docx':
                errors.append(f"Not a Word document: {doc_path}")
                print("    ✗ Not a .docx file")
                continue
            
            # Validate structure
            result = validate_docx_structure(doc_path)
            if result['is_valid']:
                print(f"    ✓ Valid ({result['paragraph_count']} paragraphs)")
            else:
                for err in result['errors']:
                    errors.append(f"{doc_path}: {err}")
                    print(f"    ✗ {err}")
            
            for warn in result.get('warnings', []):
                warnings.append(f"{doc_path}: {warn}")
                print(f"    ⚠ {warn}")
    
    # Validate images
    if args.images:
        print(f"\nImages ({len(args.images)}):")
        for img_path in args.images:
            if not Path(img_path).exists():
                errors.append(f"Image not found: {img_path}")
                print(f"  ✗ {img_path} (not found)")
            else:
                print(f"  ✓ {img_path}")
    
    # Summary
    print("\n" + "=" * 40)
    print("VALIDATION SUMMARY")
    print("=" * 40)
    
    if errors:
        print(f"\n✗ {len(errors)} error(s):")
        for err in errors:
            print(f"  - {err}")
    
    if warnings:
        print(f"\n⚠ {len(warnings)} warning(s):")
        for warn in warnings:
            print(f"  - {warn}")
    
    if not errors:
        print("\n✓ All inputs valid")
        return 0
    else:
        return 1


def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="idml_layout_engine",
        description="IDML Layout Engine - Generate IDML files from Word documents",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output",
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Generate command
    gen_parser = subparsers.add_parser(
        "generate",
        help="Generate an IDML file from Word documents",
    )
    gen_parser.add_argument(
        "-r", "--reference",
        required=True,
        help="Path to reference IDML file (template)",
    )
    gen_parser.add_argument(
        "-c", "--content",
        nargs="+",
        required=True,
        help="Path(s) to Word documents",
    )
    gen_parser.add_argument(
        "-o", "--output",
        required=True,
        help="Output IDML file path",
    )
    gen_parser.add_argument(
        "-i", "--images",
        nargs="*",
        help="Image mappings in format TITLE=PATH",
    )
    gen_parser.add_argument(
        "-s", "--seed",
        type=int,
        help="Random seed for variations",
    )
    gen_parser.set_defaults(func=cmd_generate)
    
    # Inspect command
    inspect_parser = subparsers.add_parser(
        "inspect",
        help="Inspect an IDML file structure",
    )
    inspect_parser.add_argument(
        "idml",
        help="Path to IDML file to inspect",
    )
    inspect_parser.add_argument(
        "-e", "--extract",
        metavar="DIR",
        help="Extract IDML contents to directory",
    )
    inspect_parser.add_argument(
        "-j", "--json",
        metavar="FILE",
        help="Export template as JSON",
    )
    inspect_parser.set_defaults(func=cmd_inspect)
    
    # Validate command
    val_parser = subparsers.add_parser(
        "validate",
        help="Validate input files",
    )
    val_parser.add_argument(
        "-r", "--reference",
        help="Reference IDML file",
    )
    val_parser.add_argument(
        "-c", "--content",
        nargs="*",
        help="Content Word documents",
    )
    val_parser.add_argument(
        "-i", "--images",
        nargs="*",
        help="Image files",
    )
    val_parser.set_defaults(func=cmd_validate)
    
    # Parse and execute
    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
        return 0
    
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
