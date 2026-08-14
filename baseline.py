import os
from dotenv import load_dotenv
from anthropic import Anthropic
from tools import read_file, write_file
from agent import run_tests

load_dotenv()
client = Anthropic()


def baseline_fix(bug_dir, filename="calculator.py"):
    """
    One-shot baseline: no tools, no sandbox reasoning, no retries.
    Just ask Claude to fix the code in a single plain-text response.
    """
    code = read_file(filename, bug_dir)

    passed, output = run_tests(bug_dir)
    if passed:
        return {"bug": bug_dir, "success": True}

    prompt = f"""Here is a failing test and the code being tested. Fix the bug.
Respond with ONLY the full corrected code, nothing else — no explanation,
no markdown formatting, no code fences.

Failing test output:
{output}

Current contents of {filename}:
{code}
"""

    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}]
    )

    fixed_code = response.content[0].text.strip()
    if fixed_code.startswith("```"):
        lines = fixed_code.split("\n")
        fixed_code = "\n".join(lines[1:-1])

    write_file(filename, fixed_code, bug_dir)
    passed, _ = run_tests(bug_dir)

    return {"bug": bug_dir, "success": passed}