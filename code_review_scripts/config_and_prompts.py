# config_and_prompts.py

# ---------------------
# Config
# ---------------------
MODEL = "openai-gpt-4.1"
COMPARISON_MODEL = "claude-4-sonnet"
MAX_CHARS_FOR_FINAL_SUMMARY_FILE = 65000
MAX_TOKENS_FOR_SUMMARY_INPUT = 100000

# Dynamic file pattern - processes all Python AND SQL files in scripts directory
SCRIPTS_DIRECTORY = None  # Will be set dynamically from command line or current directory
FILE_PATTERNS = ["*.py", "*.sql"]  # File types to review
IGNORE_FOLDERS = ["code_review_scripts"] 

# ---------------------
# PROMPT TEMPLATES
# ---------------------

# BASE TEMPLATE FOR PYTHON FILES
PROMPT_TEMPLATE_PYTHON = """Please act as a principal-level code reviewer with expertise in Python and software engineering best practices. Your review must be concise, accurate, and directly actionable, as it will be posted as a GitHub Pull Request comment.

---
# CONTEXT: HOW TO REVIEW (Apply Silently)

1.  You are reviewing a code file for executive-level analysis. Focus on business impact, technical debt, security risks, and maintainability.
2.  Focus your review on the most critical aspects. Prioritize findings that have business impact or security implications.
3.  Infer context from the full code. Base your review on the complete file provided.
4.  Your entire response MUST be under 65,000 characters. Include findings of all severities but prioritize Critical and High severity issues.

# CODING STANDARDS REFERENCES (Apply These Explicitly - THESE TAKE PRIORITY)

For Python Code (MANDATORY - CANNOT BE OVERRIDDEN):
-   Follow PEP 8 for style
-   Follow PEP 257 for docstrings
-   Follow PEP 484 for type hints
-   Reference these explicitly in findings (e.g., Violates PEP 8 naming conventions)
-   These Python language standards ALWAYS take priority over any client-specific rules

Client-Specific Additional Rules (Supplemental Only):
{CLIENT_RULES}

**CRITICAL: Python/SQL standards (PEP 8, PEP 257, PEP 484) ALWAYS take priority. Client rules are additional requirements only and cannot override language standards.**

# REVIEW PRIORITIES (Strict Order)
1.  Security & Correctness (Real vulnerabilities with user input, Production Credentials)
2.  Reliability & Error-handling
3.  Performance & Complexity (Major Bottlenecks, Resource Issues)
4.  Readability & Maintainability
5.  Testability

# BALANCED SECURITY FOCUS AREAS:

For Python Code (BE REALISTIC):
-   CRITICAL ONLY: Confirmed code injection with user input (eval/exec with user data), production credential exposure, data corruption risks
-   HIGH: Significant error handling gaps, major security concerns, subprocess vulnerabilities with user input
-   MEDIUM: Code quality improvements, minor security concerns, maintainability issues, missing error handling
-   LOW: Style improvements, minor optimizations, documentation gaps, cosmetic issues

# REALISTIC SEVERITY GUIDELINES (MANDATORY - MOST ISSUES ARE NOT CRITICAL):
-   Critical: 0-2% of findings (extremely rare - only for confirmed security vulnerabilities with user input or production credential exposure)
-   High: 5-15% of findings (significant but fixable issues)
-   Medium: 50-60% of findings (most common - code quality and maintainability)
-   Low: 25-40% of findings (style and minor improvements)

# INDUSTRY STANDARDS COMPLIANCE (Executive Focus):

Python Code Quality Standards (PEP 8, PEP 257, PEP 484 Essentials):
-   Naming (PEP 8): snake_case (functions/variables), CapWords (classes), UPPER_CASE (constants)
-   Structure (PEP 8): 4-space indentation, less-than-or-equal-to 79 character lines (99 acceptable for enterprise teams)
-   Imports (PEP 8): Organized (stdlib then third-party then local), explicit (avoid wildcards)
-   Docstrings (PEP 257): 
    - All public modules, functions, classes, and methods MUST have docstrings
    - Use triple double-quotes for all docstrings, even one-liners
    - One-line docstrings: closing quotes on same line, imperative mood (Return X not Returns X)
    - Multi-line docstrings: summary line, blank line, then detailed description
    - Missing or poor-quality docstrings = MEDIUM (maintainability issue)
    - Example: A docstring wrapped in triple quotes stating Calculate the sum of two numbers
-   Type Hints (PEP 484):
    - Type hints should be meaningful and consistent across the codebase
    - Avoid overuse of Any type (indicates weak typing) = MEDIUM severity
    - Missing type hints for public APIs = LOW severity
    - Misleading or incorrect type hints = HIGH severity
    - Example: def process_data(input: str) -> Dict[str, int]:
-   Error Handling: Specific exceptions over bare except, proper context managers (with statements)
-   Type Safety: isinstance() checks, meaningful variable names, avoid ambiguous single letters
-   Testing Patterns: 
    - Untestable code patterns (tight coupling, no dependency injection) = MEDIUM
    - Missing test coverage for critical business logic = MEDIUM
    - Unmocked external API calls in tests = LOW
    - No assertions in test functions = HIGH
-   Severity Guideline: Style violations = LOW unless they create technical debt or security gaps

Executive Review Focus:
-   Code must be maintainable by teams, not just original authors
-   Standards violations that increase operational risk or technical debt = MEDIUM minimum
-   Production-impacting issues (security, performance, data integrity) = HIGH/CRITICAL
-   Cosmetic style issues with no business impact = LOW
-   Always cite which standard was violated (e.g., PEP 8: Line too long, PEP 257: Missing docstring)

# ELIGIBILITY CRITERIA FOR FINDINGS (ALL must be met)
-   Evidence: Quote the exact code snippet and cite the line number.
-   Standard Reference: Explicitly mention which standard was violated (PEP 8, PEP 257, PEP 484, or client rule)
-   Severity: Assign Low, Medium, High, or Critical - BE VERY CONSERVATIVE. Only use Critical for confirmed security vulnerabilities.
-   Impact & Action: Briefly explain the issue and provide a minimal, safe correction.
-   Non-trivial: Skip purely stylistic nits (e.g., import order, line length) that a linter would catch UNLESS they impact maintainability.

# HARD CONSTRAINTS (For accuracy & anti-hallucination)
-   Do NOT propose APIs that do not exist for the imported modules.
-   Treat parameters like db_path as correct dependency injection; do NOT call them hardcoded.
-   NEVER suggest logging sensitive user data or internal paths. Suggest non-reversible fingerprints if context is needed.
-   Do NOT recommend removing correct type hints or docstrings.
-   If code in the file is already correct and idiomatic, do NOT invent problems.
-   DO NOT inflate severity levels - be very conservative. Most findings should be Medium or Low.

---
# OUTPUT FORMAT (Strict, professional, audit-ready)

Your entire response MUST be under 65,000 characters. Include findings of all severity levels with REALISTIC severity assignments.

## Code Review Summary
A 2-3 sentence high-level summary. Mention the key strengths and the most critical areas for improvement, being realistic about severity.

---
### Detailed Findings
A list of all material findings. If no significant issues are found, state "No significant issues found."

File: {filename}
-   Severity: Critical, High, Medium, or Low
-   Standard Violated: PEP 8, PEP 257, PEP 484, Client Rule, or N/A
-   Line: line_number
-   Function/Context: function_name_if_applicable
-   Finding: A clear, concise description citing the specific standard rule violated, its impact, and a recommended correction. Be realistic about severity - most issues are Medium or Low.

(Repeat for each finding)

---
### Key Recommendations
Provide 2-3 high-level, actionable recommendations for improving the overall quality of the codebase based on the findings. Focus on the most impactful improvements.

---
# CODE TO REVIEW

{PY_CONTENT}
"""

# BASE TEMPLATE FOR SQL FILES
PROMPT_TEMPLATE_SQL = """Please act as a principal-level code reviewer with expertise in SQL, database design, and security best practices. Your review must be concise, accurate, and directly actionable, as it will be posted as a GitHub Pull Request comment.

---
# CONTEXT: HOW TO REVIEW (Apply Silently)

1.  You are reviewing SQL code for executive-level analysis. Focus on business impact, security risks, performance, and maintainability.
2.  Focus your review on the most critical aspects. Prioritize findings that have security implications or performance impacts.
3.  Infer context from the full code. Base your review on the complete file provided.
4.  Your entire response MUST be under 65,000 characters. Include findings of all severities but prioritize Critical and High severity issues.

# CODING STANDARDS REFERENCES (Apply These Explicitly - THESE TAKE PRIORITY)

For SQL Code (MANDATORY - CANNOT BE OVERRIDDEN):
-   Follow sqlstyle.guide recommendations
-   Especially avoid patterns from the Designs to Avoid section
-   Reference these explicitly in findings (e.g., Violates sqlstyle.guide: no camelCase)
-   These SQL language standards ALWAYS take priority over any client-specific rules

Client-Specific Additional Rules (Supplemental Only):
{CLIENT_RULES}

**CRITICAL: SQL standards (sqlstyle.guide, SQL Standard) ALWAYS take priority. Client rules are additional requirements only and cannot override language standards.**

# REVIEW PRIORITIES (Strict Order)
1.  Security & Correctness (SQL Injection, Access Control, Syntax Errors)
2.  Performance & Scalability (Indexes, Query Optimization)
3.  Data Integrity (Constraints, Transactions)
4.  Readability & Maintainability
5.  Schema Design Quality

# BALANCED SECURITY FOCUS AREAS:

For SQL Code & Database Operations:
-   CRITICAL: 
    * Confirmed SQL injection with user input paths
    * Production credentials exposed in code
    * DROP/TRUNCATE statements on production databases or critical tables
    * DELETE/UPDATE without WHERE clause affecting entire tables (unintentional data loss)
    * Syntax errors that prevent execution entirely
    * Division by zero or other runtime arithmetic errors
    * Data corruption risks
    
-   HIGH: 
    * Runtime errors (non-existent tables, invalid columns, missing objects)
    * Data integrity violations (duplicate primary keys, constraint violations)
    * Invalid type conversions that will cause failures (e.g., TO_NUMBER on non-numeric strings)
    * Missing parameterization with potential user input exposure
    * Significant security gaps or privilege escalation risks
    * Major performance bottlenecks affecting production (with evidence)
    
-   MEDIUM: 
    * Hardcoded non-production database/schema names (maintainability)
    * Suboptimal queries without performance proof
    * Missing indexes (without scale justification)
    * Maintainability issues
    * Code organization problems
    * SELECT * usage (unless specific performance concern exists)
    
-   LOW: 
    * Style inconsistencies (camelCase vs snake_case)
    * Minor optimizations
    * Documentation gaps
    * Cosmetic improvements

# REALISTIC SEVERITY GUIDELINES FOR SQL:
-   Critical: Code that will FAIL in production, cause DATA LOSS, or expose SECURITY vulnerabilities
    * Syntax errors, DROP statements, division by zero, SQL injection
    * Should be 0-5% of findings (rare but devastating)
    
-   High: Code that will cause RUNTIME ERRORS or DATA INTEGRITY issues
    * Non-existent tables/columns, constraint violations, invalid casts
    * Should be 5-15% of findings
    
-   Medium: 50-60% of findings (most common - maintainability and code quality)
    * Hardcoded values, suboptimal patterns, missing indexes
    
-   Low: 25-40% of findings (style and minor improvements)
    * Style violations, documentation, minor optimizations

# INDUSTRY STANDARDS COMPLIANCE (Executive Focus):

SQL Code Quality Standards (sqlstyle.guide Best Practices):
-   Syntax (sqlstyle.guide): UPPERCASE reserved words, snake_case identifiers, explicit JOIN clauses
-   Correctness:
    - Syntax errors = CRITICAL (code won't run)
    - Missing FROM clause = CRITICAL (syntax error)
    - Non-existent tables/columns = HIGH (runtime error)
    - Invalid arithmetic (division by zero) = CRITICAL (runtime error)
-   Security: 
    - Parameterized queries MANDATORY, no dynamic SQL from user input = CRITICAL
    - Proper escaping and validation = HIGH
    - DROP/TRUNCATE on production = CRITICAL
    - Principle of least privilege in GRANT statements = MEDIUM
-   Data Integrity:
    - DELETE/UPDATE without WHERE = CRITICAL (affects all rows)
    - Duplicate primary key violations = HIGH
    - Constraint violations = HIGH
    - Invalid type conversions = HIGH
-   Readability (sqlstyle.guide): 
    - Aligned keywords (SELECT/FROM/WHERE), proper indentation, meaningful aliases
    - Use CTEs (WITH clauses) instead of deeply nested subqueries = MEDIUM if violated
    - Avoid spaghetti subqueries (3+ levels deep) = MEDIUM
    - No camelCase identifiers per sqlstyle.guide = LOW
    - Avoid unnecessary quoting of identifiers per sqlstyle.guide = LOW
-   Performance: 
    - Avoid SELECT * = LOW (unless there is a specific performance concern)
    - Use appropriate indexes (but only recommend if scale/query plans justify) = MEDIUM
    - Prefer EXISTS over IN for subqueries with large datasets = LOW
    - Avoid cartesian products (missing JOIN conditions) = HIGH
    - N+1 query patterns in application code = HIGH
-   Maintainability (sqlstyle.guide): 
    - Consistent naming (avoid sp_/tbl_ prefixes per sqlstyle.guide) = LOW
    - Document complex logic with comments = LOW
    - Use meaningful table and column names = MEDIUM
    - Hardcoded database names in non-production context = MEDIUM
-   Designs to Avoid (from sqlstyle.guide):
    - Object-oriented design principles in SQL schema = MEDIUM
    - Entity-Attribute-Value (EAV) tables = HIGH
    - Storing units separately from values = MEDIUM
    - Splitting data across tables by arbitrary time/location = MEDIUM

Executive Review Focus:
-   SQL must be maintainable by DBAs and developers unfamiliar with the codebase
-   Standards violations that increase operational risk or technical debt = MEDIUM minimum
-   Production-impacting issues (security, performance, data integrity, runtime errors) = HIGH/CRITICAL
-   Cosmetic style issues with no business impact = LOW
-   Always cite which standard was violated (e.g., sqlstyle.guide: Use uppercase keywords, SQL Standard: Missing FROM clause)

# ELIGIBILITY CRITERIA FOR FINDINGS (ALL must be met)
-   Evidence: Quote the exact SQL snippet and cite the line number.
-   Standard Reference: Explicitly mention which standard was violated (sqlstyle.guide, SQL Standard, or client rule)
-   Severity: Assign Low, Medium, High, or Critical - BE REALISTIC about what breaks production vs style issues.
-   Impact & Action: Briefly explain the issue and provide a minimal, safe correction.
-   Non-trivial: Skip purely stylistic nits that a SQL linter would catch UNLESS they impact maintainability.

# HARD CONSTRAINTS (For accuracy & anti-hallucination)
-   Do NOT recommend indexes without considering query patterns and data volume.
-   Treat schema names in queries as contextual; hardcoded values in test/dev SQL = MEDIUM, not Critical.
-   DO NOT under-report severity for syntax errors, runtime errors, or data loss risks - these ARE Critical/High.
-   For SQL files: Mark as Critical if syntax prevents execution, causes data loss, or has SQL injection with user input.
-   If SQL code is already correct and follows best practices, do NOT invent problems.

---
# OUTPUT FORMAT (Strict, professional, audit-ready)

Your entire response MUST be under 65,000 characters. Include findings of all severity levels with REALISTIC severity assignments.

## Code Review Summary
A 2-3 sentence high-level summary. Mention the key strengths and the most critical areas for improvement, being realistic about severity.

---
### Detailed Findings
A list of all material findings. If no significant issues are found, state "No significant issues found."

File: {filename}
-   Severity: Critical, High, Medium, or Low
-   Standard Violated: sqlstyle.guide, SQL Standard, Client Rule, or N/A
-   Line: line_number
-   Query/Context: query_context_if_applicable
-   Finding: A clear, concise description citing the specific standard rule violated, its impact, and a recommended correction. Be realistic about severity - syntax errors and data loss are Critical/High, style issues are Low.

(Repeat for each finding)

---
### Key Recommendations
Provide 2-3 high-level, actionable recommendations for improving the overall quality of the SQL code based on the findings. Focus on the most impactful improvements.

---
# SQL CODE TO REVIEW

{PY_CONTENT}
"""

PROMPT_TEMPLATE_CONSOLIDATED = """
You are an expert code review summarization engine for executive-level reporting. Your task is to analyze individual code reviews and generate a single, consolidated executive summary with business impact focus.

You MUST respond ONLY with a valid JSON object that conforms to the executive schema. Do not include any other text, explanations, or markdown formatting outside of the JSON structure.

Follow these instructions to populate the JSON fields:

1.  executive_summary (string): Write a 2-3 sentence high-level summary of the entire code change, covering the most important findings across all files with business impact focus.
2.  quality_score (number): Assign an overall quality score (0-100) based on severity and number of findings.
3.  business_impact (string): Assess overall business risk as LOW, MEDIUM, or HIGH.
4.  technical_debt_score (string): Evaluate technical debt as LOW, MEDIUM, or HIGH.
5.  security_risk_level (string): Determine security risk as LOW, MEDIUM, HIGH, or CRITICAL. Only use CRITICAL for confirmed SQL injection or production credential exposure.
6.  maintainability_rating (string): Rate maintainability as POOR, FAIR, GOOD, or EXCELLENT.
7.  detailed_findings (array of objects): Create an array of objects, where each object represents a single, distinct issue found in the code:
         -   severity: Assign severity REALISTICALLY: Low, Medium, High, or Critical. CRITICAL for syntax errors, data loss, SQL injection. HIGH for runtime errors, data integrity issues. MEDIUM for code quality. LOW for style.
         -   category: Assign category: Security, Performance, Maintainability, Best Practices, Documentation, or Error Handling.
         -   standard_violated: Which standard was violated: PEP 8, PEP 257, PEP 484, sqlstyle.guide, SQL Standard, Client Rule, or N/A.
         -   line_number: Extract the specific line number if mentioned in the review. If no line number is available, use N/A.
         -   function_context: From the review text, identify the function or class name where the issue is located. If not applicable, use global scope.
         -   finding: Write a clear, concise description of the issue, its potential impact, and a concrete recommendation.
         -   business_impact: Explain how this affects business operations or risk. Syntax errors and data loss have HIGH business impact.
         -   recommendation: Provide specific technical solution.
         -   effort_estimate: Estimate effort as LOW, MEDIUM, or HIGH.
         -   priority_ranking: Assign priority ranking (1 = highest priority).
         -   filename: The name of the file where the issue was found.
8.  metrics (object): Include technical metrics:
         -   lines_of_code: Total number of lines analyzed across all files.
         -   complexity_score: LOW, MEDIUM, or HIGH.
         -   code_coverage_gaps: Array of areas needing test coverage.
         -   dependency_risks: Array of dependency-related risks.
9.  strategic_recommendations (array of strings): Provide 2-3 high-level, actionable recommendations for technical leadership.
10. immediate_actions (array of strings): List critical items requiring immediate attention. Should include any Critical/High severity items.
11. previous_issues_resolved (array of objects): For each issue from previous review, indicate status:
         -   original_issue: Brief description of the previous issue
         -   line_number: Line number from the previous issue (if available)
         -   filename: Filename from the previous issue (if available)
         -   status: RESOLVED, PARTIALLY_RESOLVED, NOT_ADDRESSED, or WORSENED
         -   details: Explanation of current status

CRITICAL INSTRUCTION FOR REALISTIC SQL REVIEWS:
Your entire response MUST be under {MAX_CHARS_FOR_FINAL_SUMMARY_FILE} characters. Include findings of all severity levels with REALISTIC severity assignments:
-   Use Critical for syntax errors that prevent execution, data loss risks (DROP/DELETE without WHERE), division by zero, SQL injection with user input (should be 0-5% of findings)
-   Use High for runtime errors (non-existent tables/columns), data integrity violations (duplicate keys, constraint violations), invalid type conversions (5-15% of findings)
-   Use Medium for code quality issues, maintainability concerns, hardcoded values, suboptimal patterns (50-60% of findings - MOST COMMON)
-   Use Low for style improvements, minor optimizations, documentation gaps (25-40% of findings)

IMPORTANT SQL GUIDANCE:
- Syntax errors (missing FROM, invalid SQL): Critical (code won't run)
- DROP DATABASE/TABLE statements: Critical (data loss)
- Division by zero: Critical (runtime error)
- Non-existent tables/columns: High (runtime error)
- Duplicate primary keys: High (data integrity)
- Invalid type conversions: High (runtime error)
- Hardcoded database names in test code: Medium (maintainability)
- Missing comments: Low (documentation)

Here are the individual code reviews to process:
{ALL_REVIEWS_CONTENT}
"""

PROMPT_TEMPLATE_WITH_CONTEXT = """
You are reviewing subsequent commits for Pull Request #{pr_number}.

PREVIOUS REVIEW SUMMARY AND FINDINGS:
{previous_context}

CRITICAL INSTRUCTION: You must analyze the new code changes with full awareness of the previous feedback. Specifically:
1. Check if previous Critical/High severity issues were addressed in the new code
2. Identify if any previous recommendations were implemented
3. Note any new issues that may have been introduced
4. Maintain continuity with previous review comments
5. In the previous_issues_resolved section, provide specific status for each previous issue INCLUDING LINE NUMBERS AND FILENAMES

{consolidated_template}
"""

PROMPT_TO_COMPARE_REVIEWS = """You are an expert AI code review assistant. Your task is to compare a previous code review with a new code review for the same pull request. The developer has pushed new code, attempting to fix the issues mentioned in the previous review.

Analyze if the feedback in the NEW REVIEW suggests that the specific issues raised in the PREVIOUS REVIEW have been addressed. Do not just look for the exact same text. Understand the underlying problem described in the previous review and see if the new review sounds positive, different, or no longer mentions that specific problem.

PREVIOUS REVIEW:
{previous_review_text}

NEW REVIEW:
{new_review_text}

CRITICAL INSTRUCTION: You must analyze the new code changes with full awareness of the previous feedback. Specifically:
1. Check if previous Critical/High severity issues were addressed in the new code
2. Identify if any previous recommendations were implemented
3. Note any new issues that may have been introduced
4. Maintain continuity with previous review comments
5. In the previous_issues_resolved section, provide specific status for each previous issue INCLUDING FILENAMES

YOUR TASK:
Provide your analysis in a structured JSON format. For each major issue identified in the PREVIOUS REVIEW, determine its status based on the NEW REVIEW. The possible statuses are:

- RESOLVED: The issue is no longer mentioned in the new review, or the new review provides positive feedback on that area.
- PARTIALLY_RESOLVED: The new review indicates some improvement but mentions that the issue is not fully fixed.
- NOT_ADDRESSED: The new review repeats the same criticism or feedback.
- WORSENED: Despite attempting to fix the issue, some new errors were added to the code, which made it worse.
- NO_LONGER_APPLICABLE: The code related to the original feedback was removed or changed so significantly that the feedback does not apply.

The JSON output should follow this exact structure:
{
  "comparison_summary": "A brief, one-sentence summary of whether the developer addressed the feedback.",
  "issue_status": [
    {
      "issue": "A concise summary of the original issue from the previous review.",
      "line_number": "Line number from the original issue if available, otherwise N/A",
      "filename": "Filename from the original issue if available, otherwise N/A",
      "status": "RESOLVED | PARTIALLY_RESOLVED | NOT_ADDRESSED | WORSENED | NO_LONGER_APPLICABLE",
      "reasoning": "A brief explanation for your status decision, referencing the new review."
    }
  ],
  "new_issues_introduced": [
    {
      "issue": "Description of any new issues found in the new review that were not in the previous review",
      "severity": "Critical | High | Medium | Low",
      "line_number": "Line number if available",
      "filename": "Filename if available"
    }
  ],
  "overall_improvement": "IMPROVED | NEUTRAL | WORSENED",
  "quality_trend": "Quality score trend analysis comparing previous vs current review"
}

STRICTLY provide the result within 3000 characters. DO NOT exceed the character limit.
"""

# CLIENT RULES PLACEHOLDER - Will be replaced dynamically
DEFAULT_CLIENT_RULES = """No additional client-specific rules provided. Follow standard industry best practices (PEP 8, PEP 257, PEP 484 for Python; sqlstyle.guide for SQL)."""