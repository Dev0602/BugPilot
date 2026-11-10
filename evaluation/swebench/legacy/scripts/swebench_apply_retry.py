import json
import subprocess
import re
import os

REPO_PATH = os.path.expanduser("~/Desktop/swebench_repos/django__django")
TARGET_FILE = "django/forms/widgets.py"
INSTANCE_ID = "django__django-11019"

with open("swebench_retry_result.json") as f:
    result = json.load(f)

# Fresh checkout, no leftover edits
subprocess.run(["git", "checkout", "."], cwd=REPO_PATH, capture_output=True)
subprocess.run(["git", "checkout", "0668164b4ac93a5be79f5b87fae83c657124d9ab"],
                cwd=REPO_PATH, capture_output=True)

file_path = os.path.join(REPO_PATH, TARGET_FILE)
with open(file_path) as f:
    file_contents = f.read()

func_name = result["function_name"]
simple_name = func_name.split(".")[-1]

pattern = re.compile(
    rf"^def {re.escape(simple_name)}\(.*?(?=\n^def |\n^class |\Z)",
    re.DOTALL | re.MULTILINE,
)
match = pattern.search(file_contents)
if not match:
    method_pattern = re.compile(
        rf"^(    def {re.escape(simple_name)}\(.*?)(?=\n    def |\n^class |\nclass |\Z)",
        re.DOTALL | re.MULTILINE,
    )
    match = method_pattern.search(file_contents)

if not match:
    print(f"Could not locate function {func_name}")
    exit(1)

match_start = match.start()
lines_before = file_contents[:match_start].split("\n")
idx = len(lines_before) - 1
consumed_len = 0
while idx >= 0 and lines_before[idx].strip().startswith("@"):
    consumed_len += len(lines_before[idx]) + 1
    idx -= 1
decorator_start = match_start - consumed_len

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
    ["git", "diff", TARGET_FILE], cwd=REPO_PATH, capture_output=True, text=True
)
patch_text = diff_result.stdout

subprocess.run(["git", "checkout", "."], cwd=REPO_PATH, capture_output=True)

if not patch_text.strip():
    print("Empty diff, something went wrong.")
    exit(1)

prediction = [{
    "instance_id": INSTANCE_ID,
    "model_name_or_path": "bugpilot",
    "model_patch": patch_text,
}]

with open("bugpilot_retry_final.json", "w") as f:
    json.dump(prediction, f, indent=2)

print("Patch generated:")
print(patch_text)
print("\nSaved to bugpilot_retry_final.json")
