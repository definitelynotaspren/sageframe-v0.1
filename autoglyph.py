#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Auto-Glyph: Semantic Glyph Assignment for Obsidian Vaults
Automatically analyzes note content and assigns thematic glyphs using local LLMs
"""

from pathlib import Path
import frontmatter
from llama_cpp import Llama
import time
import datetime
import json
import yaml
from typing import List, Dict, Optional

# ======================
# CONFIGURATION
# ======================
VAULT_PATH = Path(r"VAULT PATH HERE")
LOG_FILE = VAULT_PATH / "glyph_assignments.jsonl"  # JSON Lines format
MODEL_PATH = r"LOCAL LLM MODEL HERE"

# ======================
# GLYPH LEXICON
# ======================
GLYPH_LEXICON = {
    "⟁": {
        "name": "Paradox Glyph",
        "meanings": ["paradox", "complex systems", "collapse", "fragmentation", "ambiguous truth"],
        "archetypes": ["The Trickster", "The Puzzle", "The Labyrinth"],
        "requires_permission": False
    },
    "⚯": {
        "name": "Dual Witness Glyph",
        "meanings": ["witnessing", "mirroring", "trauma", "grief", "duality", "entanglement"],
        "archetypes": ["The Twins", "The Mirror", "The Echo"],
        "requires_permission": False
    },
    "∷": {
        "name": "Recursion Glyph",
        "meanings": ["loops", "recursion", "patterns", "iteration", "self-reference"],
        "archetypes": ["The Ouroboros", "The Fractal", "The Algorithm"],
        "requires_permission": False
    },
    "∞": {
        "name": "Eternal Glyph",
        "meanings": ["memory", "eternity", "cycles", "immortality", "permanence"],
        "archetypes": ["The Ancient", "The Monument", "The Timeless"],
        "requires_permission": False
    },
    "🜁": {
        "name": "Breath Glyph",
        "meanings": ["breath", "spirit", "transformation", "air", "alchemy"],
        "archetypes": ["The Wind", "The Phoenix", "The Alchemist"],
        "requires_permission": False
    },
    "⧖": {
        "name": "Temporal Fold",
        "meanings": ["time dilation", "deja vu", "temporal distortion"],
        "archetypes": ["The Timekeeper", "The Prophet"],
        "requires_permission": True
    },
    "⁂": {
        "name": "Threshold Marker",
        "meanings": ["initiation", "portals", "boundary crossing"],
        "archetypes": ["The Gatekeeper", "The Wanderer"],
        "requires_permission": True
    }
}

# ======================
# CORE FUNCTIONS
# ======================
def initialize_llm() -> Llama:
    """Initialize the LLM with configured settings"""
    return Llama(
        model_path=MODEL_PATH,
        n_ctx=4096,
        n_threads=8,
        n_gpu_layers=40,
        verbose=False
    )

def log_assignment(filename: str, glyphs: List[str], action: str, error: Optional[str] = None):
    """Log processing results in JSON Lines format"""
    entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "file": filename,
        "action": action,
        "glyphs": glyphs,
        "run_id": datetime.datetime.now().strftime("%Y%m%d-%H%M%S"),
        "error": error
    }
    with open(LOG_FILE, "a", encoding="utf-8") as log:
        log.write(json.dumps(entry, ensure_ascii=False) + "\n")

def write_obsidian_file(file_path: Path, metadata: dict, content: str) -> bool:
    """
    Write properly formatted YAML frontmatter that Obsidian can parse
    Handles nested structures and special characters correctly
    """
    try:
        # Prepare metadata for YAML dumping
        safe_metadata = {}
        for key, value in metadata.items():
            if isinstance(value, (str, int, float, bool, list)):
                safe_metadata[key] = value
            else:
                # Convert complex objects to YAML-safe format
                safe_metadata[key] = yaml.safe_load(yaml.safe_dump(value, allow_unicode=True))
        
        # Write to file with proper formatting
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write('---\n')
            yaml.dump(
                safe_metadata,
                f,
                allow_unicode=True,
                sort_keys=False,
                default_flow_style=False,
                width=float("inf")
            )
            f.write('---\n\n')
            f.write(content.strip())
        return True
    except Exception as e:
        print(f"File write error for {file_path}: {str(e)}")
        return False

def generate_glyph_prompt(is_personal_stream: bool = True) -> str:
    """Generate the LLM prompt dynamically based on glyph lexicon"""
    glyph_descriptions = []
    for glyph, data in GLYPH_LEXICON.items():
        desc = f"{glyph} ({data['name']}): {', '.join(data['meanings'])}"
        if data["requires_permission"]:
            desc += " [REQUIRES PERMISSION]"
        glyph_descriptions.append(desc)
    
    rules = """Rules:
- Max 3 glyphs for personal streams
- Max 7 glyphs for shared experiences
- Permission glyphs (⧖, ⁂) required for shared streams"""
    
    return f"""Analyze the text and select the most representative glyphs:
    
Available Glyphs:
{" | ".join(glyph_descriptions)}

{rules}

Return ONLY the chosen glyphs as comma-separated characters."""

def validate_glyphstream(glyphs: List[str], is_personal: bool = True) -> List[str]:
    """Validate and filter glyph assignments based on rules"""
    valid_glyphs = [g.strip() for g in glyphs if g.strip() in GLYPH_LEXICON]
    
    # Enforce permission rules for shared streams
    if not is_personal:
        permission_glyphs = {g for g, data in GLYPH_LEXICON.items() if data["requires_permission"]}
        if not any(g in permission_glyphs for g in valid_glyphs):
            return []
    
    # Enforce maximum glyph count
    max_glyphs = 3 if is_personal else 7
    return valid_glyphs[:max_glyphs]

def llm_assign_glyphs(llm: Llama, text: str, is_personal_stream: bool = True) -> List[str]:
    """Get glyph assignments from LLM with error handling"""
    if len(text) < 50:  # Skip very short notes
        return []
    
    try:
        response = llm.create_chat_completion(
            messages=[{
                "role": "system",
                "content": generate_glyph_prompt(is_personal_stream)
            }, {
                "role": "user",
                "content": f"Text to analyze:\n\n{text[:3000]}"  # First 3000 chars
            }],
            temperature=0.3,  # Lower = more deterministic
            max_tokens=20
        )
        
        raw_output = response['choices'][0]['message']['content'].strip()
        return validate_glyphstream(raw_output.split(","), is_personal_stream)
    except Exception as e:
        print(f"LLM processing error: {str(e)}")
        return []

# ======================
# MAIN PROCESSING LOOP
# ======================
def process_vault():
    """Main function to process all markdown files in the vault"""
    # Initialize LLM and logging
    llm = initialize_llm()
    if not LOG_FILE.exists():
        LOG_FILE.write_text("")  # Create empty log file
    
    print(f"\n🔮 Starting Auto-Glyph processing for vault: {VAULT_PATH}")
    processed_files = 0
    start_time = time.time()
    
    for md_file in VAULT_PATH.rglob("*.md"):
        try:
            # Load existing note
            post = frontmatter.load(md_file)
            
            # Skip if already processed (unless --force is added later)
            if 'glyphstream' in post.metadata:
                log_assignment(md_file.name, [], "SKIPPED")
                continue
                
            print(f"Analyzing: {md_file.name}")
            
            # Determine stream type
            is_personal = "shared_experience" not in post.metadata.get("tags", [])
            glyphstream = llm_assign_glyphs(llm, post.content, is_personal)
            
            if glyphstream:
                # Build rich metadata
                glyph_metadata = {
                    glyph: {
                        "name": GLYPH_LEXICON[glyph]["name"],
                        "meanings": GLYPH_LEXICON[glyph]["meanings"],
                        "archetypes": GLYPH_LEXICON[glyph]["archetypes"],
                        "requires_permission": GLYPH_LEXICON[glyph]["requires_permission"]
                    } for glyph in glyphstream
                }
                
                # Update metadata
                post.metadata.update({
                    'glyphstream': glyphstream,
                    'glyph_metadata': glyph_metadata,
                    'last_processed': datetime.datetime.now().isoformat(),
                    'stream_type': 'personal' if is_personal else 'shared'
                })
                
                # Write back to file
                if write_obsidian_file(md_file, post.metadata, post.content):
                    log_assignment(md_file.name, glyphstream, "UPDATED")
                    print(f"  ✅ Assigned: {', '.join(glyphstream)}")
                    processed_files += 1
                else:
                    log_assignment(md_file.name, glyphstream, "WRITE_FAILED")
            else:
                log_assignment(md_file.name, [], "NO_MATCH")
            
            time.sleep(0.3)  # Rate limiting
            
        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            log_assignment(md_file.name, [], "ERROR", error_msg)
            print(f"  ❌ Failed: {error_msg}")
    
    # Final report
    duration = time.time() - start_time
    print(f"\nProcessing complete:")
    print(f"- Files processed: {processed_files}")
    print(f"- Duration: {duration:.2f} seconds")
    print(f"- Log file: {LOG_FILE}")

if __name__ == "__main__":
    process_vault()
