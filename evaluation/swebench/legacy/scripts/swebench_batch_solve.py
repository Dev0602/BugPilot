import json
import os
import re
import subprocess
from datasets import load_dataset
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()
client = Anthropic()

REPOS_DIR = os.path.expanduser("~/Desktop/swebench_repos")
os.makedirs(REPOS_DIR, exist_ok=True)


def ensure_repo(repo_name):
    """Clones the repo if not already present. Returns local path."""
    local_name = repo_name.replace("/", "__")
    local_path = os.path.join(REPOS_DIR, local_name)
    if not os.path.exists(local_path):
        print(f"  Cloning {repo_name}...")
        subprocess.run(
            ["git", "clone", f"https://github.com/{repo_name}.git", local_path],
            check=True, capture_output=True
        )
    return local_path


def get_target_file(patch_text):
    """Extracts the file path being changed from a unified diff's header."""
    match = re.search(r"diff --git a/(\S+) b/\S+", patch_text)
    return match.group(1) if match else None


def solve_instance(instance):
    instance_id = instance["instance_id"]
    repo = instance["repo"]
    base_commit = instance["base_commit"]
    problem_statement = instance["problem_statement"]

    print(f"\n{'='*60}\n{instance_id}\n{'='*60}")

    repo_path = ensure_repo(repo)

    # Reset and checkout the exact buggy commit
    subprocess.run(["git", "checkout", "."], cwd=repo_path, capture_output=True)
    subprocess.run(["git", "checkout", base_commit], cwd=repo_path, capture_output=True)

    target_file = get_target_file(instance["patch"])
    if not target_file:
        print("  Could not determine target file, skipping.")
        return None

    file_path = os.path.join(repo_path, target_file)
    if not os.path.exists(file_path):
        print(f"  Target file not found: {target_file}, skipping.")
        return None

    with open(file_path) as f:
        file_contents = f.read()

    if len(file_contents) > 150000:
        print(f"  File too large ({len(file_contents)} chars), skipping.")
        return None

    prompt = f"""You are a debugging assistant working on the real
open-source project {repo}. Here is a real GitHub issue:

{problem_statement}

Here is the full contents of {target_file}, believed to contain the bug:

{file_contents}

Diagnose the bug. Identify the ONE function responsible, and provide the
full corrected code for that function only.
"""

    try:
        response = client.messages.create(
            model="claude-fable-5",
            max_tokens=8000,
            tools=[{
                "name": "submit_fix",
                "description": "Submit the diagnosis and fixed function.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "diagnosis": {"type": "string"},
                        "function_name": {"type": "string"},
                        "fixed_function_code": {"type": "string"},
                    },
                    "required": ["diagnosis", "function_name", "fixed_function_code"]
                }
            }],
            tool_choice={"type": "tool", "name": "submit_fix"},
            messages=[{"role": "user", "content": prompt}]
        )
    except Exception as e:
        print(f"  API error: {e}")
        return None

    result = None
    for block in response.content:
        if block.type == "tool_use":
            result = block.input

    if response.stop_reason == "refusal":
        print("  Model declined to complete this instance (refusal), skipping.")
        return None

    if not result or "function_name" not in result or "fixed_function_code" not in result:
        print("  Incomplete response (missing required fields), skipping.")
        return None


    print(f"  Diagnosis: {result['diagnosis'][:100]}...")

    # Apply the fix using regex find/replace, same approach as our main agent
    func_name = result['function_name']
    # Handle dotted class-method names like "RST.__init__" or "Media.merge"
    # by extracting just the method name for matching, since methods are
    # indented and the search needs to account for that.
    simple_name = func_name.split('.')[-1]

    # Try top-level function first
    pattern = re.compile(
        rf"^def {re.escape(simple_name)}\(.*?(?=\n^def |\n^class |\Z)",
        re.DOTALL | re.MULTILINE,
    )
    match = pattern.search(file_contents)

    if not match:
        # Try as an indented class method (4-space indent, common convention)
        method_pattern = re.compile(
            rf"^(    def {re.escape(simple_name)}\(.*?)(?=\n    def |\n^class |\nclass |\Z)",
            re.DOTALL | re.MULTILINE,
        )
        match = method_pattern.search(file_contents)

    if not match:
        print(f"  Could not locate function {func_name} to patch, skipping.")
        return None

    # Expand the match backwards to include any decorator lines
    # (e.g. @staticmethod, @property) directly above the function, so we
    # don't end up with a duplicate decorator if Claude's returned code
    # also includes one.
    match_start = match.start()
    lines_before = file_contents[:match_start].split("\n")
    idx = len(lines_before) - 1
    consumed_len = 0
    while idx >= 0 and lines_before[idx].strip().startswith("@"):
        consumed_len += len(lines_before[idx]) + 1
        idx -= 1
    decorator_start = match_start - consumed_len

    # Also strip any decorator lines Claude included at the top of its
    # returned code, since we're already preserving the original ones.
    fixed_code = result["fixed_function_code"].rstrip()
    fixed_lines = fixed_code.split("\n")
    while fixed_lines and fixed_lines[0].strip().startswith("@"):
        fixed_lines.pop(0)
    fixed_code = "\n".join(fixed_lines)

    new_contents = (
        file_contents[:decorator_start]
        + file_contents[decorator_start:match_start]
        + fixed_code + "\n\n"
        + file_contents[match.end():]
    )
    with open(file_path, "w") as f:
        f.write(new_contents)

    diff_result = subprocess.run(
        ["git", "diff", target_file], cwd=repo_path, capture_output=True, text=True
    )
    patch_text = diff_result.stdout

    # Reset the repo for the next instance
    subprocess.run(["git", "checkout", "."], cwd=repo_path, capture_output=True)

    if not patch_text.strip():
        print("  Empty diff produced, skipping.")
        return None

    return {
        "instance_id": instance_id,
        "model_name_or_path": "bugpilot",
        "model_patch": patch_text,
    }


def main():
    with open("swebench_batch.json") as f:
        instances = json.load(f)

    # We need the full 'patch' field too, so reload from the dataset
    ds = load_dataset("princeton-nlp/SWE-bench_Lite", split="test")
    ds_by_id = {row["instance_id"]: row for row in ds}

    predictions = []
    for inst in instances:
        full_instance = ds_by_id[inst["instance_id"]]
        pred = solve_instance(full_instance)
        if pred:
            predictions.append(pred)

    with open("bugpilot_batch_predictions.json", "w") as f:
        json.dump(predictions, f, indent=2)

    print(f"\n\nDone. {len(predictions)}/{len(instances)} predictions generated.")
    print("Saved to bugpilot_batch_predictions.json")


if __name__ == "__main__":
    main()
    
    
def retry_with_feedback(instance, previous_result, error_output):
    """Retries a fix given the real test failure output from the first attempt."""
    repo = instance["repo"]
    problem_statement = instance["problem_statement"]

    prompt = f"""You are a debugging assistant working on the real
open-source project {repo}. You previously attempted a fix for this issue:

{problem_statement}

Your previous diagnosis was:
{previous_result['diagnosis']}

Your previous fix for {previous_result['function_name']} was:
{previous_result['fixed_function_code']}

However, running the real test suite against this fix produced this error:

{error_output}

Diagnose what went wrong with your previous fix and provide a corrected
version. IMPORTANT: your fix can only replace the body of ONE function —
you cannot add new import statements at the top of the file. If your fix
needs something like `defaultdict`, either avoid needing it (e.g. use a
plain dict with manual default handling) or use the fully-qualified form
if the module is already imported elsewhere in the file.
"""

    try:
        response = client.messages.create(
            model="claude-fable-5",
            max_tokens=8000,
            tools=[{
                "name": "submit_fix",
                "description": "Submit the corrected diagnosis and fixed function.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "diagnosis": {"type": "string"},
                        "function_name": {"type": "string"},
                        "fixed_function_code": {"type": "string"},
                    },
                    "required": ["diagnosis", "function_name", "fixed_function_code"]
                }
            }],
            tool_choice={"type": "tool", "name": "submit_fix"},
            messages=[{"role": "user", "content": prompt}]
        )
    except Exception as e:
        print(f"  Retry API error: {e}")
        return None

    if response.stop_reason == "refusal":
        print("  Model declined retry.")
        return None

    result = None
    for block in response.content:
        if block.type == "tool_use":
            result = block.input

    if not result or "function_name" not in result or "fixed_function_code" not in result:
        print("  Retry produced incomplete response.")
        return None

    return result