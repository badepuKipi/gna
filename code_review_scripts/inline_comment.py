# inline_comment.py

import os, json, requests

# Configuration - Dynamic for new repo
GH_TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
REPO = os.environ.get("GITHUB_REPOSITORY", "your-username/LLM_CodeReview1")
PR_NUMBER = str(os.environ.get("GITHUB_PR_NUMBER") or os.environ.get("GITHUB_RUN_NUMBER", "1"))

if not GH_TOKEN:
    print("Error: GH_TOKEN or GITHUB_TOKEN environment variable required")
    exit(1)

headers = {
    "Authorization": f"token {GH_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

def get_pr_files():
    """Get list of files changed in the PR"""
    url = f"https://api.github.com/repos/{REPO}/pulls/{PR_NUMBER}/files"
    response = requests.get(url, headers=headers)
    
    if response.status_code != 200:
        print(f"Failed to get PR files: {response.status_code}")
        return []
    
    files = response.json()
    changed_files = {}
    
    for file in files:
        filename = file['filename']
        # Get the patch to understand line mappings
        patch = file.get('patch', '')
        changed_files[filename] = {
            'patch': patch,
            'status': file['status'],
            'additions': file['additions'],
            'deletions': file['deletions']
        }
        print(f"Found changed file: {filename} (status: {file['status']})")
    
    return changed_files

def parse_patch_lines(patch):
    """Parse patch to get valid line numbers for commenting"""
    if not patch:
        return set()
    
    valid_lines = set()
    current_line = 0
    
    for line in patch.split('\n'):
        if line.startswith('@@'):
            # Parse hunk header: @@ -old_start,old_count +new_start,new_count @@
            parts = line.split()
            if len(parts) >= 3:
                new_info = parts[2]  # +new_start,new_count
                if new_info.startswith('+'):
                    try:
                        new_start = int(new_info[1:].split(',')[0])
                        current_line = new_start
                    except:
                        continue
        elif line.startswith('+') and not line.startswith('+++'):
            # This is a new line that was added
            valid_lines.add(current_line)
            current_line += 1
        elif line.startswith(' '):
            # Context line
            current_line += 1
        # Lines starting with '-' are deletions, we skip incrementing for those
    
    return valid_lines

def post_pr_comment(body: str):
    """Post general PR review comment"""
    url = f"https://api.github.com/repos/{REPO}/issues/{PR_NUMBER}/comments"
    response = requests.post(url, headers=headers, json={"body": body})
    if response.status_code == 201:
        print("Posted PR comment successfully")
    else:
        print(f"Failed to post PR comment: {response.status_code}")
        print(f"Response: {response.text}")

def find_matching_file(filename, changed_files):
    """Find the actual file path in changed_files that matches the given filename"""
    # Direct match first
    if filename in changed_files:
        return filename
    
    # Try to find by basename (filename without directory)
    import os
    basename = os.path.basename(filename)
    
    for changed_file in changed_files.keys():
        if os.path.basename(changed_file) == basename:
            print(f"Matched {filename} -> {changed_file}")
            return changed_file
    
    # Try partial matching (case insensitive)
    filename_lower = filename.lower()
    for changed_file in changed_files.keys():
        if filename_lower in changed_file.lower() or os.path.basename(changed_file).lower() == filename_lower:
            print(f"Partial matched {filename} -> {changed_file}")
            return changed_file
    
    return None

def get_pr_head_sha():
    """Get the actual HEAD SHA from the PR"""
    url = f"https://api.github.com/repos/{REPO}/pulls/{PR_NUMBER}"
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        pr_data = response.json()
        head_sha = pr_data['head']['sha']
        print(f"Retrieved PR HEAD SHA: {head_sha}")
        return head_sha
    else:
        print(f"Failed to get PR data: {response.status_code}")
        return None

def post_inline_comments(comments, changed_files):
    """Post inline comments for critical issues only"""
    # Get the PR HEAD SHA directly from GitHub API
    latest_sha = get_pr_head_sha()
    
    if not latest_sha:
        print("Failed to get PR HEAD SHA, cannot post inline comments")
        return
    
    print(f"Using commit SHA: {latest_sha}")
    
    comment_url = f"https://api.github.com/repos/{REPO}/pulls/{PR_NUMBER}/comments"
    posted_count = 0
    skipped_count = 0
    
    print(f"Available changed files: {list(changed_files.keys())}")
    
    for c in comments:
        original_path = c["path"]
        line_num = c["line"]
        
        # Find the actual file path in the PR
        actual_file_path = find_matching_file(original_path, changed_files)
        
        if not actual_file_path:
            print(f"Skipping comment for {original_path}: no matching file found in PR changes")
            skipped_count += 1
            continue
        
        print(f"Processing comment for {actual_file_path} (originally {original_path}) at line {line_num}")
        
        # Check if file was deleted
        if changed_files[actual_file_path]['status'] == 'removed':
            print(f"Skipping comment for {actual_file_path}: file was deleted")
            skipped_count += 1
            continue
        
        # For new files, we can comment on any line
        # For modified files, we should only comment on changed lines
        if changed_files[actual_file_path]['status'] == 'added':
            # New file - can comment on any line up to the file length
            valid_lines = set(range(1, 1000))  # Reasonable upper bound
        else:
            # Modified file - get valid lines from patch
            valid_lines = parse_patch_lines(changed_files[actual_file_path]['patch'])
        
        # If we couldn't determine valid lines or line is not valid, try anyway
        # but use line 1 as fallback for added files
        if not valid_lines and changed_files[actual_file_path]['status'] == 'added':
            line_num = 1
        elif valid_lines and line_num not in valid_lines:
            # Try to find the closest valid line
            closest_line = min(valid_lines, key=lambda x: abs(x - line_num)) if valid_lines else 1
            print(f"Line {line_num} not in diff for {actual_file_path}, using closest line {closest_line}")
            line_num = closest_line
        
        data = {
            "body": c["body"],
            "commit_id": latest_sha,
            "path": actual_file_path,  # Use the actual file path from PR
            "side": "RIGHT",
            "line": line_num
        }
        
        response = requests.post(comment_url, headers=headers, json=data)
        if response.status_code == 201:
            print(f"Posted inline comment on {actual_file_path}:{line_num}")
            posted_count += 1
        else:
            print(f"Failed to post inline comment on {actual_file_path}:{line_num}: {response.status_code}")
            print(f"Response: {response.text}")
            
            # Try alternative approach: use position instead of line for diffs
            if response.status_code == 422:
                print(f"Retrying with line 1 for {actual_file_path}")
                data["line"] = 1
                retry_response = requests.post(comment_url, headers=headers, json=data)
                if retry_response.status_code == 201:
                    print(f"Posted inline comment on {actual_file_path}:1 (retry)")
                    posted_count += 1
                else:
                    print(f"Retry also failed: {retry_response.status_code}")
                    skipped_count += 1
            else:
                skipped_count += 1
    
    print(f"Posted {posted_count}/{len(comments)} inline comments ({skipped_count} skipped)")

if __name__ == "__main__":
    try:
        print(f"Processing review for PR #{PR_NUMBER} in {REPO}")
        
        # Get changed files in the PR
        changed_files = get_pr_files()
        if not changed_files:
            print("No changed files found in PR. Cannot post inline comments.")
            exit(1)
        
        # Read the review output
        with open("review_output.json") as f:
            review_data = json.load(f)
        
        print(f"Found {len(review_data['criticals'])} critical issues")
        
        # Post overall PR review comment
        review_body = f"""## Automated LLM Code Review


### Full Review:
{review_data['full_review']}

"""
        
        review_body += "\n*Critical issues are also posted as inline comments on specific lines where possible.*"
        
        post_pr_comment(review_body)
        
        # Prepare inline comments for critical findings only
        inline_comments = []
        for c in review_data["criticals"]:
            # Try multiple possible field names for the description
            finding_text = c.get('finding', '') or c.get('description', '') or c.get('issue', '') or c.get('message', '')
            
            # If still no description found, try to extract from other fields
            if not finding_text:
                # Try to get it from a title or summary field
                finding_text = c.get('title', '') or c.get('summary', '')
                # If still nothing, use a generic message
                if not finding_text:
                    finding_text = "Critical security or code quality issue detected"
            
            recommendation_text = c.get('recommendation', 'Please review this issue')
            line_num = c.get('line', c.get('line_number', 1))
            filename = c.get('filename', c.get('file', review_data.get('file', 'unknown.py')))
            severity = c.get('severity', 'Critical')
            
            # Convert line number to int if it's not already
            try:
                if line_num == 'N/A':
                    line_num = 1
                else:
                    line_num = int(line_num)
            except (ValueError, TypeError):
                line_num = 1
            
            # Ensure filename is relative path (remove leading ./ if present)
            if filename.startswith('./'):
                filename = filename[2:]
            
            # Format the issue description with line number
            issue_description = f"line no. {line_num}, Issue : {finding_text}"
            
            inline_comments.append({
                "path": filename,
                "line": line_num,
                "body": f"**🔴 {severity.upper()} ISSUE**\n{issue_description}\n**💡 Recommendation:** {recommendation_text}\n\n---\n*Generated by automated LLM code review*"
            })
        
        if inline_comments:
            print(f"Posting {len(inline_comments)} critical inline comments...")
            post_inline_comments(inline_comments, changed_files)
        else:
            print("No critical issues found for inline comments")
            
    except FileNotFoundError:
        print("review_output.json not found. Run cortex_python_review.py first.")
        exit(1)
    except KeyError as e:
        print(f"Error: Missing key in review data: {e}")
        print("Available keys in review data:")
        print(list(review_data.keys()))
        if 'criticals' in review_data and len(review_data['criticals']) > 0:
            print("Available keys in criticals[0]:")
            print(list(review_data['criticals'][0].keys()))
        exit(1)
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
