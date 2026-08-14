import re
import time
import docker
import os
import json
from dotenv import load_dotenv
from anthropic import Anthropic
from tools import read_file, write_file, list_directory, search_code, get_function_signature, detect_requirements
from db import init_db, save_result

load_dotenv()
client = Anthropic()
docker_client = docker.from_env()

# Rough public pricing for claude-haiku-4-5 (per million tokens)
INPUT_COST_PER_M = 1.0
OUTPUT_COST_PER_M = 5.0

TOOLS = [
    {
        "name": "list_directory",
        "description": "List all files in the bug's directory.",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "search_code",
        "description": "Search all files in the bug's directory for a keyword or function name.",
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "The keyword or function name to search for."}
            },
            "required": ["keyword"]
        }
    },
    {
        "name": "submit_fix",
        "description": "Submit the diagnosis and fixed function for the bug.",
        "input_schema": {
            "type": "object",
            "properties": {
                "diagnosis": {
                    "type": "string",
                    "description": "One sentence explaining the bug."
                },
                "function_name": {
                    "type": "string",
                    "description": "The name of the function that contains the bug."
                },
                "fixed_function_code": {
                    "type": "string",
                    "description": "The full corrected code for that one function, from 'def' to its end."
                }
            },
            "required": ["diagnosis", "function_name", "fixed_function_code"]
        }
    },
    {
        "name": "get_function_signature",
        "description": "Get just the signature line (not the body) of a named function in the bug's directory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "function_name": {"type": "string", "description": "The name of the function to look up."}
            },
            "required": ["function_name"]
        }
    },
]


def parse_coverage(logs):
    """Extracts the total coverage percentage from pytest-cov output."""
    match = re.search(r"TOTAL\s+\d+\s+\d+\s+(\d+)%", logs)
    if match:
        return int(match.group(1))
    return None


def run_tests(bug_dir):
    """
    Runs pytest (with coverage) inside the sandbox for a given bug folder.
    If the project has its own requirements.txt or pyproject.toml, those
    dependencies are installed first, in the SAME container as the test
    run (installing in a separate container doesn't work — each container
    has its own isolated filesystem, so packages don't carry over).
    """
    install_cmd = detect_requirements(bug_dir)

    if install_cmd:
        full_command = f"sh -c '{install_cmd} -q && pytest -v --cov=. --cov-report=term-missing'"
        needs_network = True
    else:
        full_command = "pytest -v --cov=. --cov-report=term-missing"
        needs_network = False

    container = docker_client.containers.run(
        "bugpilot-sandbox",
        command=full_command,
        volumes={
            f"{os.getcwd()}/{bug_dir}": {"bind": "/app", "mode": "rw"}
        },
        working_dir="/app",
        detach=True,
        network_disabled=not needs_network,
    )

    result = container.wait()
    logs = container.logs().decode()
    container.remove()
    passed = result["StatusCode"] == 0
    coverage = parse_coverage(logs)
    return passed, logs, coverage

def apply_function_patch(full_code, function_name, new_function_code):
    """
    Finds a top-level function definition by name inside full_code and
    replaces it with new_function_code. Returns the updated full file text.
    """
    pattern = re.compile(
        rf"^def {re.escape(function_name)}\(.*?(?=\n^def |\Z)",
        re.DOTALL | re.MULTILINE,
    )
    match = pattern.search(full_code)
    if not match:
        raise ValueError(f"Could not find function '{function_name}' to patch.")

    new_function_code = new_function_code.rstrip() + "\n\n"
    return full_code[:match.start()] + new_function_code + full_code[match.end():]


def run_tool(tool_name, tool_input, bug_dir):
    """Executes one of our real tools and returns a text result for Claude."""
    if tool_name == "list_directory":
        files = list_directory(bug_dir)
        return f"Files in directory: {files}"

    if tool_name == "search_code":
        matches = search_code(bug_dir, tool_input["keyword"])
        if not matches:
            return f"No matches found for '{tool_input['keyword']}'."
        lines = [f"{m['file']}:{m['line_number']}: {m['line_text']}" for m in matches]
        return "\n".join(lines)
    
    if tool_name == "get_function_signature":
        return get_function_signature(bug_dir, tool_input["function_name"])

    return f"Unknown tool: {tool_name}"

def diagnose_and_fix(test_output, bug_dir, attempt_history=None, filename="calculator.py", max_tool_turns=7):
    """
    Asks Claude to diagnose the bug and propose a targeted function-level fix.
    Claude may call list_directory / search_code first to investigate before
    submitting its fix via submit_fix — this is a real multi-turn tool loop,
    not a single request/response.
    """
    code = read_file(filename, bug_dir)

    history_text = ""
    if attempt_history:
        history_text = "\n\nPrevious attempts that did NOT fix the bug:\n"
        for i, past in enumerate(attempt_history, 1):
            history_text += f"\nAttempt {i}: {past['diagnosis']}\n(This did not work.)\n"

    prompt = f"""You are a debugging assistant working inside a folder called
"{bug_dir}". A Python test is failing.

Failing test output:
{test_output}

Current contents of {filename}:
{code}
{history_text}

You may use list_directory or search_code if you need to investigate other
files in the folder before deciding on a fix. When ready, diagnose the bug,
identify the ONE function that contains it, and submit ONLY that function's
corrected code (the full function, from "def" to its end) using the
submit_fix tool.
"""

    messages = [{"role": "user", "content": prompt}]
    total_input_tokens = 0
    total_output_tokens = 0
    start_time = time.time()

    for turn in range(max_tool_turns):
        response = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=4000,
            tools=TOOLS,
            messages=messages,
        )
        total_input_tokens += response.usage.input_tokens
        total_output_tokens += response.usage.output_tokens

        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]

        # Check if Claude submitted its final fix
        for block in tool_use_blocks:
            if block.name == "submit_fix":
                result = block.input
                required = ("diagnosis", "function_name", "fixed_function_code")
                if not all(k in result for k in required):
                    raise ValueError(f"Claude's response was incomplete: {result}")
                latency = time.time() - start_time
                result["usage"] = {
                    "input_tokens": total_input_tokens,
                    "output_tokens": total_output_tokens,
                    "cost_usd": (
                        total_input_tokens / 1_000_000 * INPUT_COST_PER_M
                        + total_output_tokens / 1_000_000 * OUTPUT_COST_PER_M
                    ),
                    "latency_sec": round(latency, 2),
                    "tool_turns": turn + 1,
                }
                return result

        # Otherwise, Claude called an investigation tool — run it and continue
        if tool_use_blocks:
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in tool_use_blocks:
                print(f"  (investigating: {block.name}({block.input}))")
                output = run_tool(block.name, block.input, bug_dir)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": output,
                })
            messages.append({"role": "user", "content": tool_results})
        else:
            raise ValueError("Claude did not return a tool call.")

    raise ValueError(f"Claude did not submit a fix within {max_tool_turns} tool turns.")


def solve_bug(bug_dir, filename="calculator.py", max_attempts=3):
    """Runs the full agent loop on a single bug folder. Returns a result dict."""
    print(f"\n{'='*50}")
    print(f"BUG: {bug_dir}")
    print('='*50)

    passed, output, coverage = run_tests(bug_dir)

    if passed:
        print("Already passing — skipping.")
        return {
            "bug": bug_dir, "success": True, "attempts": 0,
            "cost_usd": 0, "latency_sec": 0,
            "diagnosis": None, "function_name": None,
            "coverage": coverage,
        }

    attempt_history = []
    total_cost = 0.0
    total_latency = 0.0

    for attempt in range(1, max_attempts + 1):
        print(f"\n--- Attempt {attempt} of {max_attempts} ---")
        if attempt > 1:
            time.sleep(1.5 * (2 ** (attempt - 2)))  # 1.5s, 3s, 6s, ...

        result = diagnose_and_fix(output, bug_dir, attempt_history, filename)
        print("Diagnosis:", result["diagnosis"])
        print(f"Patching function: {result['function_name']}")

        total_cost += result["usage"]["cost_usd"]
        total_latency += result["usage"]["latency_sec"]

        full_code = read_file(filename, bug_dir)
        try:
            patched_code = apply_function_patch(
                full_code, result["function_name"], result["fixed_function_code"]
            )
        except ValueError as e:
            print(f"Patch application failed: {e}")
            attempt_history.append({"diagnosis": result["diagnosis"], "note": "patch failed to apply"})
            continue

        write_file(filename, patched_code, bug_dir)
        passed, output, coverage = run_tests(bug_dir)

        attempt_history.append({
            "diagnosis": result["diagnosis"],
            "function_name": result["function_name"],
        })

        if passed:
            print(f" SUCCESS after {attempt} attempt(s) | cost=${total_cost:.5f} | time={total_latency:.1f}s")
            return {
                "bug": bug_dir, "success": True, "attempts": attempt,
                "cost_usd": round(total_cost, 5), "latency_sec": round(total_latency, 1),
                "diagnosis": result["diagnosis"], "function_name": result["function_name"],
                "coverage": coverage,
            }

    print(f" FAILED after {max_attempts} attempts | cost=${total_cost:.5f} | time={total_latency:.1f}s")
    return {
        "bug": bug_dir, "success": False, "attempts": max_attempts,
        "cost_usd": round(total_cost, 5), "latency_sec": round(total_latency, 1),
        "diagnosis": result["diagnosis"], "function_name": result["function_name"],
        "coverage": coverage,
    }


def main():
    init_db()
    bugs = [
        ("bugs/bug_01_calculator", "calculator.py"),
        ("bugs/bug_02_discount", "calculator.py"),
        ("bugs/bug_03_grade", "calculator.py"),
        ("bugs/bug_04_reverse", "calculator.py"),
        ("bugs/bug_05_sum_range", "calculator.py"),
        ("bugs/bug_06_mutable_default", "calculator.py"),
        ("bugs/bug_07_word_count", "calculator.py"),
        ("bugs/bug_08_factorial", "calculator.py"),
        ("bugs/bug_09_ats_exact_match", "ats_scorer.py"),
        ("bugs/bug_10_prime_checker", "calculator.py"),
        ("bugs/bug_11_safe_divide", "calculator.py"),
        ("bugs/bug_12_invalid_input", "calculator.py"),
        ("bugs/bug_13_list_index", "list_utils.py"),
        ("bugs/bug_14_dictionary", "user_utils.py"),
        ("bugs/bug_15_sets", "set_utils.py"),
        ("bugs/bug_16_string_processing", "string_utils.py"),
        ("bugs/bug_17_recursion", "factorial.py"),
        ("bugs/bug_18_algorithm", "search.py"),
        ("bugs/bug_19_empty_input", "data_utils.py"),
        ("bugs/bug_20_buzzword_detection", "text_utils.py"),
    ]

    results = [solve_bug(bug_dir, filename) for bug_dir, filename in bugs]

    os.makedirs("results", exist_ok=True)
    os.makedirs("logs", exist_ok=True)
    run_timestamp = time.strftime("%Y%m%d_%H%M%S")

    for r in results:
        bug_name = r["bug"].split("/")[-1]
        with open(f"results/{bug_name}.json", "w") as f:
            json.dump(r, f, indent=2)
            
    for r in results:
        save_result(r, run_timestamp)

    with open(f"logs/run_{run_timestamp}.json", "w") as f:
        json.dump({"timestamp": run_timestamp, "results": results}, f, indent=2)

    print(f"\n{'='*50}")
    print("SUMMARY")
    print('='*50)
    total = len(results)
    successes = sum(1 for r in results if r["success"])
    total_cost = sum(r["cost_usd"] for r in results)
    total_time = sum(r["latency_sec"] for r in results)

    for r in results:
        status = " PASSED" if r["success"] else " FAILED"
        cov = f", cov={r['coverage']}%" if r.get("coverage") is not None else ""
        print(f"{r['bug']}: {status} ({r['attempts']} attempt(s), ${r['cost_usd']:.5f}, {r['latency_sec']}s{cov})")

    print(f"\nOverall: {successes}/{total} bugs fixed ({successes/total*100:.0f}%)")
    print(f"Total cost: ${total_cost:.5f} | Total time: {total_time:.1f}s")


if __name__ == "__main__":
    main()