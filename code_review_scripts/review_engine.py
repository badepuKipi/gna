# review_engine.py

import os, sys, json, re, glob
from pathlib import Path
from config_and_prompts import *

# def get_changed_python_files(folder_path=None):
#     """
#     Dynamically get all Python AND SQL files from the specified folder or scripts directory.
#     Uses wildcard pattern matching for flexibility.
#     """
#     # If no folder specified, use the scripts directory
#     if not folder_path:
#         folder_path = SCRIPTS_DIRECTORY
       
#     if not os.path.exists(folder_path):
#         print(f"❌ Directory {folder_path} not found")
#         return []
   
#     all_files = []
   
#     # Process both Python and SQL files
#     for pattern in FILE_PATTERNS:
#         # Use glob pattern to find files
#         pattern_path = os.path.join(folder_path, pattern)
#         found_files = glob.glob(pattern_path)
       
#         # Also check subdirectories recursively
#         recursive_pattern = os.path.join(folder_path, "**", pattern)
#         found_files.extend(glob.glob(recursive_pattern, recursive=True))
       
#         all_files.extend(found_files)
   
#     # Remove duplicates and sort
#     all_files = sorted(list(set(all_files)))
   
#     print(f"📁 Found {len(all_files)} code files in {folder_path} using patterns {FILE_PATTERNS}:")
#     for file in all_files:
#         file_type = "SQL" if file.lower().endswith('.sql') else "Python"
#         print(f"  - {file} ({file_type})")
   
#     return all_files

def get_changed_python_files(folder_path=None):
    """
    Dynamically get all Python AND SQL files from the specified folder or scripts directory.
    Uses wildcard pattern matching for flexibility.
    Excludes folders specified in IGNORE_FOLDERS.
    """
    # If no folder specified, use the scripts directory or current directory
    if not folder_path:
        folder_path = SCRIPTS_DIRECTORY or "."
       
    if not os.path.exists(folder_path):
        print(f"❌ Directory {folder_path} not found")
        return []
   
    all_files = []
   
    # Process both Python and SQL files
    for pattern in FILE_PATTERNS:
        # Use glob pattern to find files
        pattern_path = os.path.join(folder_path, pattern)
        found_files = glob.glob(pattern_path)
       
        # Also check subdirectories recursively
        recursive_pattern = os.path.join(folder_path, "**", pattern)
        found_files.extend(glob.glob(recursive_pattern, recursive=True))
       
        all_files.extend(found_files)
   
    # Remove duplicates
    all_files = list(set(all_files))
    
    # Filter out ignored folders
    filtered_files = []
    for file in all_files:
        # Check if any ignored folder is in the file path
        should_ignore = False
        for ignore_folder in IGNORE_FOLDERS:
            if ignore_folder in os.path.normpath(file).split(os.sep):
                should_ignore = True
                print(f"  ⊘ Ignoring {file} (in excluded folder: {ignore_folder})")
                break
        
        if not should_ignore:
            filtered_files.append(file)
    
    # Sort the filtered files
    filtered_files = sorted(filtered_files)
   
    print(f"📁 Found {len(filtered_files)} code files in {folder_path} using patterns {FILE_PATTERNS}:")
    print(f"   (Excluded {len(all_files) - len(filtered_files)} files from folders: {IGNORE_FOLDERS})")
    for file in filtered_files:
        file_type = "SQL" if file.lower().endswith('.sql') else "Python"
        print(f"  - {file} ({file_type})")
   
    return filtered_files

def build_prompt_for_individual_review(code_text: str, filename: str = "code_file", client_rules: str = None) -> str:
    """
    Build the appropriate prompt based on file type (Python or SQL) with optional client rules.
    
    Args:
        code_text: The code content to review
        filename: Name of the file being reviewed
        client_rules: Optional client-specific rules/instructions
    """
    # Determine file type
    is_sql = filename.lower().endswith('.sql')
    
    # Select appropriate template
    template = PROMPT_TEMPLATE_SQL if is_sql else PROMPT_TEMPLATE_PYTHON
    
    # Handle client rules - FIX #2: Client rules supplement but DO NOT override Python/SQL standards
    if client_rules and client_rules.strip():
        rules_text = f"""**Client has provided additional specific guidelines (these supplement but DO NOT override PEP 8, PEP 257, PEP 484, or SQL standards):**

{client_rules}

**IMPORTANT: These client rules are ADDITIONAL requirements. Python/SQL language standards (PEP 8, PEP 257, PEP 484, sqlstyle.guide) ALWAYS take priority. Where client rules conflict with language standards, the language standards win. Cite "Client Rule" only when these additional guidelines are violated.**
"""
    else:
        rules_text = DEFAULT_CLIENT_RULES
    
    # Build the final prompt
    prompt = template.replace("{CLIENT_RULES}", rules_text)
    prompt = prompt.replace("{PY_CONTENT}", code_text)
    prompt = prompt.replace("{filename}", filename)
    
    return prompt

def build_prompt_for_consolidated_summary(all_reviews_content: str, previous_context: str = None, pr_number: int = None) -> str:
    if previous_context and pr_number:
        prompt = PROMPT_TEMPLATE_WITH_CONTEXT.replace("{previous_context}", previous_context)
        prompt = prompt.replace("{pr_number}", str(pr_number))
        prompt = prompt.replace("{consolidated_template}", PROMPT_TEMPLATE_CONSOLIDATED)
        prompt = prompt.replace("{ALL_REVIEWS_CONTENT}", all_reviews_content)
    else:
        prompt = PROMPT_TEMPLATE_CONSOLIDATED.replace("{ALL_REVIEWS_CONTENT}", all_reviews_content)
    return prompt

def review_with_cortex(model, prompt_text: str, session) -> str:
    try:
        clean_prompt = prompt_text.replace("'", "''").replace("\\", "\\\\")
        query = f"SELECT SNOWFLAKE.CORTEX.COMPLETE('{model}', '{clean_prompt}') as response"
        df = session.sql(query)
        result = df.collect()[0][0]
        return result
    except Exception as e:
        print(f"Error calling Cortex complete for model '{model}': {e}", file=sys.stderr)
        return f"ERROR: Could not get response from Cortex. Reason: {e}"

def estimate_tokens(text: str) -> int:
    """
    Rough token estimation: ~1 token per 4 characters for English text.
    More accurate for code (which has more symbols).
    """
    # Simple estimation
    simple_estimate = len(text) // 4
    
    # More accurate for code (which has more symbols)
    code_estimate = len(text.split()) * 1.3  # Words + symbols
    
    return int(max(simple_estimate, code_estimate))

def check_token_limits(prompt: str, max_tokens: int = 100000) -> tuple:
    """
    Check if prompt exceeds token limits
    Returns: (is_within_limit, estimated_tokens)
    """
    estimated = estimate_tokens(prompt)
    return (estimated <= max_tokens, estimated)

def chunk_large_file(code_text: str, max_tokens: int = 80000) -> list:
    """
    Token-aware chunking that considers prompt overhead.
    Since we don't worry about token limits anymore, we keep files together when possible.
    """
    # Reserve tokens for prompt template (~8K tokens for our enhanced prompts)
    PROMPT_OVERHEAD = 8000
    max_code_tokens = max_tokens - PROMPT_OVERHEAD
    
    # Convert tokens to approximate characters
    max_chunk_chars = max_code_tokens * 4
    
    if len(code_text) <= max_chunk_chars:
        return [code_text]
    
    lines = code_text.split('\n')
    chunks = []
    current_chunk = []
    current_size = 0
    
    for line in lines:
        line_size = len(line) + 1
        if current_size + line_size > max_chunk_chars and current_chunk:
            chunk_text = '\n'.join(current_chunk)
            estimated_tokens = estimate_tokens(chunk_text)
            print(f"  📊 Chunk created: ~{estimated_tokens:,} tokens")
            chunks.append(chunk_text)
            current_chunk = [line]
            current_size = line_size
        else:
            current_chunk.append(line)
            current_size += line_size
   
    if current_chunk:
        chunks.append('\n'.join(current_chunk))
   
    return chunks

def calculate_executive_quality_score(findings: list, total_lines_of_code: int) -> int:
    """
    Executive-level rule-based quality scoring (0-100).
    MUCH MORE BALANCED - Fixed overly harsh scoring.
   
    Scoring Logic (REALISTIC):
    - Start with base score of 100
    - Reasonable deductions that won't hit zero easily
    - Focus on actionable scoring for executives
    """
    if not findings or len(findings) == 0:
        return 100
   
    base_score = 100
    total_deductions = 0
   
    # MUCH MORE BALANCED severity weightings
    severity_weights = {
        "Critical": 12,    # Each critical issue deducts 12 points (but there should be very few)
        "High": 4,         # Each high issue deducts 4 points
        "Medium": 1.5,     # Each medium issue deducts 1.5 points
        "Low": 0.3         # Each low issue deducts 0.3 points
    }
   
    # Count issues by severity - STRICT PRECISION (NO CONVERSION)
    severity_counts = {"Critical": 0, "High": 0, "Medium": 0, "Low": 0}
    total_affected_lines = 0
   
    print(f"  📊 Scoring {len(findings)} findings...")
   
    for finding in findings:
        severity = str(finding.get("severity", "")).strip()  # Keep original case
       
        # STRICT MATCHING - NO CONVERSION TO MEDIUM
        if severity == "Critical":
            severity_counts["Critical"] += 1
        elif severity == "High":
            severity_counts["High"] += 1
        elif severity == "Medium":
            severity_counts["Medium"] += 1
        elif severity == "Low":
            severity_counts["Low"] += 1
        else:
            # LOG UNRECOGNIZED SEVERITY BUT DON'T COUNT IT
            print(f"    ⚠️ UNRECOGNIZED SEVERITY: '{severity}' in finding: {finding.get('finding', 'Unknown')[:50]}... - SKIPPING")
            continue  # Skip this finding entirely instead of converting
           
        print(f"    - {severity}: {finding.get('finding', 'No description')[:50]}...")
       
        # Count affected lines (treat N/A as 1 line)
        line_num = finding.get("line_number", "N/A")
        total_affected_lines += 1
   
    print(f"  📈 Severity breakdown: Critical={severity_counts['Critical']}, High={severity_counts['High']}, Medium={severity_counts['Medium']}, Low={severity_counts['Low']}")
   
    # Calculate REALISTIC deductions from severity
    for severity, count in severity_counts.items():
        if count > 0:
            weight = severity_weights[severity]
           
            # MUCH MORE BALANCED progressive penalty
            if severity == "Critical":
                # Critical: Should be very rare, but high impact
                if count <= 2:
                    deduction = weight * count
                else:
                    deduction = weight * 2 + (count - 2) * (weight + 3)
                # Cap critical deductions at 30 points max
                deduction = min(30, deduction)
            elif severity == "High":
                # High: Linear scaling with small bonus after 10 issues
                if count <= 10:
                    deduction = weight * count
                else:
                    deduction = weight * 10 + (count - 10) * (weight + 1)
                # Cap high severity deductions at 25 points max
                deduction = min(25, deduction)
            else:
                # Medium/Low: Pure linear scaling with caps
                deduction = weight * count
                # Reasonable caps
                if severity == "Medium":
                    deduction = min(20, deduction)
                else:
                    deduction = min(10, deduction)
               
            total_deductions += deduction
            print(f"    {severity}: {count} issues = -{deduction:.1f} points (capped)")
   
    # MUCH REDUCED penalties
    if total_lines_of_code > 0:
        affected_ratio = total_affected_lines / total_lines_of_code
        if affected_ratio > 0.4:  # Only penalize if more than 40% affected
            coverage_penalty = min(5, int(affected_ratio * 20))  # Max 5 point penalty
            total_deductions += coverage_penalty
            print(f"    Coverage penalty: -{coverage_penalty} points ({affected_ratio:.1%} affected)")
   
    # REALISTIC critical threshold penalties (should rarely trigger)
    if severity_counts["Critical"] >= 3:  # Very high threshold
        total_deductions += 10
        print(f"    Executive threshold penalty: -10 points (3+ critical issues)")
   
    if severity_counts["Critical"] + severity_counts["High"] >= 20:  # High threshold
        total_deductions += 5
        print(f"    Production readiness penalty: -5 points (20+ critical/high issues)")
   
    # Calculate final score
    final_score = max(0, base_score - int(total_deductions))
   
    print(f"  🎯 Final calculation: {base_score} - {int(total_deductions)} = {final_score}")
   
    # ADJUSTED executive score bands for more realistic scoring
    if final_score >= 85:
        return min(100, final_score)  # Excellent
    elif final_score >= 70:
        return final_score  # Good
    elif final_score >= 50:
        return final_score  # Fair - needs attention
    else:
        return max(30, final_score)  # Poor - but never below 30 for functional code

def parse_llm_json_with_retry(raw_response: str, session, model: str, max_retries: int = 2) -> dict:
    """
    Attempt to parse LLM JSON with multiple strategies and retries
    """
    # Strategy 1: Direct JSON parsing
    try:
        consolidated_json = json.loads(raw_response)
        print("  ✅ Successfully parsed consolidated JSON response")
        return consolidated_json
    except json.JSONDecodeError as e:
        print(f"  ⚠️ JSON parsing failed: {e}")
        print(f"  📝 Raw response preview: {raw_response[:500]}...")
    
    # Strategy 2: Find JSON between ```json and ```
    json_code_match = re.search(r'```json\s*(\{.*?\})\s*```', raw_response, re.DOTALL)
    if json_code_match:
        try:
            consolidated_json = json.loads(json_code_match.group(1))
            print("  ✅ Successfully extracted JSON from code block")
            return consolidated_json
        except json.JSONDecodeError:
            pass
    
    # Strategy 3: Find largest JSON-like structure
    json_matches = re.findall(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', raw_response, re.DOTALL)
    for match in sorted(json_matches, key=len, reverse=True):
        try:
            consolidated_json = json.loads(match)
            print("  ✅ Successfully extracted JSON using pattern matching")
            return consolidated_json
        except json.JSONDecodeError:
            continue
    
    # Strategy 4: Clean and fix common JSON issues
    try:
        # Common fixes for malformed JSON
        cleaned_json = raw_response
        # Fix trailing commas
        cleaned_json = re.sub(r',(\s*[}\]])', r'\1', cleaned_json)
        # Extract first complete JSON object
        json_match = re.search(r'\{.*\}', cleaned_json, re.DOTALL)
        if json_match:
            consolidated_json = json.loads(json_match.group())
            print("  ✅ Successfully parsed cleaned JSON")
            return consolidated_json
    except json.JSONDecodeError:
        pass
    
    # Strategy 5: Ask LLM to fix the JSON
    if max_retries > 0:
        print(f"  🔄 Attempting JSON repair with LLM (retries left: {max_retries})...")
        repair_prompt = f"""The following text should be valid JSON but has syntax errors. 
Please output ONLY the corrected JSON with no other text, no markdown formatting, no code blocks:

{raw_response[:10000]}
"""
        try:
            repaired = review_with_cortex(model, repair_prompt, session)
            return parse_llm_json_with_retry(repaired, session, model, max_retries - 1)
        except Exception as e:
            print(f"  ⚠️ JSON repair failed: {e}")
    
    # Strategy 6: Fallback with basic structure
    print("  ❌ All JSON parsing strategies failed, using fallback")
    return {
        "executive_summary": "JSON parsing failed - analysis completed but results may be incomplete",
        "quality_score": 75,
        "business_impact": "MEDIUM",
        "technical_debt_score": "MEDIUM",
        "security_risk_level": "MEDIUM",
        "maintainability_rating": "FAIR",
        "detailed_findings": [],
        "metrics": {"lines_of_code": 0, "complexity_score": "MEDIUM", "code_coverage_gaps": [], "dependency_risks": []},
        "strategic_recommendations": ["Review LLM output formatting", "Implement JSON validation"],
        "immediate_actions": ["Fix JSON parsing issues"],
        "previous_issues_resolved": []
    }