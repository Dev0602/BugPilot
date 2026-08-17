import sys
import os
import subprocess
import re
from anthropic import Anthropic

target_file = sys.argv[1]

client = Anthropic()

with open(target_file) as f:
    file_contents = f.read()

prompt = f"""You are a debugging assistant. Here is the contents of
{target_file}:

{file_contents}

Analyze this file for any bugs. If you find one, identify the ONE
function responsible and provide the full corrected code for that
function only. If you find no bugs, say so clearly.
"""

response = client.messages.create(
    model="claude-fable-5",
    max_tokens=4000,
    tools=[{
        "name": "submit_fix",
        "description": "Submit the diagnosis and fixed function, or report no bug found.",
        "input_schema": {
            "type": "object",
            "properties": {
                "bug_found": {"type": "boolean"},
                "diagnosis": {"type": "string"},
                "function_name": {"type": "string"},
                "fixed_function_code": {"type": "string"},
            },
            "required": ["bug_found", "diagnosis"]
        }
    }],
    tool_choice={"type": "tool", "name": "submit_fix"},
    messages=[{"role": "user", "content": prompt}]
)

result = None
for block in response.content:
    if block.type == "tool_use":
        result = block.input

if not result or not result.get("bug_found"):
    print("No bug found.")
    diagnosis = result.get("diagnosis", "No issues detected.") if result else "No response."
    print(f"::set-output name=diagnosis::{diagnosis}")
    sys.exit(0)

print("Diagnosis:", result["diagnosis"])
print("Function:", result["function_name"])

func_name = result["function_name"]
simple_name = func_name.split(".")[-1]
pattern = re.compile(
    rf"^def {re.escape(simple_name)}\(.*?(?=\n^def |\n^class |\Z)",
    re.DOTALL | re.MULTILINE,
)
match = pattern.search(file_contents)

if not match:
    print("Could not locate function to patch.")
    sys.exit(0)

new_contents = (
    file_contents[:match.start()]
    + result["fixed_function_code"].rstrip() + "\n\n"
    + file_contents[match.end():]
)
with open(target_file, "w") as f:
    f.write(new_contents)

diff_result = subprocess.run(
    ["git", "diff", target_file], capture_output=True, text=True
)
print("\nGenerated patch:")
print(diff_result.stdout)

print(f"::set-output name=diagnosis::{result['diagnosis']}")