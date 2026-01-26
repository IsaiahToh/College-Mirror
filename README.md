# IDML Layout Engine

A production-grade, deterministic layout generation system for Adobe InDesign IDML files.

## Overview

This system generates new IDML files by:
1. Parsing a reference IDML file to extract layout structure (template)
2. Reading content from Word documents (.docx)
3. Assigning content to layout slots
4. Applying rule-based layout variations
5. Generating a new IDML file that opens correctly in InDesign

**Key Principle**: This system is entirely mechanical and deterministic. No AI is used for layout decisions or XML generation.

## Installation

```bash
# Clone the repository
git clone https://github.com/IsaiahToh/College-Mirror.git
cd College-Mirror

# Install in development mode
pip install -e ".[dev]"
```

## Quick Start

### Web Application (Recommended)

The easiest way to use the IDML Layout Engine is through the web interface:

```bash
# Run the web application
python run.py

# Or with custom options
python run.py --port 8080 --debug
```

Then open http://127.0.0.1:5000 in your browser.

**Features:**
- Drag & drop Word documents
- Drag & drop images to specific sections
- Visual section management with 4-column grid
- Edit section titles inline
- Upload reference IDML template
- Configure variation seed and enable/disable variations
- One-click IDML generation and download

### Command Line

```bash
# Generate an IDML file
idml-layout generate \
    --reference template.idml \
    --content section1.docx section2.docx \
    --output output.idml \
    --seed 42

# Inspect an IDML file
idml-layout inspect template.idml --json template_info.json

# Validate input files
idml-layout validate --reference template.idml --content *.docx
```

### Python API

```python
from idml_layout_engine import LayoutEngine

# Create engine
engine = LayoutEngine(
    reference_idml="template.idml",
    content_docs=["section1.docx", "section2.docx"],
    image_mapping={"Section Title": "image.jpg"},
    variation_seed=42
)

# Generate output
output_path = engine.generate("output.idml")
```

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Word Documents │     │  Reference IDML │     │  Image Files    │
│  (.docx)        │     │  (template)     │     │  (mapped)       │
└────────┬────────┘     └────────┬────────┘     └────────┬────────┘
         │                       │                       │
         ▼                       ▼                       │
┌─────────────────┐     ┌─────────────────┐              │
│ Content Parser  │     │ Layout Detector │              │
│ → ContentBlocks │     │ → LayoutTemplate│              │
└────────┬────────┘     └────────┬────────┘              │
         │                       │                       │
         └───────────┬───────────┘                       │
                     ▼                                   │
            ┌─────────────────┐                          │
            │ Variation Engine│◄─────────────────────────┘
            │ (Rule-based)    │
            └────────┬────────┘
                     │
                     ▼
            ┌─────────────────┐
            │ IDML Generator  │
            │ → output.idml   │
            └─────────────────┘
```

## Pipeline Stages

### 1. Layout Detection (IDML → LayoutTemplate)

Parses the reference IDML file and extracts:
- Page dimensions, margins, column geometry
- All text frames and image frames
- Frame geometry (x, y, width, height)
- Applied paragraph and object styles
- Column assignment based on geometry
- Vertical ordering of frames within each column

### 2. Content Parsing (Word → ContentBlocks)

Parses Word documents into structured content:
- First paragraph = Section title
- Remaining paragraphs = Body text
- Quote paragraphs identified by configurable rules
- Images mapped to sections via title matching

### 3. Variation Engine (Rule-Based)

Applies deterministic, seedable variations:
- Swaps compatible image slots between columns
- Swaps compatible quote slots
- Respects slot type and size constraints
- Fully reproducible with same seed

### 4. IDML Generation

Produces valid IDML output:
- Clones structure from reference IDML
- Replaces text content in stories
- Updates image links
- Maintains all styles and formatting
- Outputs valid ZIP archive

## Project Structure

```
idml_layout_engine/
├── __init__.py          # Package exports
├── __main__.py          # CLI entry point
├── engine.py            # Main orchestration (LayoutEngine)
├── models.py            # Data models (Slot, LayoutTemplate, etc.)
├── parser.py            # IDML parsing and template extraction
├── content_parser.py    # Word document parsing
├── variation.py         # Rule-based variation engine
├── generator.py         # IDML generation
├── algorithms.py        # Core algorithms
└── utils.py             # Utility functions

examples/
├── example_basic.py           # Basic usage example
├── example_step_by_step.py    # Step-by-step with debugging
└── example_inspect_idml.py    # IDML inspection tool

tests/
├── test_models.py
├── test_parser.py
├── test_content_parser.py
├── test_variation.py
└── test_generator.py
```

## Configuration

### Style Names

Update style names in `parser.py` to match your reference IDML:

```python
# In parser.py, update these lists:
TITLE_STYLE_NAMES = ["ArticleTitle", "Headline"]
BODY_STYLE_NAMES = ["BodyText", "Body"]
QUOTE_STYLE_NAMES = ["PullQuote", "Quote"]
```

### Quote Detection

Configure quote detection in `content_parser.py`:

```python
from idml_layout_engine.content_parser import QuoteDetectionConfig

config = QuoteDetectionConfig(
    quote_style_names=["Quote", "PullQuote"],
    quote_prefix_patterns=[r'^>\s+', r'^"\s*'],
    use_length_heuristic=False,
)
```

### Image Mapping

Map images to sections by title:

```python
image_mapping = {
    "Section One Title": "images/section1.jpg",
    "Section Two Title": ["images/s2_a.jpg", "images/s2_b.jpg"],
}
```

## Debugging

### Step-by-Step Execution

```python
engine = LayoutEngine(reference_idml="template.idml", content_docs=[...])

# Run stages individually
template = engine.parse_template()
sections = engine.parse_content()
assignments = engine.assign_content()
assignments = engine.apply_variations()
output = engine.generate_output("output.idml")

# Inspect intermediate results
print(engine.get_template_summary())
print(engine.get_content_summary())
print(engine.get_assignment_summary())

# Export debug info
engine.export_debug_info("debug_output/")
```

### IDML Inspection

```bash
# Extract IDML for manual inspection
idml-layout inspect template.idml --extract extracted_idml/

# Export template as JSON
idml-layout inspect template.idml --json template.json
```

## Design Principles

1. **Deterministic**: Same inputs + seed always produce same output
2. **Mechanical**: All XML generation is programmatic, not AI-driven
3. **Debuggable**: Every stage can be inspected and logged
4. **Maintainable**: Heavy documentation and explicit assumptions
5. **Conservative**: Only make changes explicitly defined by rules

## Tech Stack & Core Libraries

### Backend
| Technology | Purpose |
|------------|---------|
| **Python 3.10+** | Core language |
| **Flask** | Web framework for the UI |
| **Werkzeug** | WSGI utilities, file uploads |

### Core Libraries
| Library | Purpose |
|---------|---------|
| **lxml** | XML parsing and manipulation for IDML files |
| **python-docx** | Reading Word documents (.docx) |
| **Pillow** | Image processing and validation |

### Frontend
| Technology | Purpose |
|------------|---------|
| **Vanilla JavaScript** | No framework, pure JS for simplicity |
| **HTML5 Drag & Drop API** | File and image drag/drop handling |
| **CSS3** | Custom styling with CSS variables |
| **Font Awesome** | Icons |

### File Formats
| Format | Role |
|--------|------|
| **IDML** | Adobe InDesign Markup Language (ZIP of XML files) |
| **DOCX** | Microsoft Word documents (ZIP of XML files) |
| **JSON** | Session data persistence |

### Architecture Pattern
```
┌─────────────────────────────────────────────────────────────┐
│                     Web Application                         │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────┐  │
│  │   HTML/CSS  │◄──►│   Flask     │◄──►│  Session Store  │  │
│  │   + JS UI   │    │   Routes    │    │  (JSON files)   │  │
│  └─────────────┘    └──────┬──────┘    └─────────────────┘  │
└────────────────────────────┼────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                   IDML Layout Engine                        │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────┐  │
│  │ IDMLParser  │    │ ContentParser│    │ VariationEngine │  │
│  │   (lxml)    │    │(python-docx)│    │  (seedable RNG) │  │
│  └──────┬──────┘    └──────┬──────┘    └────────┬────────┘  │
│         │                  │                    │           │
│         └──────────────────┼────────────────────┘           │
│                            ▼                                │
│                   ┌─────────────────┐                       │
│                   │  IDMLGenerator  │                       │
│                   │  (ZIP + lxml)   │                       │
│                   └─────────────────┘                       │
└─────────────────────────────────────────────────────────────┘
```

## Limitations

- Does not infer design intent
- Does not improve or modify the reference layout
- Requires explicit configuration for style names
- Image links require proper path configuration
- Does not handle complex text threading across pages (placeholder)

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes with tests
4. Submit a pull request

## License

MIT License - see LICENSE file for details.
