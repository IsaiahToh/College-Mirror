"""
Utility Functions for IDML Layout Engine
=========================================

This module contains utility functions used across the layout engine:

- Logging configuration
- File handling utilities
- Debugging helpers
- Validation functions
- Serialization utilities
"""

from __future__ import annotations

import os
import sys
import json
import logging
import hashlib
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime


# =============================================================================
# Logging Configuration
# =============================================================================


def setup_logging(
    level: int = logging.INFO,
    log_file: Optional[str | Path] = None,
    format_string: Optional[str] = None,
) -> None:
    """
    Configure logging for the layout engine.
    
    Args:
        level: Logging level (e.g., logging.INFO, logging.DEBUG)
        log_file: Optional file path for logging output
        format_string: Custom format string for log messages
    """
    if format_string is None:
        format_string = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    handlers: List[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    
    if log_file:
        file_handler = logging.FileHandler(str(log_file))
        handlers.append(file_handler)
    
    logging.basicConfig(
        level=level,
        format=format_string,
        handlers=handlers,
    )
    
    # Set level for our package
    logging.getLogger("idml_layout_engine").setLevel(level)


def get_logger(name: str) -> logging.Logger:
    """Get a logger for a module."""
    return logging.getLogger(f"idml_layout_engine.{name}")


# =============================================================================
# File Handling
# =============================================================================


def ensure_directory(path: str | Path) -> Path:
    """
    Ensure a directory exists, creating it if necessary.
    
    Args:
        path: Directory path
        
    Returns:
        Path object for the directory
    """
    dir_path = Path(path)
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path


def safe_filename(name: str, max_length: int = 255) -> str:
    """
    Create a safe filename from an arbitrary string.
    
    Removes or replaces characters that are problematic in filenames.
    
    Args:
        name: Original name
        max_length: Maximum length for the filename
        
    Returns:
        Sanitized filename
    """
    # Replace problematic characters
    replacements = {
        '/': '_',
        '\\': '_',
        ':': '-',
        '*': '_',
        '?': '_',
        '"': "'",
        '<': '(',
        '>': ')',
        '|': '-',
    }
    
    result = name
    for old, new in replacements.items():
        result = result.replace(old, new)
    
    # Truncate if necessary
    if len(result) > max_length:
        # Keep extension if present
        if '.' in result:
            base, ext = result.rsplit('.', 1)
            available = max_length - len(ext) - 1
            result = base[:available] + '.' + ext
        else:
            result = result[:max_length]
    
    return result


def compute_file_hash(path: str | Path, algorithm: str = 'md5') -> str:
    """
    Compute a hash of a file's contents.
    
    Useful for cache invalidation and change detection.
    
    Args:
        path: Path to the file
        algorithm: Hash algorithm ('md5', 'sha1', 'sha256')
        
    Returns:
        Hex digest of the file hash
    """
    hasher = hashlib.new(algorithm)
    
    with open(path, 'rb') as f:
        while chunk := f.read(8192):
            hasher.update(chunk)
    
    return hasher.hexdigest()


# =============================================================================
# Debugging Helpers
# =============================================================================


def format_geometry(x: float, y: float, width: float, height: float) -> str:
    """Format geometry values for display."""
    return f"({x:.1f}, {y:.1f}, {width:.1f}×{height:.1f})"


def format_slot_summary(slots: List[Any]) -> str:
    """
    Create a formatted summary of slots.
    
    Args:
        slots: List of Slot objects
        
    Returns:
        Multi-line formatted string
    """
    from .models import SlotType
    
    lines = ["Slot Summary:", "-" * 40]
    
    # Group by type
    by_type: Dict[str, List[Any]] = {}
    for slot in slots:
        type_name = slot.slot_type.name
        if type_name not in by_type:
            by_type[type_name] = []
        by_type[type_name].append(slot)
    
    for type_name, type_slots in sorted(by_type.items()):
        lines.append(f"\n{type_name} ({len(type_slots)} slots):")
        for slot in type_slots:
            geo = slot.geometry
            lines.append(
                f"  - {slot.slot_id}: "
                f"col={slot.column_index}, "
                f"pos={slot.vertical_position.name}, "
                f"size={slot.paragraph_units:.1f}pu"
            )
    
    return "\n".join(lines)


def dump_as_json(obj: Any, indent: int = 2) -> str:
    """
    Dump an object as JSON, handling non-serializable types.
    
    Args:
        obj: Object to serialize
        indent: JSON indentation
        
    Returns:
        JSON string
    """
    def default_handler(o):
        if hasattr(o, 'to_dict'):
            return o.to_dict()
        if hasattr(o, '__dict__'):
            return o.__dict__
        if hasattr(o, 'name'):  # Enum
            return o.name
        return str(o)
    
    return json.dumps(obj, indent=indent, default=default_handler)


def create_debug_report(
    template: Any,
    content_sections: List[Any],
    assignments: Dict[str, Any],
    output_path: Optional[str | Path] = None,
) -> str:
    """
    Create a comprehensive debug report.
    
    Args:
        template: LayoutTemplate object
        content_sections: List of ContentSection objects
        assignments: Assignment dictionary
        output_path: Optional file to write report to
        
    Returns:
        Report as a string
    """
    lines = [
        "=" * 60,
        "IDML Layout Engine Debug Report",
        f"Generated: {datetime.now().isoformat()}",
        "=" * 60,
        "",
    ]
    
    # Template info
    if template:
        lines.extend([
            "TEMPLATE",
            "-" * 40,
            f"ID: {template.template_id}",
            f"Source: {template.source_idml_path}",
            f"Page: {template.page_dimensions.width} x {template.page_dimensions.height} pt",
            f"Columns: {template.page_dimensions.column_count}",
            f"Slots: {len(template.slots)}",
            f"Groups: {len(template.slot_groups)}",
            "",
        ])
    
    # Content info
    lines.extend([
        "CONTENT",
        "-" * 40,
        f"Sections: {len(content_sections)}",
    ])
    for section in content_sections:
        lines.append(
            f"  - {section.title.text[:40]}... "
            f"({len(section.body_blocks)} blocks, "
            f"{len(section.image_paths)} images)"
        )
    lines.append("")
    
    # Assignments
    lines.extend([
        "ASSIGNMENTS",
        "-" * 40,
        f"Total: {len(assignments)}",
    ])
    for slot_id, assignment in list(assignments.items())[:10]:
        lines.append(
            f"  - {slot_id}: {assignment.content.content_type.name}"
        )
    if len(assignments) > 10:
        lines.append(f"  ... and {len(assignments) - 10} more")
    
    report = "\n".join(lines)
    
    if output_path:
        with open(output_path, 'w') as f:
            f.write(report)
    
    return report


# =============================================================================
# Validation Functions
# =============================================================================


class ValidationError(Exception):
    """Exception raised for validation failures."""
    pass


def validate_idml_path(path: str | Path) -> Path:
    """
    Validate that a path points to a valid IDML file.
    
    Args:
        path: Path to validate
        
    Returns:
        Validated Path object
        
    Raises:
        ValidationError: If path is invalid
    """
    p = Path(path)
    
    if not p.exists():
        raise ValidationError(f"File not found: {path}")
    
    if not p.is_file():
        raise ValidationError(f"Not a file: {path}")
    
    if p.suffix.lower() != '.idml':
        raise ValidationError(f"Not an IDML file (expected .idml extension): {path}")
    
    return p


def validate_docx_path(path: str | Path) -> Path:
    """
    Validate that a path points to a valid Word document.
    
    Args:
        path: Path to validate
        
    Returns:
        Validated Path object
        
    Raises:
        ValidationError: If path is invalid
    """
    p = Path(path)
    
    if not p.exists():
        raise ValidationError(f"File not found: {path}")
    
    if not p.is_file():
        raise ValidationError(f"Not a file: {path}")
    
    if p.suffix.lower() != '.docx':
        raise ValidationError(f"Not a Word document (expected .docx extension): {path}")
    
    return p


def validate_image_path(path: str | Path) -> Path:
    """
    Validate that a path points to a valid image file.
    
    Args:
        path: Path to validate
        
    Returns:
        Validated Path object
        
    Raises:
        ValidationError: If path is invalid
    """
    p = Path(path)
    
    if not p.exists():
        raise ValidationError(f"Image file not found: {path}")
    
    if not p.is_file():
        raise ValidationError(f"Not a file: {path}")
    
    valid_extensions = {'.jpg', '.jpeg', '.png', '.tiff', '.tif', '.eps', '.pdf', '.psd', '.ai'}
    if p.suffix.lower() not in valid_extensions:
        raise ValidationError(
            f"Unsupported image format: {p.suffix}. "
            f"Supported: {', '.join(valid_extensions)}"
        )
    
    return p


def validate_inputs(
    reference_idml: str | Path,
    content_docs: List[str | Path],
    image_mapping: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Validate all input files for the layout engine.
    
    Args:
        reference_idml: Path to reference IDML
        content_docs: List of Word document paths
        image_mapping: Optional image mapping
        
    Returns:
        Dictionary with validated paths and any warnings
        
    Raises:
        ValidationError: If any required input is invalid
    """
    result = {
        'reference_idml': None,
        'content_docs': [],
        'images': [],
        'warnings': [],
    }
    
    # Validate reference IDML
    result['reference_idml'] = validate_idml_path(reference_idml)
    
    # Validate content documents
    for doc_path in content_docs:
        try:
            result['content_docs'].append(validate_docx_path(doc_path))
        except ValidationError as e:
            result['warnings'].append(str(e))
    
    if not result['content_docs']:
        raise ValidationError("No valid content documents found")
    
    # Validate images
    if image_mapping:
        for title, img_path in image_mapping.items():
            if isinstance(img_path, list):
                for ip in img_path:
                    try:
                        result['images'].append(validate_image_path(ip))
                    except ValidationError as e:
                        result['warnings'].append(str(e))
            else:
                try:
                    result['images'].append(validate_image_path(img_path))
                except ValidationError as e:
                    result['warnings'].append(str(e))
    
    return result


# =============================================================================
# Serialization Utilities
# =============================================================================


def save_template_cache(template: Any, cache_path: str | Path) -> None:
    """
    Save a parsed template to a cache file.
    
    Useful for avoiding re-parsing the same template.
    
    Args:
        template: LayoutTemplate object
        cache_path: Path for the cache file
    """
    cache_data = {
        'version': 1,
        'timestamp': datetime.now().isoformat(),
        'template': template.to_dict(),
    }
    
    with open(cache_path, 'w') as f:
        json.dump(cache_data, f, indent=2)


def load_template_cache(cache_path: str | Path) -> Optional[Dict[str, Any]]:
    """
    Load a template from cache.
    
    Args:
        cache_path: Path to the cache file
        
    Returns:
        Template dictionary, or None if cache is invalid/missing
    """
    try:
        with open(cache_path, 'r') as f:
            cache_data = json.load(f)
        
        if cache_data.get('version') != 1:
            return None
        
        return cache_data.get('template')
        
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return None


# =============================================================================
# Progress Tracking
# =============================================================================


class ProgressTracker:
    """
    Simple progress tracker for long-running operations.
    
    Usage:
        tracker = ProgressTracker(total=100, description="Processing")
        for i in range(100):
            do_work()
            tracker.update()
        tracker.complete()
    """
    
    def __init__(
        self,
        total: int,
        description: str = "Processing",
        log_interval: int = 10,
    ):
        self.total = total
        self.description = description
        self.log_interval = log_interval
        self.current = 0
        self.logger = logging.getLogger("idml_layout_engine.progress")
    
    def update(self, amount: int = 1) -> None:
        """Update progress."""
        self.current += amount
        
        # Log at intervals
        if self.current % self.log_interval == 0 or self.current == self.total:
            percent = (self.current / self.total) * 100
            self.logger.info(
                f"{self.description}: {self.current}/{self.total} ({percent:.1f}%)"
            )
    
    def complete(self) -> None:
        """Mark as complete."""
        self.current = self.total
        self.logger.info(f"{self.description}: Complete")
