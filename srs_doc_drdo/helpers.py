# helpers.py — file readers, archive extractors, project stats, prompt builder, download helpers

import io
import zipfile
import tarfile
import random
import ast
import re
import json
from pathlib import Path
from datetime import datetime

import PyPDF2
import streamlit as st

from constants import SUPPORTED_EXTENSIONS, SRS_SECTIONS, SECTION_PROMPTS, THINKING_MESSAGES


# ─── File readers ─────────────────────────────────────────────────────────────

def read_pdf(data: bytes) -> str:
    try:
        reader = PyPDF2.PdfReader(io.BytesIO(data))
        return "\n".join(p.extract_text() or "" for p in reader.pages)
    except Exception:
        return ""

def read_text(data: bytes) -> str:
    try:
        return data.decode("utf-8", errors="ignore")
    except Exception:
        return ""

def read_file(data: bytes, filename: str) -> str:
    if Path(filename).suffix.lower() == ".pdf":
        return read_pdf(data)
    return read_text(data)


# ─── Archive extractors ───────────────────────────────────────────────────────

def extract_zip(fileobj) -> dict[str, str]:
    files = {}
    try:
        with zipfile.ZipFile(fileobj, "r") as z:
            for entry in z.namelist():
                if entry.endswith("/") or "__MACOSX" in entry or entry.startswith("."):
                    continue
                # Skip hidden directories, virtual environments, caches, and outputs
                parts = Path(entry).parts
                if any(part.startswith(".") or part in ["__pycache__", "node_modules", ".venv", "venv", "srs_output", "graphify-out"] for part in parts):
                    continue
                if Path(entry).suffix.lower() not in SUPPORTED_EXTENSIONS:
                    continue
                try:
                    content = read_file(z.read(entry), entry)
                    if content.strip():
                        files[entry] = content
                except Exception:
                    pass
    except Exception as e:
        st.error(f"ZIP error: {e}")
    return files

def extract_tar(fileobj) -> dict[str, str]:
    files = {}
    try:
        with tarfile.open(fileobj=fileobj, mode="r:*") as t:
            for member in t.getmembers():
                if member.isdir() or member.name.startswith("."):
                    continue
                # Skip hidden directories, virtual environments, caches, and outputs
                parts = Path(member.name).parts
                if any(part.startswith(".") or part in ["__pycache__", "node_modules", ".venv", "venv", "srs_output", "graphify-out"] for part in parts):
                    continue
                if Path(member.name).suffix.lower() not in SUPPORTED_EXTENSIONS:
                    continue
                try:
                    f = t.extractfile(member)
                    if f:
                        content = read_file(f.read(), member.name)
                        if content.strip():
                            files[member.name] = content
                except Exception:
                    pass
    except Exception as e:
        st.error(f"TAR error: {e}")
    return files


# ─── Project stats ────────────────────────────────────────────────────────────

def language_counts(files: dict) -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in files:
        lang = SUPPORTED_EXTENSIONS.get(Path(path).suffix.lower(), "Other")
        counts[lang] = counts.get(lang, 0) + 1
    return counts

def total_size_kb(files: dict) -> float:
    return sum(len(v) for v in files.values()) / 1024


# ─── Codebase context builder ─────────────────────────────────────────────────

def build_codebase_context(files: dict, max_chars: int = 80_000) -> str:
    parts, used = [], 0
    for path, content in files.items():
        ext  = Path(path).suffix.lower()
        lang = SUPPORTED_EXTENSIONS.get(ext, "text")
        snip = content[:5000] + ("\n...[truncated]" if len(content) > 5000 else "")
        chunk = f"\n\n### File: `{path}` ({lang})\n```{ext.lstrip('.')}\n{snip}\n```"
        if used + len(chunk) > max_chars:
            parts.append(f"\n\n### [{len(files) - len(parts)} more files omitted due to context limit]")
            break
        parts.append(chunk)
        used += len(chunk)
    return "".join(parts)


# ─── Prompt builder ───────────────────────────────────────────────────────────

def build_srs_prompt(section_key: str, files: dict) -> str:
    section_instruction = SECTION_PROMPTS.get(
        section_key,
        f"Generate only the SRS section titled '{SRS_SECTIONS.get(section_key, {}).get('title', section_key)}' "
        f"based strictly and exclusively on the uploaded codebase. "
        f"Do NOT hallucinate or invent any information not present in the provided files."
    )
    codebase_context = build_codebase_context(files)

    file_summary = "\n".join(
        f"  - {path} ({SUPPORTED_EXTENSIONS.get(Path(path).suffix.lower(), 'file')})"
        for path in list(files.keys())[:60]
    )
    if len(files) > 60:
        file_summary += f"\n  ... and {len(files) - 60} more files"

    return f"""You are a senior systems analyst and technical writer producing a formal, IEEE-830 compliant Software Requirements Specification (SRS) document.

PROJECT SUMMARY:
- Total files: {len(files)}
- Total size: {total_size_kb(files):.1f} KB
- Languages detected: {', '.join(f"{lang}({cnt})" for lang, cnt in language_counts(files).items())}
- File list:
{file_summary}

TASK INSTRUCTION:
{section_instruction}

ABSOLUTE RULES — VIOLATION OF THESE IS NOT ACCEPTABLE:
1. BASE EVERYTHING ON THE CODEBASE BELOW. Every statement, claim, requirement, and data point must be directly traceable to the provided files.
2. DO NOT HALLUCINATE. Never invent file names, function names, endpoints, features, data models, user roles, SLA numbers, version numbers, or technologies that are not present in the codebase.
3. DO NOT USE FILLER MINIMUMS. Do not pad sections to reach a "minimum" number of entries. Include only what is genuinely found. A shorter, accurate document is far better than a longer, fabricated one.
4. WHEN INFORMATION IS ABSENT, SAY SO. If a sub-section cannot be addressed from the provided code, write exactly: "Not determinable from the provided codebase." Do not guess, infer, or generalise.
5. CITE YOUR EVIDENCE. When making a claim, reference the specific file name that supports it (e.g., "as defined in models.py", "see auth_middleware.js"). Do NOT include any code syntax, code snippets, or code blocks in the output.
6. DO NOT USE WEASEL WORDS. Avoid "typically", "usually", "it is assumed", "likely", "generally", "it can be inferred that" — these introduce unverified content.
7. NO CODE IN OUTPUT. The generated SRS document must contain ZERO lines of source code. Do NOT include any code snippets, function signatures, class definitions, variable declarations, import statements, or code blocks (no triple-backtick blocks). The SRS is a professional requirements document written entirely in plain English prose, tables, and numbered lists. Describe what the software does in plain English — never show how it does it in code.
8. Write in formal, professional Markdown. Use ## headings, tables, and numbered lists where appropriate. All descriptions must be in plain English sentences.

CODEBASE (this is the ONLY source of truth — do not use any external knowledge about what this type of system "usually" does):
{codebase_context}

Generate the requested SRS section now. Begin directly with the section heading — no preamble:"""


# ─── Ollama streaming call ────────────────────────────────────────────────────

def call_ollama_stream(client, prompt: str) -> str:
    """Show an animated spinner until the first token arrives, then stream live."""
    model = st.session_state.current_model
    try:
        stream = client.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            stream=True,
            options={
            "num_ctx":64000,}
        )
        spinner_ph = st.empty()
        def token_gen():
            first = True
            for chunk in stream:
                token = chunk.get("message", {}).get("content", "")
                if token:
                    if first:
                        spinner_ph.empty()
                        first = False
                    yield token
        with spinner_ph:
            with st.spinner( random.choice(THINKING_MESSAGES)):
                full = st.write_stream(token_gen())
        return full or ""
    except Exception as e:
        st.error(f"Ollama error: {e}")
        return ""


# ─── Download helpers ─────────────────────────────────────────────────────────

def assemble_full_srs(sections: dict) -> str:
    header = f"""# Software Requirements Specification
**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}
**Standard:** IEEE 830 / ISO/IEC 29148

---

"""
    body_parts = []
    for sec_key, sec_meta in SRS_SECTIONS.items():
        if sec_key in sections and sections[sec_key].strip():
            body_parts.append(sections[sec_key])
            body_parts.append("\n\n---\n\n")
    return header + "".join(body_parts)

def download_full_srs(sections: dict):
    full_doc = assemble_full_srs(sections)
    st.download_button(
        label="⬇️ Download Full SRS (.md)",
        data=full_doc,
        file_name=f"SRS_Document_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
        mime="text/markdown",
        use_container_width=True,
    )

def download_section(section_key: str, content: str):
    import random
    title = SRS_SECTIONS.get(section_key, {}).get("title", section_key)
    safe_title = title.replace(" ", "_").replace(".", "")
    st.download_button(
        label="⬇️ Download Section",
        data=content,
        file_name=f"SRS_{safe_title}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
        mime="text/markdown",
        use_container_width=True,
        key=f"dl_{section_key}_{random.randint(0,9999)}",
    )


# ─── Pure-Python AST & Regex Extractor ────────────────────────────────────────

def extract_codebase_graph(codebase_path: Path) -> dict:
    """
    Extracts code classes, functions, and call relationships from a directory
    using only built-in standard libraries (ast for Python, regex for others).
    Matches the schema expected by the SQLite graph_loader.
    """
    nodes = []
    links = []
    
    # Map function and class names to their node IDs to resolve call relationships
    func_name_to_ids = {}
    class_name_to_ids = {}
    temp_calls = [] # List of tuples: (caller_fn_id, called_fn_name)
    
    # 1. Walk the directory and extract nodes
    for path in Path(codebase_path).rglob("*"):
        if not path.is_file():
            continue
        # Skip hidden directories, virtual environments, and caches
        if any(part.startswith(".") or part in ["__pycache__", "node_modules", ".venv", "venv", "srs_output", "graphify-out"] for part in path.parts):
            continue
            
        rel_path = str(path.relative_to(codebase_path))
        ext = path.suffix.lower()
        
        # Only parse supported code files
        if ext not in SUPPORTED_EXTENSIONS:
            continue
            
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
            
        # Parse Python files using built-in AST module
        if ext == ".py":
            try:
                tree = ast.parse(content)
                
                class PythonVisitor(ast.NodeVisitor):
                    def __init__(self):
                        self.current_class = None
                        self.current_function = None
                        
                    def visit_ClassDef(self, node):
                        class_id = f"class:{rel_path}:{node.name}"
                        doc = ast.get_docstring(node) or ""
                        nodes.append({
                            "id": class_id,
                            "label": node.name,
                            "type": "class",
                            "file_path": rel_path,
                            "line_start": node.lineno,
                            "line_end": getattr(node, "end_lineno", node.lineno),
                            "docstring": doc
                        })
                        class_name_to_ids[node.name] = class_id
                        
                        old_class = self.current_class
                        self.current_class = node.name
                        self.generic_visit(node)
                        self.current_class = old_class
                        
                    def visit_FunctionDef(self, node):
                        fn_name = f"{self.current_class}.{node.name}" if self.current_class else node.name
                        fn_id = f"fn:{rel_path}:{fn_name}"
                        doc = ast.get_docstring(node) or ""
                        nodes.append({
                            "id": fn_id,
                            "label": node.name,
                            "type": "function",
                            "file_path": rel_path,
                            "line_start": node.lineno,
                            "line_end": getattr(node, "end_lineno", node.lineno),
                            "docstring": doc
                        })
                        
                        # Store in lookup mapping
                        func_name_to_ids[node.name] = func_name_to_ids.get(node.name, []) + [fn_id]
                        if self.current_class:
                            func_name_to_ids[fn_name] = func_name_to_ids.get(fn_name, []) + [fn_id]
                            
                        # Extract calls inside this function
                        old_fn = self.current_function
                        self.current_function = fn_id
                        
                        # Sub-visitor to find calls inside this function body
                        class CallVisitor(ast.NodeVisitor):
                            def __init__(self):
                                self.calls = []
                            def visit_Call(self, call_node):
                                # Detect simple name call e.g., foo()
                                if isinstance(call_node.func, ast.Name):
                                    self.calls.append(call_node.func.id)
                                # Detect attribute call e.g., self.foo() or obj.foo()
                                elif isinstance(call_node.func, ast.Attribute):
                                    self.calls.append(call_node.func.attr)
                                self.generic_visit(call_node)
                                
                        cv = CallVisitor()
                        for child in node.body:
                            cv.visit(child)
                            
                        # Add raw call records to resolve later
                        for called_name in cv.calls:
                            temp_calls.append((fn_id, called_name))
                            
                        self.current_function = old_fn
                        
                visitor = PythonVisitor()
                visitor.visit(tree)
                
            except Exception:
                # Fallback to regex if AST parsing fails (e.g. syntax error in file)
                pass
                
        # Regex-based parser for non-Python or fallback Python
        if ext != ".py" or not any(n["file_path"] == rel_path and n["type"] == "function" for n in nodes):
            fn_patterns = [
                r"\bfunction\s+(\w+)\s*\(", # JS/PHP/Swift
                r"\bconst\s+(\w+)\s*=\s*(?:\([^)]*\)|[^=]+)\s*=>", # JS/TS arrow functions
                r"\bdef\s+(\w+)\s*\(", # Python def (fallback)
                r"\b(?:public|private|protected|static|\s) +[\w<>\s,]+ +(\w+)\s*\([^)]*\)\s*\{" # Java/C++ methods
            ]
            
            lines = content.splitlines()
            for i, line in enumerate(lines):
                for pattern in fn_patterns:
                    m = re.search(pattern, line)
                    if m:
                        name = m.group(1)
                        if name in ["if", "for", "while", "switch", "catch", "return", "class", "import", "export"]:
                            continue
                        fn_id = f"fn:{rel_path}:{name}"
                        nodes.append({
                            "id": fn_id,
                            "label": name,
                            "type": "function",
                            "file_path": rel_path,
                            "line_start": i + 1,
                            "line_end": i + 1,
                            "docstring": ""
                        })
                        func_name_to_ids[name] = func_name_to_ids.get(name, []) + [fn_id]
                        break
                        
    # 2. Resolve explicit AST call edges
    for src_id, dest_name in temp_calls:
        if dest_name in func_name_to_ids:
            for target_id in func_name_to_ids[dest_name]:
                links.append({
                    "source": src_id,
                    "target": target_id,
                    "type": "calls",
                    "confidence": "EXTRACTED",
                    "score": 1.0
                })
                
    # 3. Scan for name matching to build cross-references (implicit calls)
    # Build a set of existing (source, target) pairs for O(1) duplicate detection
    edge_set: set[tuple[str, str]] = {(l["source"], l["target"]) for l in links}

    for path in Path(codebase_path).rglob("*"):
        if not path.is_file():
            continue
        if any(part.startswith(".") or part in ["__pycache__", "node_modules", ".venv", "venv", "srs_output", "graphify-out"] for part in path.parts):
            continue
        rel_path = str(path.relative_to(codebase_path))
        ext = path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            continue
            
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
            
        # Get all function node IDs for this file (computed once per file)
        src_fns = [n["id"] for n in nodes if n["file_path"] == rel_path and n["type"] == "function"]
        if not src_fns:
            continue

        # Check if this file references any function name from the codebase e.g. "func_name("
        for func_name, target_ids in func_name_to_ids.items():
            if f"{func_name}(" in content or f"{func_name} (" in content:
                for src_id in src_fns:
                    for target_id in target_ids:
                        if src_id != target_id:
                            pair = (src_id, target_id)
                            if pair not in edge_set:
                                edge_set.add(pair)
                                links.append({
                                    "source": src_id,
                                    "target": target_id,
                                    "type": "calls",
                                    "confidence": "INFERRED",
                                    "score": 0.8
                                })
                                
    # 4. Add "file" nodes to represent the directory tree structure
    for path in Path(codebase_path).rglob("*"):
        if not path.is_file():
            continue
        if any(part.startswith(".") or part in ["__pycache__", "node_modules", ".venv", "venv", "srs_output", "graphify-out"] for part in path.parts):
            continue
        rel_path = str(path.relative_to(codebase_path))
        if path.suffix.lower() in SUPPORTED_EXTENSIONS:
            file_id = f"file:{rel_path}"
            
            # Count file lines
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    line_count = sum(1 for _ in f)
            except Exception:
                line_count = 1
                
            nodes.append({
                "id": file_id,
                "label": path.name,
                "type": "file",
                "file_path": rel_path,
                "line_start": 1,
                "line_end": line_count,
                "docstring": ""
            })
            
    return {"nodes": nodes, "links": links}


def run_pure_python_extractor(codebase_path: Path, output_json_path: Path):
    """Generates the graph dictionary and writes it to a file, mimicking graphifyy's output."""
    graph = extract_codebase_graph(codebase_path)
    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(graph, f, indent=2)

