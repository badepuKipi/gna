# main.py

import os, sys, json, re, uuid
from pathlib import Path
import pandas as pd
from datetime import datetime

# Import from our modules
from config_and_prompts import *
from snowflake_utils import *
from review_engine import (
    get_changed_python_files,
    build_prompt_for_individual_review,
    build_prompt_for_consolidated_summary,
    review_with_cortex,
    check_token_limits,
    chunk_large_file,
    calculate_executive_quality_score,
    parse_llm_json_with_retry
)

def load_client_rules(rules_file_path: str = None) -> str:
    """
    Load optional client-specific rules from a text file.
    
    Args:
        rules_file_path: Path to the client rules file. If None, looks for 'client_rules.txt' in current directory.
    
    Returns:
        String containing client rules, or None if no file found
    """
    if not rules_file_path:
        rules_file_path = "client_rules.txt"
    
    if not os.path.exists(rules_file_path):
        print(f"  📋 No client rules file found at '{rules_file_path}' - using standard guidelines only")
        return None
    
    try:
        with open(rules_file_path, 'r', encoding='utf-8') as f:
            rules_content = f.read().strip()
        
        if not rules_content:
            print(f"  📋 Client rules file is empty - using standard guidelines only")
            return None
        
        print(f"  ✅ Loaded client-specific rules from '{rules_file_path}' ({len(rules_content)} characters)")
        return rules_content
    
    except Exception as e:
        print(f"  ⚠️ Error reading client rules file: {e}")
        return None

def format_executive_pr_display(json_response: dict, processed_files: list, current_database: str, current_schema: str) -> str:
    summary = json_response.get("executive_summary", "Technical analysis completed")
    findings = json_response.get("detailed_findings", [])
    quality_score = json_response.get("quality_score", 75)
    business_impact = json_response.get("business_impact", "MEDIUM")
    security_risk = json_response.get("security_risk_level", "MEDIUM")
    tech_debt = json_response.get("technical_debt_score", "MEDIUM")
    maintainability = json_response.get("maintainability_rating", "FAIR")
    metrics = json_response.get("metrics", {})
    strategic_recs = json_response.get("strategic_recommendations", [])
    immediate_actions = json_response.get("immediate_actions", [])
    previous_issues = json_response.get("previous_issues_resolved", [])
   
    critical_count = sum(1 for f in findings if str(f.get("severity", "")).upper() == "CRITICAL")
    high_count = sum(1 for f in findings if str(f.get("severity", "")).upper() == "HIGH")
    medium_count = sum(1 for f in findings if str(f.get("severity", "")).upper() == "MEDIUM")
    low_count = sum(1 for f in findings if str(f.get("severity", "")).upper() == "LOW")
   
    python_files = [f for f in processed_files if f.lower().endswith('.py')]
    sql_files = [f for f in processed_files if f.lower().endswith('.sql')]
   
    python_critical = sum(1 for f in findings if f.get("filename", "").lower().endswith('.py') and str(f.get("severity", "")).upper() == "CRITICAL")
    python_high = sum(1 for f in findings if f.get("filename", "").lower().endswith('.py') and str(f.get("severity", "")).upper() == "HIGH")
    sql_critical = sum(1 for f in findings if f.get("filename", "").lower().endswith('.sql') and str(f.get("severity", "")).upper() == "CRITICAL")
    sql_high = sum(1 for f in findings if f.get("filename", "").lower().endswith('.sql') and str(f.get("severity", "")).upper() == "HIGH")
   
    risk_emoji = {"LOW": "🟢", "MEDIUM": "🟡", "HIGH": "🟠", "CRITICAL": "🔴"}
    quality_emoji = "🟢" if quality_score >= 80 else ("🟡" if quality_score >= 60 else "🔴")
   
    if len(summary) < 30:
        summary = summary + " Code review analysis completed."
   
    display_text = f"""# 📊 Executive Code Review Report

**Files Analyzed:** {len(processed_files)} files | **Analysis Date:** {datetime.now().strftime('%Y-%m-%d')} | **Database:** {current_database}.{current_schema}

## 🎯 Executive Summary
{summary}

## 📈 Quality Dashboard

| Metric | Score | Status | Business Impact |
|--------|-------|--------|-----------------|
| **Overall Quality** | {quality_score}/100 | {quality_emoji} | {business_impact} Risk |
| **Security Risk** | {security_risk} | {risk_emoji.get(security_risk, "🟡")} | Critical security concerns |
| **Technical Debt** | {tech_debt} | {risk_emoji.get(tech_debt, "🟡")} | {len(findings)} items |
| **Maintainability** | {maintainability} | {risk_emoji.get(maintainability, "🟡")} | Long-term sustainability |

## 🔍 Issue Distribution

| Severity | Count | Priority Actions |
|----------|-------|------------------|
| 🔴 Critical | {critical_count} | Immediate fix required |
| 🟠 High | {high_count} | Fix within sprint |
| 🟡 Medium | {medium_count} | Plan for next release |
| 🟢 Low | {low_count} | Technical improvement |

## 📁 File Analysis Breakdown

| File Type | Count | Critical Issues | High Issues |
|-----------|-------|----------------|-------------|
| 🐍 Python | {len(python_files)} | {python_critical} | {python_high} |
| 🗄️ SQL | {len(sql_files)} | {sql_critical} | {sql_high} |

"""

    if previous_issues:
        display_text += """<details>
<summary><strong>📈 Previous Issues Resolution Status</strong> (Click to expand)</summary>

| Previous Issue | File | Line | Status | Details |
|----------------|------|------|--------|---------|
"""
        for issue in previous_issues:
            status = issue.get("status", "UNKNOWN")
            status_emoji = {"RESOLVED": "✅", "PARTIALLY_RESOLVED": "⚠️", "NOT_ADDRESSED": "❌", "WORSENED": "🔴", "NO_LONGER_APPLICABLE": "🚫"}.get(status, "❓")
           
            original_display = issue.get("original_issue", "")
            filename = issue.get("filename", "N/A")
            line_number = issue.get("line_number", "N/A")
            details_display = issue.get("details", "")
           
            display_text += f"| {original_display} | {filename} | {line_number} | {status_emoji} {status} | {details_display} |\n"
       
        display_text += "\n</details>\n\n"

    non_low_findings = [f for f in findings if str(f.get("severity", "")).upper() != "LOW"]
   
    if non_low_findings:
        display_text += """<details>
<summary><strong>🔍 Current Review Findings</strong> (Click to expand)</summary>

| Priority | File | Line | Issue | Business Impact |
|----------|------|------|-------|-----------------|
"""
       
        severity_order = {"Critical": 1, "High": 2, "Medium": 3, "Low": 4}
        sorted_findings = sorted(non_low_findings, key=lambda x: severity_order.get(str(x.get("severity", "Low")), 4))
       
        for finding in sorted_findings[:20]:
            severity = str(finding.get("severity", "Medium"))
            filename = finding.get("filename", "N/A")
            line = finding.get("line_number", "N/A")
           
            issue_display = str(finding.get("finding", ""))
            business_impact_display = str(finding.get("business_impact", ""))
           
            priority_emoji = {"Critical": "🔴", "High": "🟠", "Medium": "🟡", "Low": "🟢"}.get(severity, "🟡")
           
            display_text += f"| {priority_emoji} {severity} | {filename} | {line} | {issue_display} | {business_impact_display} |\n"
       
        display_text += "\n</details>\n\n"

    if immediate_actions:
        display_text += """<details>
<summary><strong>⚡ Immediate Actions Required</strong> (Click to expand)</summary>

"""
        for i, action in enumerate(immediate_actions, 1):
            display_text += f"{i}. {action}\n"
        display_text += "\n</details>\n\n"

    display_text += f"""---

**📋 Review Summary:** {len(findings)} findings identified | **🎯 Quality Score:** {quality_score}/100 | **⚡ Critical Issues:** {critical_count}

*🔬 Powered by Snowflake Cortex AI • Three-Stage Executive Analysis • Stored in {current_database}.{current_schema}*"""

    return display_text

def main():
    print(f"🚀 Starting Cortex Code Review System")
    
    session, cfg = get_snowflake_session()
    print(f"📋 Configuration: {cfg['account']} | User: {cfg['user']} | Database: {cfg.get('database', 'N/A')}")
    
    database_available, current_database, current_schema = setup_database_with_fallback(session, cfg)
    
    if len(sys.argv) >= 5:
        folder_to_scan = sys.argv[1]
        output_folder_path = sys.argv[2]
        try:
            pull_request_number = int(sys.argv[3]) if sys.argv[3] and sys.argv[3].strip() else None
        except (ValueError, IndexError):
            print(f"⚠️  Warning: Invalid or empty PR number '{sys.argv[3] if len(sys.argv) > 3 else 'None'}', using None")
            pull_request_number = None
        commit_sha = sys.argv[4]
        directory_mode = True
       
        print(f"📁 Command line mode: Scanning directory '{folder_to_scan}'")
        code_files = get_changed_python_files(folder_to_scan)
        if not code_files:
            print(f"❌ No Python/SQL files found in {folder_to_scan} directory using patterns {FILE_PATTERNS}")
            return
        folder_path = folder_to_scan
           
    else:
        # CHANGED SECTION: Default to current directory if SCRIPTS_DIRECTORY not set
        default_folder = SCRIPTS_DIRECTORY or "."
        code_files = get_changed_python_files(default_folder)
        if not code_files:
            print(f"❌ No Python/SQL files found in {default_folder} directory using patterns {FILE_PATTERNS}")
            return
           
        folder_path = default_folder
        output_folder_path = "output_reviews"
        pull_request_number = 0
        commit_sha = "test"
        directory_mode = False
        print(f"Running in dynamic pattern mode with {len(code_files)} code files from {folder_path}")

    if os.path.exists(output_folder_path):
        import shutil
        shutil.rmtree(output_folder_path)
    os.makedirs(output_folder_path, exist_ok=True)

    client_rules = load_client_rules()
    
    all_individual_reviews = []
    processed_files = []

    print("\n🔍 STAGE 1: Individual File Analysis...")
    print("=" * 60)
   
    for file_path in code_files:
        filename = os.path.basename(file_path)
        file_type = "SQL" if filename.lower().endswith('.sql') else "Python"
        print(f"\n--- Reviewing file: {filename} ({file_type}) ---")
        processed_files.append(filename)

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                code_content = f.read()

            if not code_content.strip():
                review_text = "No code found in file, skipping review."
            else:
                chunks = chunk_large_file(code_content)
                print(f"  File split into {len(chunks)} chunk(s)")
                
                first_chunk = chunks[0] if chunks else ""
                test_prompt = build_prompt_for_individual_review(first_chunk, filename, client_rules)
                is_within_limit, token_estimate = check_token_limits(test_prompt, MAX_TOKENS_FOR_SUMMARY_INPUT)
                print(f"  📊 Estimated prompt tokens: ~{token_estimate:,} / {MAX_TOKENS_FOR_SUMMARY_INPUT:,}")
                
                if not is_within_limit:
                    print(f"  ⚠️ WARNING: Prompt may exceed token limit! Results may be truncated.")
               
                chunk_reviews = []
                for i, chunk in enumerate(chunks):
                    chunk_name = f"{filename}_chunk_{i+1}" if len(chunks) > 1 else filename
                    print(f"  Processing chunk: {chunk_name}")
                   
                    individual_prompt = build_prompt_for_individual_review(chunk, chunk_name, client_rules)
                    review_text = review_with_cortex(MODEL, individual_prompt, session)
                    chunk_reviews.append(review_text)
               
                if len(chunk_reviews) > 1:
                    review_text = "\n\n".join([f"## Chunk {i+1}\n{review}" for i, review in enumerate(chunk_reviews)])
                else:
                    review_text = chunk_reviews[0]

            all_individual_reviews.append({
                "filename": filename,
                "review_feedback": review_text
            })

            output_filename = f"{Path(filename).stem}_individual_review.md"
            output_file_path = os.path.join(output_folder_path, output_filename)
            with open(output_file_path, 'w', encoding='utf-8') as outfile:
                outfile.write(review_text)
            print(f"  ✅ Individual review saved: {output_filename}")

        except Exception as e:
            print(f"  ❌ Error processing {filename}: {e}")
            all_individual_reviews.append({
                "filename": filename,
                "review_feedback": f"ERROR: Could not generate review. Reason: {e}"
            })

    print(f"\n🔄 STAGE 2: Executive Consolidation...")
    print("=" * 60)
    print(f"Consolidating {len(all_individual_reviews)} individual reviews...")

    if not all_individual_reviews:
        print("❌ No reviews to consolidate")
        return

    try:
        if database_available:
            setup_review_log_table(session, database_available, current_database, current_schema)

        previous_review_context = None
        if pull_request_number and pull_request_number != 0 and database_available:
            current_files_being_reviewed = processed_files
            previous_review_context = get_previous_review(session, database_available, current_database, current_schema, pull_request_number, current_files_being_reviewed, commit_sha)
            if previous_review_context:
                print("  📋 This is a subsequent commit review with previous context (filtered by current files)")
            else:
                print("  📋 This is the initial review for these files (no previous relevant findings)")
        elif not database_available:
            print("  ⚠️ Database not available - cannot retrieve previous reviews")

        combined_reviews_json = json.dumps(all_individual_reviews, indent=2)
        print(f"  Combined reviews: {len(combined_reviews_json)} characters")

        consolidation_prompt = build_prompt_for_consolidated_summary(
            combined_reviews_json,
            previous_review_context,
            pull_request_number
        )
        consolidation_prompt = consolidation_prompt.replace("{MAX_CHARS_FOR_FINAL_SUMMARY_FILE}", str(MAX_CHARS_FOR_FINAL_SUMMARY_FILE))
        consolidated_raw = review_with_cortex(MODEL, consolidation_prompt, session)
       
        consolidated_json = parse_llm_json_with_retry(consolidated_raw, session, MODEL, max_retries=2)
       
        findings = consolidated_json.get("detailed_findings", [])
        total_lines = sum(len(review.get("review_feedback", "").split('\n')) for review in all_individual_reviews)
       
        rule_based_score = calculate_executive_quality_score(findings, total_lines)
        consolidated_json["quality_score"] = rule_based_score
       
        print(f"  🎯 Rule-based quality score calculated: {rule_based_score}/100 (overriding LLM score)")

        executive_summary = format_executive_pr_display(consolidated_json, processed_files, current_database or "N/A", current_schema or "N/A")
       
        consolidated_path = os.path.join(output_folder_path, "consolidated_executive_summary.md")
        with open(consolidated_path, 'w', encoding='utf-8') as f:
            f.write(executive_summary)
        print(f"  ✅ Executive summary saved: consolidated_executive_summary.md")

        json_path = os.path.join(output_folder_path, "consolidated_data.json")
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(consolidated_json, f, indent=2)

        critical_findings = [f for f in consolidated_json.get("detailed_findings", []) if str(f.get("severity", "")).upper() == "CRITICAL"]
       
        criticals = []
        for f in critical_findings:
            critical = {
                "line": f.get("line_number", "N/A"),
                "issue": f.get("finding", "Critical issue found"),
                "recommendation": f.get("recommendation", f.get("finding", "")),
                "severity": f.get("severity", "Critical"),
                "filename": f.get("filename", "N/A"),
                "business_impact": f.get("business_impact", "No business impact specified"),
                "description": f.get("finding", "Critical issue found")
            }
            criticals.append(critical)

        critical_summary = ""
        if critical_findings:
            critical_summary = "Critical Issues Summary:\n"
            for i, finding in enumerate(critical_findings, 1):
                line_num = finding.get("line_number", "N/A")
                critical_summary += f"* **Line {line_num}:** Critical issues are also posted as inline comments on {line_num} line\n"

        review_output_data = {
            "full_review": executive_summary,
            "full_review_markdown": executive_summary,
            "full_review_json": consolidated_json,
            "criticals": criticals,
            "critical_summary": critical_summary,
            "critical_count": len(critical_findings),
            "file": processed_files[0] if processed_files else "unknown",
            "timestamp": datetime.now().isoformat()
        }

        with open("review_output.json", "w", encoding='utf-8') as f:
            json.dump(review_output_data, f, indent=2, ensure_ascii=False)
        print("  ✅ review_output.json saved for inline_comment.py compatibility")

        comparison_result = None
        if pull_request_number and pull_request_number != 0 and database_available:
            print("\n🔄 STAGE 3: LLM Comparison with Previous Review...")
            print("=" * 60)
           
            previous_review_summary = fetch_last_review_for_comparison(session, database_available, current_database, current_schema, pull_request_number, processed_files, commit_sha)
           
            if previous_review_summary:
                print("📋 Previous review found (filtered by current files). Performing LLM comparison...")
               
                formatted_prompt = PROMPT_TO_COMPARE_REVIEWS.replace(
                    "{previous_review_text}", str(previous_review_summary)
                ).replace(
                    "{new_review_text}", json.dumps(consolidated_json, indent=2)
                )
               
                comparison_result = get_llm_comparison(COMPARISON_MODEL, formatted_prompt, session)
               
                if comparison_result:
                    print("✅ LLM comparison successful")
                    print(f"📊 Comparison summary: {comparison_result.get('comparison_summary', 'No summary available')}")
                   
                    if 'issue_status' in comparison_result:
                        previous_issues_resolved = []
                        for issue_status in comparison_result.get('issue_status', []):
                            resolved_issue = {
                                "original_issue": issue_status.get('issue', ''),
                                "line_number": issue_status.get('line_number', 'N/A'),
                                "filename": issue_status.get('filename', 'N/A'),
                                "status": issue_status.get('status', 'UNKNOWN'),
                                "details": issue_status.get('reasoning', '')
                            }
                            previous_issues_resolved.append(resolved_issue)
                       
                        consolidated_json["previous_issues_resolved"] = previous_issues_resolved
                       
                        print(f"📈 Updated consolidated JSON with {len(previous_issues_resolved)} previous issue statuses (current files only)")
                       
                        executive_summary = format_executive_pr_display(consolidated_json, processed_files, current_database or "N/A", current_schema or "N/A")
                       
                        with open(consolidated_path, 'w', encoding='utf-8') as f:
                            f.write(executive_summary)
                        with open(json_path, 'w', encoding='utf-8') as f:
                            json.dump(consolidated_json, f, indent=2)
                       
                        review_output_data["full_review"] = executive_summary
                        review_output_data["full_review_markdown"] = executive_summary
                        review_output_data["full_review_json"] = consolidated_json
                       
                        with open("review_output.json", "w", encoding='utf-8') as f:
                            json.dump(review_output_data, f, indent=2, ensure_ascii=False)
                       
                        print("✅ Updated executive summary, JSON files, and review_output.json with comparison results")
                else:
                    print("⚠️ LLM comparison failed or returned no results")
            else:
                print("📋 No previous review found for comparison - this appears to be the initial review for these files")

        if pull_request_number and pull_request_number != 0 and database_available:
            store_review_log(session, database_available, current_database, current_schema, pull_request_number, commit_sha, executive_summary, consolidated_json, processed_files, comparison_result)

        if 'GITHUB_OUTPUT' in os.environ:
            delimiter = str(uuid.uuid4())
            with open(os.environ['GITHUB_OUTPUT'], 'a') as gh_out:
                gh_out.write(f'consolidated_summary_text<<{delimiter}\n')
                gh_out.write(f'{executive_summary}\n')
                gh_out.write(f'{delimiter}\n')
            print("  ✅ GitHub Actions output written")

        print(f"\n🎉 THREE-STAGE ANALYSIS COMPLETED!")
        print("=" * 60)
        print(f"📁 Files processed: {len(processed_files)}")
        print(f"🔍 Individual reviews: {len(all_individual_reviews)} (STAGE 1)")
        print(f"📊 Executive summary: 1 (STAGE 2)")
        if comparison_result:
            print(f"🔄 LLM comparison: ✅ (STAGE 3)")
            print(f"📈 Issues compared: {len(comparison_result.get('issue_status', []))}")
        else:
            print(f"🔄 LLM comparison: ❌ (No previous review or comparison failed)")
        print(f"🎯 Quality Score: {consolidated_json.get('quality_score', 'N/A')}/100")
        print(f"📈 Findings: {len(consolidated_json.get('detailed_findings', []))}")
       
        if database_available:
            print(f"💾 Database logging: ✅ APPENDED to {current_database}.{current_schema} with comparison_result")
        else:
            print(f"💾 Database logging: ❌ Not available")
       
    except Exception as e:
        print(f"❌ Consolidation error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠️ Process interrupted by user")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if 'session' in locals() and session:
            try:
                session.close()
                print("\n🔒 Snowflake session closed")
            except:
                pass
