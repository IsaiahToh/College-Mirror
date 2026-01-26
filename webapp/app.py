"""
Flask application for IDML Layout Engine.

A web interface for generating IDML files from Word documents and reference templates.
"""

import os
import uuid
import json
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional

from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    send_file,
    session,
)
from werkzeug.utils import secure_filename

# python-docx for extracting title from Word documents
try:
    from docx import Document as DocxDocument
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False
    DocxDocument = None

# Create Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")

# Configuration
UPLOAD_FOLDER = Path(__file__).parent / "uploads"
OUTPUT_FOLDER = Path(__file__).parent / "outputs"
ALLOWED_WORD_EXTENSIONS = {"docx", "doc"}
ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "tif", "tiff"}
ALLOWED_TEMPLATE_EXTENSIONS = {"idml"}

# Ensure folders exist
UPLOAD_FOLDER.mkdir(exist_ok=True)
OUTPUT_FOLDER.mkdir(exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["OUTPUT_FOLDER"] = OUTPUT_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100MB max


def allowed_file(filename: str, allowed_extensions: set) -> bool:
    """Check if file has an allowed extension."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed_extensions


def get_session_folder() -> Path:
    """Get or create a session-specific upload folder."""
    if "session_id" not in session:
        session["session_id"] = str(uuid.uuid4())
    
    session_folder = UPLOAD_FOLDER / session["session_id"]
    session_folder.mkdir(exist_ok=True)
    
    # Create subfolders
    (session_folder / "documents").mkdir(exist_ok=True)
    (session_folder / "images").mkdir(exist_ok=True)
    (session_folder / "template").mkdir(exist_ok=True)
    
    return session_folder


def get_session_data_file() -> Path:
    """Get the session data JSON file path."""
    return get_session_folder() / "session_data.json"


def load_session_data() -> dict:
    """Load session data from JSON file."""
    data_file = get_session_data_file()
    if data_file.exists():
        with open(data_file) as f:
            return json.load(f)
    return {
        "documents": [],
        "sections": [],
        "template": None,
        "settings": {
            "seed": None,
            "enable_variations": True,
        },
    }


def save_session_data(data: dict) -> None:
    """Save session data to JSON file."""
    data_file = get_session_data_file()
    with open(data_file, "w") as f:
        json.dump(data, f, indent=2, default=str)


def extract_title_from_docx(filepath: Path) -> str:
    """
    Extract title from a Word document.
    
    The title is the first bold+underlined paragraph in the document.
    Falls back to the first non-empty paragraph if no bold+underlined text found.
    Falls back to the filename if document is empty.
    """
    if not HAS_DOCX:
        # If python-docx not available, use filename as title
        return filepath.stem.replace("_", " ").replace("-", " ").title()
    
    try:
        doc = DocxDocument(str(filepath))
        
        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                continue
            
            # Check if this paragraph is bold AND underlined (title)
            if para.runs:
                total_chars = 0
                bold_chars = 0
                underlined_chars = 0
                
                for run in para.runs:
                    text_len = len(run.text.strip())
                    if text_len == 0:
                        continue
                    total_chars += text_len
                    if run.bold:
                        bold_chars += text_len
                    if run.underline:
                        underlined_chars += text_len
                
                if total_chars > 0:
                    is_bold = (bold_chars / total_chars) >= 0.8
                    is_underlined = (underlined_chars / total_chars) >= 0.8
                    
                    if is_bold and is_underlined:
                        return text
            
            # If first non-empty paragraph is not bold+underlined,
            # still use it as the title (fallback)
            return text
        
        # No paragraphs found, use filename
        return filepath.stem.replace("_", " ").replace("-", " ").title()
        
    except Exception as e:
        # On any error, fall back to filename
        return filepath.stem.replace("_", " ").replace("-", " ").title()


# ============================================================================
# Routes
# ============================================================================

@app.route("/")
def index():
    """Render the main application page."""
    return render_template("index.html")


@app.route("/api/session", methods=["GET"])
def get_session():
    """Get current session data."""
    data = load_session_data()
    return jsonify({
        "success": True,
        "data": data,
    })


@app.route("/api/session/reset", methods=["POST"])
def reset_session():
    """Reset the current session, clearing all uploads."""
    session_folder = get_session_folder()
    
    # Clear all files
    for subfolder in ["documents", "images", "template"]:
        folder = session_folder / subfolder
        if folder.exists():
            shutil.rmtree(folder)
            folder.mkdir()
    
    # Reset session data
    save_session_data({
        "documents": [],
        "sections": [],
        "template": None,
        "settings": {
            "seed": None,
            "enable_variations": True,
        },
    })
    
    return jsonify({"success": True, "message": "Session reset successfully"})


# ============================================================================
# Document Upload Routes
# ============================================================================

@app.route("/api/documents", methods=["POST"])
def upload_documents():
    """Upload Word documents."""
    if "files" not in request.files:
        return jsonify({"success": False, "error": "No files provided"}), 400
    
    files = request.files.getlist("files")
    session_folder = get_session_folder()
    data = load_session_data()
    
    uploaded = []
    
    for file in files:
        if file and file.filename and allowed_file(file.filename, ALLOWED_WORD_EXTENSIONS):
            filename = secure_filename(file.filename)
            # Add timestamp to avoid collisions
            base, ext = os.path.splitext(filename)
            unique_filename = f"{base}_{uuid.uuid4().hex[:8]}{ext}"
            
            filepath = session_folder / "documents" / unique_filename
            file.save(filepath)
            
            # Extract title from document content (first bold+underlined paragraph)
            title = extract_title_from_docx(filepath)
            
            doc_info = {
                "id": str(uuid.uuid4()),
                "filename": unique_filename,
                "original_filename": filename,
                "title": title,
                "uploaded_at": datetime.now().isoformat(),
            }
            
            data["documents"].append(doc_info)
            
            # Create a section for this document
            section_info = {
                "id": doc_info["id"],
                "document_id": doc_info["id"],
                "title": title,
                "images": [],
                "quote_count": 0,  # Number of quote slots for this section
            }
            data["sections"].append(section_info)
            
            uploaded.append(doc_info)
    
    save_session_data(data)
    
    return jsonify({
        "success": True,
        "uploaded": uploaded,
        "total_documents": len(data["documents"]),
        "sections": data["sections"],
    })


@app.route("/api/documents/<doc_id>", methods=["DELETE"])
def delete_document(doc_id: str):
    """Delete a document and its associated section."""
    session_folder = get_session_folder()
    data = load_session_data()
    
    # Find and remove the document
    doc_to_remove = None
    for doc in data["documents"]:
        if doc["id"] == doc_id:
            doc_to_remove = doc
            break
    
    if not doc_to_remove:
        return jsonify({"success": False, "error": "Document not found"}), 404
    
    # Delete the file
    filepath = session_folder / "documents" / doc_to_remove["filename"]
    if filepath.exists():
        filepath.unlink()
    
    # Remove from documents list
    data["documents"] = [d for d in data["documents"] if d["id"] != doc_id]
    
    # Remove associated section and its images
    section_to_remove = None
    for section in data["sections"]:
        if section["document_id"] == doc_id:
            section_to_remove = section
            break
    
    if section_to_remove:
        # Delete associated images
        for img in section_to_remove.get("images", []):
            img_path = session_folder / "images" / img["filename"]
            if img_path.exists():
                img_path.unlink()
        
        data["sections"] = [s for s in data["sections"] if s["document_id"] != doc_id]
    
    save_session_data(data)
    
    return jsonify({
        "success": True,
        "message": "Document deleted",
        "sections": data["sections"],
    })


@app.route("/api/sections/<section_id>/quote_count", methods=["PUT"])
def update_section_quote_count(section_id: str):
    """Update the quote count for a section."""
    data = load_session_data()
    
    try:
        quote_count = int(request.json.get("quote_count", 0))
        quote_count = max(0, min(10, quote_count))  # Clamp between 0 and 10
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "Invalid quote count"}), 400
    
    # Update section quote count
    for section in data["sections"]:
        if section["id"] == section_id:
            section["quote_count"] = quote_count
            save_session_data(data)
            return jsonify({
                "success": True, 
                "quote_count": quote_count,
                "sections": data["sections"],
            })
    
    return jsonify({"success": False, "error": "Section not found"}), 404


# ============================================================================
# Image Upload Routes
# ============================================================================

@app.route("/api/sections/<section_id>/images", methods=["POST"])
def upload_section_images(section_id: str):
    """Upload images to a specific section."""
    if "files" not in request.files:
        return jsonify({"success": False, "error": "No files provided"}), 400
    
    files = request.files.getlist("files")
    session_folder = get_session_folder()
    data = load_session_data()
    
    # Find the section
    section = None
    for s in data["sections"]:
        if s["id"] == section_id:
            section = s
            break
    
    if not section:
        return jsonify({"success": False, "error": "Section not found"}), 404
    
    uploaded = []
    
    for file in files:
        if file and file.filename and allowed_file(file.filename, ALLOWED_IMAGE_EXTENSIONS):
            filename = secure_filename(file.filename)
            base, ext = os.path.splitext(filename)
            unique_filename = f"{section['title'].replace(' ', '_')}_{uuid.uuid4().hex[:8]}{ext}"
            
            filepath = session_folder / "images" / unique_filename
            file.save(filepath)
            
            img_info = {
                "id": str(uuid.uuid4()),
                "filename": unique_filename,
                "original_filename": filename,
                "uploaded_at": datetime.now().isoformat(),
            }
            
            section["images"].append(img_info)
            uploaded.append(img_info)
    
    save_session_data(data)
    
    return jsonify({
        "success": True,
        "uploaded": uploaded,
        "section": section,
    })


@app.route("/api/sections/<section_id>/images/<image_id>", methods=["DELETE"])
def delete_section_image(section_id: str, image_id: str):
    """Delete an image from a section."""
    session_folder = get_session_folder()
    data = load_session_data()
    
    # Find the section
    section = None
    for s in data["sections"]:
        if s["id"] == section_id:
            section = s
            break
    
    if not section:
        return jsonify({"success": False, "error": "Section not found"}), 404
    
    # Find and remove the image
    img_to_remove = None
    for img in section["images"]:
        if img["id"] == image_id:
            img_to_remove = img
            break
    
    if not img_to_remove:
        return jsonify({"success": False, "error": "Image not found"}), 404
    
    # Delete the file
    filepath = session_folder / "images" / img_to_remove["filename"]
    if filepath.exists():
        filepath.unlink()
    
    section["images"] = [i for i in section["images"] if i["id"] != image_id]
    
    save_session_data(data)
    
    return jsonify({"success": True, "section": section})


@app.route("/api/images/<image_id>/move", methods=["POST"])
def move_image(image_id: str):
    """Move an image from one section to another."""
    data = load_session_data()
    target_section_id = request.json.get("target_section_id")
    
    if not target_section_id:
        return jsonify({"success": False, "error": "Target section not specified"}), 400
    
    # Find source section and image
    source_section = None
    image_to_move = None
    
    for section in data["sections"]:
        for img in section["images"]:
            if img["id"] == image_id:
                source_section = section
                image_to_move = img
                break
        if image_to_move:
            break
    
    if not image_to_move:
        return jsonify({"success": False, "error": "Image not found"}), 404
    
    # Find target section
    target_section = None
    for section in data["sections"]:
        if section["id"] == target_section_id:
            target_section = section
            break
    
    if not target_section:
        return jsonify({"success": False, "error": "Target section not found"}), 404
    
    # Move the image
    source_section["images"] = [i for i in source_section["images"] if i["id"] != image_id]
    target_section["images"].append(image_to_move)
    
    save_session_data(data)
    
    return jsonify({
        "success": True,
        "sections": data["sections"],
    })


@app.route("/api/images/<filename>")
def serve_image(filename: str):
    """Serve an uploaded image."""
    session_folder = get_session_folder()
    filepath = session_folder / "images" / secure_filename(filename)
    
    if not filepath.exists():
        return jsonify({"success": False, "error": "Image not found"}), 404
    
    return send_file(filepath)


# ============================================================================
# Template Upload Routes
# ============================================================================

@app.route("/api/template", methods=["POST"])
def upload_template():
    """Upload the reference IDML template."""
    if "file" not in request.files:
        return jsonify({"success": False, "error": "No file provided"}), 400
    
    file = request.files["file"]
    
    if not file or not file.filename:
        return jsonify({"success": False, "error": "No file selected"}), 400
    
    if not allowed_file(file.filename, ALLOWED_TEMPLATE_EXTENSIONS):
        return jsonify({"success": False, "error": "Only IDML files are allowed"}), 400
    
    session_folder = get_session_folder()
    data = load_session_data()
    
    # Clear existing template
    template_folder = session_folder / "template"
    for f in template_folder.iterdir():
        f.unlink()
    
    filename = secure_filename(file.filename)
    filepath = template_folder / filename
    file.save(filepath)
    
    template_info = {
        "filename": filename,
        "original_filename": file.filename,
        "uploaded_at": datetime.now().isoformat(),
    }
    
    data["template"] = template_info
    save_session_data(data)
    
    return jsonify({
        "success": True,
        "template": template_info,
    })


@app.route("/api/template", methods=["DELETE"])
def delete_template():
    """Delete the uploaded template."""
    session_folder = get_session_folder()
    data = load_session_data()
    
    if not data["template"]:
        return jsonify({"success": False, "error": "No template uploaded"}), 404
    
    # Delete the file
    filepath = session_folder / "template" / data["template"]["filename"]
    if filepath.exists():
        filepath.unlink()
    
    data["template"] = None
    save_session_data(data)
    
    return jsonify({"success": True, "message": "Template deleted"})


# ============================================================================
# Settings Routes
# ============================================================================

@app.route("/api/settings", methods=["GET"])
def get_settings():
    """Get current generation settings."""
    data = load_session_data()
    return jsonify({
        "success": True,
        "settings": data["settings"],
    })


@app.route("/api/settings", methods=["PUT"])
def update_settings():
    """Update generation settings."""
    data = load_session_data()
    new_settings = request.json
    
    if "seed" in new_settings:
        data["settings"]["seed"] = new_settings["seed"]
    
    if "enable_variations" in new_settings:
        data["settings"]["enable_variations"] = bool(new_settings["enable_variations"])
    
    save_session_data(data)
    
    return jsonify({
        "success": True,
        "settings": data["settings"],
    })


# ============================================================================
# Generation Routes
# ============================================================================

@app.route("/api/generate", methods=["POST"])
def generate_idml():
    """Generate the IDML file from uploaded content."""
    session_folder = get_session_folder()
    data = load_session_data()
    
    # Validate inputs
    if not data["documents"]:
        return jsonify({"success": False, "error": "No documents uploaded"}), 400
    
    if not data["template"]:
        return jsonify({"success": False, "error": "No template uploaded"}), 400
    
    try:
        # Import the layout engine
        from idml_layout_engine.engine import LayoutEngine, LayoutEngineConfig
        
        # Prepare file paths
        template_path = session_folder / "template" / data["template"]["filename"]
        document_paths = [
            session_folder / "documents" / doc["filename"]
            for doc in data["documents"]
        ]
        
        # Build image mapping (section title -> list of image paths)
        image_mapping = {}
        for section in data["sections"]:
            section_images = [
                str(session_folder / "images" / img["filename"])
                for img in section.get("images", [])
            ]
            if section_images:
                image_mapping[section["title"]] = section_images
        
        # Create output filename
        output_filename = f"output_{datetime.now().strftime('%Y%m%d_%H%M%S')}.idml"
        output_path = OUTPUT_FOLDER / session["session_id"]
        output_path.mkdir(exist_ok=True)
        output_file = output_path / output_filename
        
        # Configure and run the engine
        config = LayoutEngineConfig(
            variation_seed=data["settings"].get("seed"),
            debug_mode=True,
        )
        
        # Skip variations if disabled
        if not data["settings"].get("enable_variations", True):
            config.variation_seed = None
        
        engine = LayoutEngine(
            reference_idml=template_path,
            content_docs=document_paths,
            image_mapping=image_mapping,
            config=config,
        )
        
        result_path = engine.generate(output_file)
        
        return jsonify({
            "success": True,
            "output_filename": output_filename,
            "download_url": f"/api/download/{output_filename}",
            "debug_info": {
                "template_summary": engine.get_template_summary(),
                "content_summary": engine.get_content_summary(),
                "assignment_summary": engine.get_assignment_summary(),
            },
        })
            
    except ImportError as e:
        # Engine not fully implemented yet - create a copy of the template as placeholder
        output_filename = f"output_{datetime.now().strftime('%Y%m%d_%H%M%S')}.idml"
        output_path = OUTPUT_FOLDER / session["session_id"]
        output_path.mkdir(exist_ok=True)
        output_file = output_path / output_filename
        
        # Copy the template as a placeholder output
        template_path = session_folder / "template" / data["template"]["filename"]
        if template_path.exists():
            shutil.copy(template_path, output_file)
        
        return jsonify({
            "success": True,
            "output_filename": output_filename,
            "download_url": f"/api/download/{output_filename}",
            "debug_info": {
                "message": "Engine integration pending - template copied as placeholder",
                "documents": len(data["documents"]),
                "sections_with_images": sum(1 for s in data["sections"] if s.get("images")),
            },
            "mock": True,
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        
        # Try to create placeholder file anyway so download works
        try:
            output_filename = f"output_{datetime.now().strftime('%Y%m%d_%H%M%S')}.idml"
            output_path = OUTPUT_FOLDER / session["session_id"]
            output_path.mkdir(exist_ok=True)
            output_file = output_path / output_filename
            
            template_path = session_folder / "template" / data["template"]["filename"]
            if template_path.exists():
                shutil.copy(template_path, output_file)
                
                return jsonify({
                    "success": True,
                    "output_filename": output_filename,
                    "download_url": f"/api/download/{output_filename}",
                    "debug_info": {
                        "message": f"Error during generation: {str(e)} - template copied as fallback",
                        "error": str(e),
                    },
                    "mock": True,
                })
        except:
            pass
        
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


@app.route("/api/download/<filename>")
def download_output(filename: str):
    """Download a generated IDML file."""
    if "session_id" not in session:
        return jsonify({"success": False, "error": "No active session"}), 400
    
    output_path = OUTPUT_FOLDER / session["session_id"] / secure_filename(filename)
    
    if not output_path.exists():
        return jsonify({"success": False, "error": "File not found"}), 404
    
    return send_file(
        output_path,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.adobe.indesign-idml-package",
    )


# ============================================================================
# Run Application
# ============================================================================

if __name__ == "__main__":
    app.run(debug=True, port=5000)
