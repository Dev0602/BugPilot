import json
import subprocess
from anthropic import Anthropic
from dotenv import load_dotenv
from tools import list_directory, search_code, get_function_signature

load_dotenv()
client = Anthropic()

REPO_PATH = "/Users/baireddy/Desktop/swebench_astropy"
INSTANCE_ID = "astropy__astropy-12907"
PROBLEM_STATEMENT = """Modeling's `separability_matrix` does not compute separability correctly for nested CompoundModels
Consider the following model:

from astropy.modeling import models as m
from astropy.modeling.separable import separability_matrix

cm = m.Linear1D(10) & m.Linear1D(5)

It's separability matrix as you might expect is a diagonal - but nesting compound models breaks this. This feels like a bug to me, but I might be missing something?
"""

# Give Claude the actual buggy file directly, since we already know it's
# in astropy/modeling/separable.py from our manual investigation earlier
with open(f"{REPO_PATH}/astropy/modeling/separable.py") as f:
    file_contents = f.read()

prompt = f"""You are a debugging assistant working on a real open-source
Python project (astropy). Here is a real GitHub issue describing a bug:

{PROBLEM_STATEMENT}

Here is the full contents of astropy/modeling/separable.py, which is
believed to contain the bug:

{file_contents}

Diagnose the bug. Identify the ONE function responsible, and provide the
full corrected code for that function only.
"""

response = client.messages.create(
    model="claude-haiku-4-5",
    max_tokens=4000,
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

for block in response.content:
    if block.type == "tool_use":
        result = block.input
        print("Diagnosis:", result["diagnosis"])
        print("Function:", result["function_name"])
        print("\nFixed code:\n", result["fixed_function_code"])

        with open("swebench_agent_output.json", "w") as f:
            json.dump(result, f, indent=2)