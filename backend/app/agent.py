import re
import time
import docker
import os
import json
import ast
import textwrap

from requests.exceptions import ReadTimeout
from dotenv import load_dotenv
from anthropic import Anthropic
from .config import (
    DEPENDENCY_INSTALL_TIMEOUT_SEC,
    INPUT_COST_PER_M,
    MAX_ATTEMPTS,
    MODEL,
    OUTPUT_COST_PER_M,
    TEST_TIMEOUT_SEC,
)
from .tools import (
    read_file,
    read_file_range,
    write_file,
    list_directory,
    search_code,
    get_function_signature,
    detect_requirements,
)
from .db import (
    init_db,
    save_result,
    save_attempt,
    save_patch,
    save_test_result,
    save_tool_call,
    start_run,
    finish_run,
)
load_dotenv()


def get_anthropic_client():
    """
    Create the Anthropic client only when an LLM request is required.

    This keeps BugPilot importable and unit-testable without requiring
    an API key for code paths that do not call the model.
    """
    try:
        return Anthropic()
    except Exception as exc:
        raise RuntimeError(
            "Anthropic client could not be initialized. "
            "Set ANTHROPIC_API_KEY before running AI repair tasks."
        ) from exc
def get_docker_client():
    """
    Create a Docker client only when Docker-backed execution is required.

    Keeping Docker initialization lazy allows BugPilot's non-Docker
    components to be imported and unit-tested even when Docker Desktop
    is not running.
    """
    try:
        docker_client = docker.from_env()
        docker_client.ping()
        return docker_client
    except docker.errors.DockerException as exc:
        raise RuntimeError(
            "Docker is not available. Start Docker Desktop before "
            "running sandboxed tests."
        ) from exc
SANDBOX_MEMORY_LIMIT = "512m"
SANDBOX_NANO_CPUS = 1_000_000_000
SANDBOX_PIDS_LIMIT = 128

TOOLS = [{'name': 'list_directory', 'description': 'Inspect the repository structure. Can list one directory level or recursively explore a bounded repository tree.', 'input_schema': {'type': 'object', 'properties': {'path': {'type': 'string', 'description': "Repository-relative directory path. Use '.' for the root.", 'default': '.'}, 'recursive': {'type': 'boolean', 'description': 'Whether to recursively list nested directories.', 'default': False}, 'max_depth': {'type': 'integer', 'description': 'Maximum recursive directory depth.', 'default': 2}}}}, {'name': 'search_code', 'description': 'Recursively search repository source files for a keyword, function, class, error message, or other text.', 'input_schema': {'type': 'object', 'properties': {'keyword': {'type': 'string', 'description': 'Text to search for.'}, 'path': {'type': 'string', 'description': 'Optional repository-relative directory to search.', 'default': '.'}}, 'required': ['keyword']}}, {'name': 'read_file', 'description': 'Read a bounded section of a repository file with line numbers. Use this after locating a potentially relevant source file.', 'input_schema': {'type': 'object', 'properties': {'filepath': {'type': 'string', 'description': 'Repository-relative file path.'}, 'start_line': {'type': 'integer', 'description': 'First line to read.', 'default': 1}, 'end_line': {'type': 'integer', 'description': 'Optional final line to read.'}}, 'required': ['filepath']}}, {'name': 'get_function_signature', 'description': 'Find Python functions or class methods by name anywhere in the repository using AST parsing.', 'input_schema': {'type': 'object', 'properties': {'function_name': {'type': 'string', 'description': 'Function or method name to locate.'}, 'path': {'type': 'string', 'description': 'Optional directory to search.', 'default': '.'}}, 'required': ['function_name']}}, {'name': 'submit_fix', 'description': 'Submit the final diagnosis and smallest safe source-code repair. Use function replacement for an existing Python function or method. Use unified_diff when the repair requires adding a function or method, changing class/module-level code, or making multiple related edits inside one existing Python source file.', 'input_schema': {'type': 'object', 'properties': {'diagnosis': {'type': 'string', 'description': 'Concise explanation of the root cause.'}, 'file_path': {'type': 'string', 'description': 'Repository-relative existing Python source file containing the bug.'}, 'repair_type': {'type': 'string', 'enum': ['replace_function', 'unified_diff'], 'description': 'Repair representation. Use replace_function for one existing function or method. Use unified_diff for a targeted single-file patch.'}, 'function_name': {'type': 'string', 'description': 'Existing function or method name for replace_function repairs. Qualified names such as ClassName.method_name are allowed.'}, 'fixed_function_code': {'type': 'string', 'description': 'Complete corrected function implementation for replace_function repairs, including the def or async def line.'}, 'unified_diff': {'type': 'string', 'description': 'Standard unified git diff for exactly one existing Python source file. Do not modify tests, create/delete files, rename files, or include unrelated edits.'}}, 'required': ['diagnosis', 'file_path']}}]


def parse_coverage(logs):
    """Extracts the total coverage percentage from pytest-cov output."""
    match = re.search(r"TOTAL\s+\d+\s+\d+\s+(\d+)%", logs)
    if match:
        return int(match.group(1))
    return None

def _sandbox_limits():
    """
    Shared Docker security/resource restrictions.

    These limits reduce the impact of buggy or generated code running
    inside BugPilot's sandbox.
    """
    return {
        "mem_limit": SANDBOX_MEMORY_LIMIT,
        "nano_cpus": SANDBOX_NANO_CPUS,
        "pids_limit": SANDBOX_PIDS_LIMIT,
        "cap_drop": ["ALL"],
        "security_opt": ["no-new-privileges:true"],
    }


def _prepare_dependency_volume(
    docker_client,
    bug_dir,
    install_cmd,
):
    """
    Install project dependencies into an isolated temporary Docker volume.

    Network access is permitted only in this preparation container.
    The repository itself is mounted read-only and copied into the
    container before installation so pip cannot modify benchmark files.

    Returns the temporary Docker volume containing installed dependencies.
    """

    dependency_volume = docker_client.volumes.create()

    source_path = os.path.abspath(bug_dir)

    if not install_cmd.startswith("pip install "):
        dependency_volume.remove(force=True)

        raise RuntimeError(
            f"Unsupported dependency install command: {install_cmd}"
        )

    isolated_install_cmd = install_cmd.replace(
        "pip install ",
        "pip install --target /deps ",
        1,
    )

    command = (
        "sh -lc '"
        "mkdir -p /workspace && "
        "cp -a /src/. /workspace/ && "
        "cd /workspace && "
        f"{isolated_install_cmd}"
        "'"
    )

    container = None

    try:
        container = docker_client.containers.run(
            "bugpilot-sandbox",
            command=command,
            volumes={
                source_path: {
                    "bind": "/src",
                    "mode": "ro",
                },
                dependency_volume.name: {
                    "bind": "/deps",
                    "mode": "rw",
                },
            },
            working_dir="/workspace",
            detach=True,

            # Network is allowed only during dependency preparation.
            network_disabled=False,

            **_sandbox_limits(),
        )

        try:
            result = container.wait(
                timeout=DEPENDENCY_INSTALL_TIMEOUT_SEC
            )

        except ReadTimeout as exc:
            try:
                container.kill()
            except docker.errors.DockerException:
                pass

            raise RuntimeError(
                "Dependency installation exceeded "
                f"{DEPENDENCY_INSTALL_TIMEOUT_SEC} seconds."
            ) from exc

        logs = container.logs().decode(
            errors="replace"
        )

        if result["StatusCode"] != 0:
            raise RuntimeError(
                "Dependency installation failed:\n"
                + logs[-4000:]
            )

        return dependency_volume

    except Exception:
        try:
            dependency_volume.remove(
                force=True
            )
        except docker.errors.DockerException:
            pass

        raise

    finally:
        if container is not None:
            try:
                container.remove(
                    force=True
                )
            except docker.errors.DockerException:
                pass


def run_tests(bug_dir):
    """
    Run pytest inside BugPilot's isolated Docker sandbox.

    Security model:

    1. Dependencies, if required, are installed in a separate temporary
       container with network access.
    2. The actual test container always runs with networking disabled.
    3. Memory, CPU, PID count, Linux capabilities, and runtime duration
       are restricted.
    4. Temporary containers and dependency volumes are cleaned up.
    """

    docker_client = get_docker_client()

    install_cmd = detect_requirements(
        bug_dir
    )

    dependency_volume = None
    container = None

    source_path = os.path.abspath(
        bug_dir
    )

    volumes = {
        source_path: {
            "bind": "/src",
            "mode": "ro",
        }
    }

    environment = {
        "PYTHONDONTWRITEBYTECODE": "1",
    }

    try:
        if install_cmd:
            dependency_volume = (
                _prepare_dependency_volume(
                    docker_client,
                    bug_dir,
                    install_cmd,
                )
            )

            volumes[
                dependency_volume.name
            ] = {
                "bind": "/deps",
                "mode": "ro",
            }

            environment[
                "PYTHONPATH"
            ] = "/deps"

        command = (
            "sh -lc '"
            "mkdir -p /tmp/workspace && "
            "cp -a /src/. /tmp/workspace/ && "
            "cd /tmp/workspace && "
            "pytest -v "
            "-p no:cacheprovider "
            "--cov=. "
            "--cov-report=term-missing"
            "'"
        )

        container = docker_client.containers.run(
            "bugpilot-sandbox",
            command=command,
            volumes=volumes,
            working_dir="/tmp",
            environment=environment,
            detach=True,

            # Generated code never receives network access.
            network_disabled=True,

            # Prevent writes to the container's root filesystem.
            # /app remains writable because it is a bind mount.
            read_only=True,

            # pytest and Python may require temporary storage.
            tmpfs={
                "/tmp": (
                    "rw,noexec,nosuid,"
                    "size=64m"
                )
            },

            **_sandbox_limits(),
        )

        try:
            result = container.wait(
                timeout=TEST_TIMEOUT_SEC
            )

        except ReadTimeout as exc:
            try:
                container.kill()
            except docker.errors.DockerException:
                pass

            logs = container.logs().decode(
                errors="replace"
            )

            raise RuntimeError(
                f"Sandbox test execution exceeded "
                f"{TEST_TIMEOUT_SEC} seconds.\n"
                f"{logs[-2000:]}"
            ) from exc

        logs = container.logs().decode(
            errors="replace"
        )

        passed = (
            result["StatusCode"] == 0
        )

        coverage = parse_coverage(
            logs
        )

        return (
            passed,
            logs,
            coverage,
        )

    finally:
        if container is not None:
            try:
                container.remove(
                    force=True
                )
            except docker.errors.DockerException:
                pass

        if dependency_volume is not None:
            try:
                dependency_volume.remove(
                    force=True
                )
            except docker.errors.DockerException:
                pass


class _PatchTargetFinder(ast.NodeVisitor):
    """
    Find Python functions, async functions, nested functions, and class methods.

    Qualified names look like:
        calculate_total
        Calculator.calculate_total
        Outer.Inner.method
        outer_function.inner_function
    """

    def __init__(self):
        self.scope = []
        self.matches = []

    def visit_ClassDef(self, node):
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def _visit_function(self, node):
        qualified_name = ".".join(self.scope + [node.name])

        self.matches.append(
            {
                "name": node.name,
                "qualified_name": qualified_name,
                "node": node,
            }
        )

        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_FunctionDef(self, node):
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node):
        self._visit_function(node)


def _clean_function_code(code):
    """
    Normalize function code returned by the model.

    Markdown code fences are removed and indentation is normalized.
    """
    code = code.strip()

    if code.startswith("```"):
        lines = code.splitlines()

        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        code = "\n".join(lines)

    return textwrap.dedent(code).strip("\n")


def apply_function_patch(full_code, function_name, new_function_code):
    """
    Replace one Python function or method using AST source locations.

    Supports:
      - top-level functions
      - class methods
      - decorated functions/methods
      - async functions
      - nested functions
      - qualified names such as MyClass.my_method

    If an unqualified name matches multiple functions, patching is rejected
    instead of guessing.
    """

    try:
        tree = ast.parse(full_code)
    except SyntaxError as exc:
        raise ValueError(
            f"Target file contains invalid Python syntax: {exc}"
        ) from exc

    finder = _PatchTargetFinder()
    finder.visit(tree)

    if "." in function_name:
        candidates = [
            match
            for match in finder.matches
            if match["qualified_name"] == function_name
        ]
    else:
        candidates = [
            match
            for match in finder.matches
            if match["name"] == function_name
        ]

    if not candidates:
        available = ", ".join(
            match["qualified_name"]
            for match in finder.matches[:20]
        )

        raise ValueError(
            f"Could not find function '{function_name}'. "
            f"Available functions include: {available}"
        )

    if len(candidates) > 1:
        names = ", ".join(
            match["qualified_name"]
            for match in candidates
        )

        raise ValueError(
            f"Function name '{function_name}' is ambiguous. "
            f"Use one of these qualified names: {names}"
        )

    target = candidates[0]["node"]

    if target.end_lineno is None:
        raise ValueError(
            f"Python AST did not provide an end line for '{function_name}'."
        )

    cleaned_code = _clean_function_code(new_function_code)

    try:
        replacement_tree = ast.parse(cleaned_code)
    except SyntaxError as exc:
        raise ValueError(
            f"Generated replacement contains invalid Python syntax: {exc}"
        ) from exc

    replacement_functions = [
        node
        for node in replacement_tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]

    if len(replacement_functions) != 1:
        raise ValueError(
            "Replacement must contain exactly one function definition."
        )

    replacement_function = replacement_functions[0]

    if replacement_function.name != target.name:
        raise ValueError(
            f"Replacement function is named '{replacement_function.name}', "
            f"but BugPilot is trying to patch '{target.name}'."
        )

    if replacement_function.decorator_list:
        raise ValueError(
            "Do not include decorators in fixed_function_code. "
            "BugPilot preserves the target function's existing decorators."
        )

    source_lines = full_code.splitlines(keepends=True)

    # FunctionDef.lineno points at the def/async def line, not its decorators.
    # Existing decorators therefore remain untouched.
    start_line = target.lineno - 1
    end_line = target.end_lineno

    original_line = source_lines[start_line]
    indentation = original_line[
        : len(original_line) - len(original_line.lstrip())
    ]

    replacement_lines = cleaned_code.splitlines()

    indented_replacement = "\n".join(
        indentation + line if line.strip() else ""
        for line in replacement_lines
    )
    indented_replacement = indented_replacement.rstrip() + "\n"

    patched_code = (
        "".join(source_lines[:start_line])
        + indented_replacement
        + "".join(source_lines[end_line:])
    )

    try:
        ast.parse(patched_code)
    except SyntaxError as exc:
        raise ValueError(
            f"Patched file would contain invalid Python syntax: {exc}"
        ) from exc

    return patched_code


def run_tool(tool_name, tool_input, bug_dir):
    """Execute a repository investigation tool for Claude."""

    try:
        if tool_name == "list_directory":
            files = list_directory(
                bug_dir,
                path=tool_input.get("path", "."),
                recursive=tool_input.get("recursive", False),
                max_depth=tool_input.get("max_depth", 2),
            )

            if not files:
                return "No files found."

            return "\n".join(files)

        if tool_name == "search_code":
            matches = search_code(
                bug_dir,
                tool_input["keyword"],
                path=tool_input.get("path", "."),
            )

            if not matches:
                return f"No matches found for '{tool_input['keyword']}'."

            return "\n".join(
                f"{match['file']}:{match['line_number']}: "
                f"{match['line_text']}"
                for match in matches
            )

        if tool_name == "read_file":
            return read_file_range(
                tool_input["filepath"],
                bug_dir,
                start_line=tool_input.get("start_line", 1),
                end_line=tool_input.get("end_line"),
            )

        if tool_name == "get_function_signature":
            return get_function_signature(
                bug_dir,
                tool_input["function_name"],
                path=tool_input.get("path", "."),
            )

        return f"Unknown tool: {tool_name}"

    except Exception as exc:
        return f"Tool error ({type(exc).__name__}): {exc}"

def diagnose_and_fix(
    test_output,
    bug_dir,
    attempt_history=None,
    max_tool_turns=10,
    attempt_id=None,
):
    """
    Ask Claude to investigate the repository, locate the responsible file and
    function, diagnose the failure, and submit a targeted repair.

    Invalid or incomplete submit_fix calls are returned to the model as tool
    errors so Claude can correct the submission instead of crashing the run.

    When attempt_id is provided, repository tool activity is persisted to the
    SQLite observability database.
    """

    history_text = ""

    if attempt_history:
        history_text = (
            "\nPrevious repair attempts that did NOT fix the bug:\n"
        )

        for index, past in enumerate(
            attempt_history,
            1,
        ):
            history_text += (
                f"\nAttempt {index}:\n"
                f"File: {past.get('file_path', 'unknown')}\n"
                f"Function: {past.get('function_name', 'unknown')}\n"
                f"Diagnosis: {past.get('diagnosis', 'unknown')}\n"
                f"Outcome: {past.get('note', 'unknown')}\n"
            )

            verification_output = past.get(
                "verification_output"
            )

            if verification_output:
                history_text += (
                    "Verification output from that failed repair:\n"
                    f"{verification_output[-2000:]}\n"
                )

    prompt = f"""
You are BugPilot, an autonomous software debugging agent.

You are working inside the repository:

{bug_dir}

A test is currently failing.

ORIGINAL FAILING TEST OUTPUT
----------------------------
{test_output}

{history_text}

You are NOT given the source file containing the bug.

Investigate the repository yourself.

Recommended workflow:

1. Inspect the repository structure.
2. Use the failing test/error information to search for relevant symbols,
   functions, classes, strings, or files.
3. Read the relevant source code.
4. Determine the root cause.
5. Identify the exact source file and function containing the bug.
6. Submit a targeted repair using submit_fix.

Do not guess a file without inspecting the repository.

Before submitting a repair, perform a focused correctness review:

1. Identify the required behavior and important invariants from the issue,
   existing implementation, and relevant tests.
2. Mentally check the proposed change against the reported failure, normal
   inputs, boundary cases, and nested or reordered inputs where applicable.
3. Preserve semantic contracts. For equality and hashing, compare actual
   normalized values rather than equating objects by hash values; ensure
   equivalent objects have equal hashes.
4. For parsers, formatters, and text-processing functions, account for escaped
   delimiters, literal characters, placeholders, and mixed inputs.
5. Check that the change does not unintentionally break nearby behavior.
   Use available testing tools when possible; never claim tests were run
   unless their results were actually observed.
6. If your proposed change does not satisfy these checks, revise it before
   calling submit_fix.


Do not modify test files.

Previous failed repairs have been rolled back, so the repository starts from
its original broken state on every retry.

Use previous-attempt evidence to avoid repeating an identical failed repair.

Prefer the smallest correct source-code change that fixes the failure without
breaking existing behavior.

When you have enough evidence, call submit_fix with ALL FOUR fields:

- diagnosis
- file_path
- function_name
- fixed_function_code

Do not embed one field inside another field.
"""

    messages = [
        {
            "role": "user",
            "content": prompt,
        }
    ]

    total_input_tokens = 0
    total_output_tokens = 0
    tool_sequence = 0

    start_time = time.time()
    anthropic_client = get_anthropic_client()

    required_submit_fields = (
        "diagnosis",
        "file_path",
        "function_name",
        "fixed_function_code",
    )

    def trace_tool_call(
        sequence_number,
        tool_name,
        tool_input,
        output_text,
        is_error=False,
        duration_ms=None,
    ):
        """
        Persist one agent tool event. Database tracing is optional and must
        never interrupt BugPilot's repair process.
        """

        if attempt_id is None:
            return

        try:
            save_tool_call(
                attempt_id=attempt_id,
                sequence_number=sequence_number,
                tool_name=tool_name,
                tool_input=tool_input,
                output_text=output_text,
                is_error=is_error,
                duration_ms=duration_ms,
            )
        except Exception as exc:
            print(
                "  (tool trace warning: "
                f"{type(exc).__name__}: {exc})"
            )

    for turn in range(max_tool_turns):
        response = anthropic_client.messages.create(
            model=MODEL,
            max_tokens=4000,
            tools=TOOLS,
            messages=messages,
        )

        total_input_tokens += response.usage.input_tokens
        total_output_tokens += response.usage.output_tokens

        tool_use_blocks = [
            block
            for block in response.content
            if block.type == "tool_use"
        ]

        if not tool_use_blocks:
            raise ValueError(
                "Claude did not return a tool call."
            )

        # Claude's tool call must appear in the conversation before its
        # corresponding tool_result message.
        messages.append(
            {
                "role": "assistant",
                "content": response.content,
            }
        )

        tool_results = []

        for block in tool_use_blocks:
            tool_sequence += 1

            if block.name == "submit_fix":
                result = block.input

                if not isinstance(result, dict):
                    error_message = (
                        "submit_fix input must be an object. "
                        "Call submit_fix again with diagnosis, "
                        "file_path, function_name, and fixed_function_code."
                    )

                    trace_tool_call(
                        sequence_number=tool_sequence,
                        tool_name="submit_fix",
                        tool_input=result,
                        output_text=error_message,
                        is_error=True,
                    )

                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "is_error": True,
                            "content": error_message,
                        }
                    )
                    continue

                missing_fields = [
                    field
                    for field in required_submit_fields
                    if (
                        field not in result
                        or result[field] is None
                        or (
                            isinstance(result[field], str)
                            and not result[field].strip()
                        )
                    )
                ]

                if missing_fields:
                    print(
                        "  (invalid submit_fix: missing "
                        + ", ".join(missing_fields)
                        + ")"
                    )

                    error_message = (
                        "submit_fix is incomplete. Missing or empty fields: "
                        + ", ".join(missing_fields)
                        + ". Call submit_fix again with ALL FOUR fields: "
                        "diagnosis, file_path, function_name, and "
                        "fixed_function_code. Do not embed one field inside "
                        "another field."
                    )

                    trace_tool_call(
                        sequence_number=tool_sequence,
                        tool_name="submit_fix",
                        tool_input=result,
                        output_text=error_message,
                        is_error=True,
                    )

                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "is_error": True,
                            "content": error_message,
                        }
                    )
                    continue

                latency = time.time() - start_time

                trace_tool_call(
                    sequence_number=tool_sequence,
                    tool_name="submit_fix",
                    tool_input=result,
                    output_text="Fix accepted for patch application.",
                    is_error=False,
                )

                result["usage"] = {
                    "input_tokens": total_input_tokens,
                    "output_tokens": total_output_tokens,
                    "cost_usd": (
                        total_input_tokens
                        / 1_000_000
                        * INPUT_COST_PER_M
                        + total_output_tokens
                        / 1_000_000
                        * OUTPUT_COST_PER_M
                    ),
                    "latency_sec": round(latency, 2),
                    "tool_turns": turn + 1,
                }

                return result

            print(
                f"  (investigating: {block.name}({block.input}))"
            )

            tool_started = time.time()
            output = run_tool(
                block.name,
                block.input,
                bug_dir,
            )
            tool_duration_ms = (time.time() - tool_started) * 1000

            tool_failed = (
                output.startswith("Tool error (")
                or output.startswith("Unknown tool:")
            )

            trace_tool_call(
                sequence_number=tool_sequence,
                tool_name=block.name,
                tool_input=block.input,
                output_text=output,
                is_error=tool_failed,
                duration_ms=round(tool_duration_ms, 2),
            )

            tool_result = {
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": output,
            }

            if tool_failed:
                tool_result["is_error"] = True

            tool_results.append(tool_result)

        # Invalid submit_fix calls and normal investigation tools return here
        # so Claude can continue with another tool turn.
        messages.append(
            {
                "role": "user",
                "content": tool_results,
            }
        )

    raise ValueError(
        "Claude did not submit a valid fix "
        f"within {max_tool_turns} tool turns."
    )


def _repair_fingerprint(result):
    """
    Create a normalized identity for a repair proposal.

    Used to detect an identical failed repair being proposed again.
    """

    diagnosis = " ".join(
        result["diagnosis"].lower().split()
    )

    fixed_code = "\n".join(
        line.rstrip()
        for line in result["fixed_function_code"]
        .strip()
        .splitlines()
    )

    return (
        result["file_path"],
        result["function_name"],
        diagnosis,
        fixed_code,
    )
       
def solve_bug(bug_dir, max_attempts=MAX_ATTEMPTS, run_id=None):
    """
    Run the complete BugPilot repair loop for one repository.

    Every failed repair is rolled back so each retry starts from
    the original broken repository state.

    When run_id is provided, attempt, patch, and test history is
    persisted to SQLite for observability and dashboard replay.
    """

    print(f"\n{'=' * 50}")
    print(f"BUG: {bug_dir}")
    print("=" * 50)

    def trace_db(
        function,
        *args,
        **kwargs,
    ):
        """
        Observability must never break the repair pipeline.

        If no run_id was supplied, tracing is disabled. This also
        keeps unit tests independent from the SQLite database.
        """

        if run_id is None:
            return None

        try:
            return function(
                *args,
                **kwargs,
            )

        except Exception as exc:
            print(
                "  (database trace warning: "
                f"{type(exc).__name__}: {exc})"
            )

            return None

    initial_test_started = time.time()

    (
        passed,
        initial_test_output,
        coverage,
    ) = run_tests(
        bug_dir
    )

    initial_test_duration = (
        time.time()
        - initial_test_started
    )

    if passed:
        print(
            "Already passing — skipping."
        )

        return {
            "bug": bug_dir,
            "success": True,
            "attempts": 0,
            "cost_usd": 0,
            "latency_sec": 0,
            "diagnosis": None,
            "file_path": None,
            "function_name": None,
            "coverage": coverage,
            "stop_reason": (
                "already_passing"
            ),
        }

    attempt_history = []

    failed_fingerprints = set()

    total_cost = 0.0
    total_latency = 0.0

    result = None

    attempts_executed = 0

    stop_reason = (
        "max_attempts_reached"
    )

    for attempt in range(
        1,
        max_attempts + 1,
    ):
        attempts_executed = attempt

        print(
            f"\n--- Attempt {attempt} "
            f"of {max_attempts} ---"
        )

        if attempt > 1:
            delay = (
                1.5
                * (
                    2
                    ** (
                        attempt - 2
                    )
                )
            )

            print(
                f"Waiting {delay:.1f}s "
                "before retry..."
            )

            time.sleep(delay)

        # ---------------------------------------------
        # Create attempt record before asking Claude.
        # ---------------------------------------------
        attempt_id = trace_db(
            save_attempt,
            run_id,
            bug_dir,
            attempt,
            status="started",
        )

        # Store the original failing test once.
        if (
            attempt == 1
            and attempt_id is not None
        ):
            trace_db(
                save_test_result,
                attempt_id,
                phase="initial",
                passed=False,
                coverage=coverage,
                logs=initial_test_output,
                duration_sec=round(
                    initial_test_duration,
                    3,
                ),
            )

        try:
            if attempt_id is None:
                result = diagnose_and_fix(
                    initial_test_output,
                    bug_dir,
                    attempt_history,
                )
            else:
                result = diagnose_and_fix(
                    initial_test_output,
                    bug_dir,
                    attempt_history,
                    attempt_id=attempt_id,
                )

        except Exception as exc:
            if attempt_id is not None:
                trace_db(
                    save_attempt,
                    run_id,
                    bug_dir,
                    attempt,
                    status="agent_error",
                    verification_output=str(
                        exc
                    ),
                    stop_reason=(
                        "agent_error"
                    ),
                )

            raise

        print(
            "Diagnosis:",
            result["diagnosis"],
        )

        print(
            "Target file: "
            f"{result['file_path']}"
        )

        print(
            "Patching function: "
            f"{result['function_name']}"
        )

        usage = result.get(
            "usage",
            {},
        )

        attempt_cost = float(
            usage.get(
                "cost_usd",
                0,
            )
            or 0
        )

        attempt_latency = float(
            usage.get(
                "latency_sec",
                0,
            )
            or 0
        )

        total_cost += attempt_cost

        total_latency += (
            attempt_latency
        )

        # Update the attempt after diagnosis.
        if attempt_id is not None:
            trace_db(
                save_attempt,
                run_id,
                bug_dir,
                attempt,
                status="diagnosed",
                diagnosis=result.get(
                    "diagnosis"
                ),
                file_path=result.get(
                    "file_path"
                ),
                function_name=result.get(
                    "function_name"
                ),
                input_tokens=usage.get(
                    "input_tokens"
                ),
                output_tokens=usage.get(
                    "output_tokens"
                ),
                tool_turns=usage.get(
                    "tool_turns"
                ),
                cost_usd=attempt_cost,
                latency_sec=(
                    attempt_latency
                ),
            )

        fingerprint = (
            _repair_fingerprint(
                result
            )
        )

        # ---------------------------------------------
        # Repeated-repair early stopping.
        # ---------------------------------------------
        if (
            fingerprint
            in failed_fingerprints
        ):
            print(
                "Stopping early: Claude "
                "repeated an identical repair "
                "proposal that already failed."
            )

            stop_reason = (
                "repeated_failed_repair"
            )

            if attempt_id is not None:
                trace_db(
                    save_attempt,
                    run_id,
                    bug_dir,
                    attempt,
                    status=(
                        "repeated_repair"
                    ),
                    diagnosis=result.get(
                        "diagnosis"
                    ),
                    file_path=result.get(
                        "file_path"
                    ),
                    function_name=result.get(
                        "function_name"
                    ),
                    input_tokens=usage.get(
                        "input_tokens"
                    ),
                    output_tokens=usage.get(
                        "output_tokens"
                    ),
                    tool_turns=usage.get(
                        "tool_turns"
                    ),
                    cost_usd=attempt_cost,
                    latency_sec=(
                        attempt_latency
                    ),
                    stop_reason=(
                        "repeated_failed_repair"
                    ),
                )

            break

        target_file = (
            result["file_path"]
        )

        # Save exact original repository state.
        original_code = read_file(
            target_file,
            bug_dir,
        )

        try:
            patched_code = (
                apply_function_patch(
                    original_code,
                    result[
                        "function_name"
                    ],
                    result[
                        "fixed_function_code"
                    ],
                )
            )

        except ValueError as exc:
            print(
                "Patch application failed: "
                f"{exc}"
            )

            failed_fingerprints.add(
                fingerprint
            )

            attempt_history.append(
                {
                    "diagnosis": (
                        result[
                            "diagnosis"
                        ]
                    ),
                    "file_path": (
                        result[
                            "file_path"
                        ]
                    ),
                    "function_name": (
                        result[
                            "function_name"
                        ]
                    ),
                    "note": (
                        "patch could not "
                        "be applied"
                    ),
                    "verification_output": (
                        str(exc)
                    ),
                }
            )

            if attempt_id is not None:
                trace_db(
                    save_attempt,
                    run_id,
                    bug_dir,
                    attempt,
                    status="patch_error",
                    diagnosis=result.get(
                        "diagnosis"
                    ),
                    file_path=result.get(
                        "file_path"
                    ),
                    function_name=result.get(
                        "function_name"
                    ),
                    input_tokens=usage.get(
                        "input_tokens"
                    ),
                    output_tokens=usage.get(
                        "output_tokens"
                    ),
                    tool_turns=usage.get(
                        "tool_turns"
                    ),
                    cost_usd=attempt_cost,
                    latency_sec=(
                        attempt_latency
                    ),
                    verification_output=(
                        str(exc)
                    ),
                    stop_reason=(
                        "patch_apply_error"
                    ),
                )

            continue

        write_file(
            target_file,
            patched_code,
            bug_dir,
        )

        # Save the actual full-file patch.
        if attempt_id is not None:
            trace_db(
                save_patch,
                attempt_id,
                file_path=target_file,
                function_name=result.get(
                    "function_name"
                ),
                original_code=(
                    original_code
                ),
                patched_code=(
                    patched_code
                ),
                applied=True,
            )

        verification_started = (
            time.time()
        )

        try:
            (
                passed,
                verification_output,
                coverage,
            ) = run_tests(
                bug_dir
            )

        except Exception as exc:
            # Never leave the repository mutated
            # when verification itself crashes.
            write_file(
                target_file,
                original_code,
                bug_dir,
            )

            if attempt_id is not None:
                trace_db(
                    save_attempt,
                    run_id,
                    bug_dir,
                    attempt,
                    status=(
                        "verification_error"
                    ),
                    diagnosis=result.get(
                        "diagnosis"
                    ),
                    file_path=result.get(
                        "file_path"
                    ),
                    function_name=result.get(
                        "function_name"
                    ),
                    input_tokens=usage.get(
                        "input_tokens"
                    ),
                    output_tokens=usage.get(
                        "output_tokens"
                    ),
                    tool_turns=usage.get(
                        "tool_turns"
                    ),
                    cost_usd=attempt_cost,
                    latency_sec=(
                        attempt_latency
                    ),
                    verification_output=(
                        str(exc)
                    ),
                    stop_reason=(
                        "verification_error"
                    ),
                )

            raise

        verification_duration = (
            time.time()
            - verification_started
        )

        if attempt_id is not None:
            trace_db(
                save_test_result,
                attempt_id,
                phase="verification",
                passed=passed,
                coverage=coverage,
                logs=(
                    verification_output
                ),
                duration_sec=round(
                    verification_duration,
                    3,
                ),
            )

        # ---------------------------------------------
        # Successful repair.
        # ---------------------------------------------
        if passed:
            if attempt_id is not None:
                trace_db(
                    save_attempt,
                    run_id,
                    bug_dir,
                    attempt,
                    status="passed",
                    diagnosis=result.get(
                        "diagnosis"
                    ),
                    file_path=result.get(
                        "file_path"
                    ),
                    function_name=result.get(
                        "function_name"
                    ),
                    input_tokens=usage.get(
                        "input_tokens"
                    ),
                    output_tokens=usage.get(
                        "output_tokens"
                    ),
                    tool_turns=usage.get(
                        "tool_turns"
                    ),
                    cost_usd=attempt_cost,
                    latency_sec=(
                        attempt_latency
                    ),
                    verification_output=(
                        verification_output
                    ),
                    stop_reason=(
                        "tests_passed"
                    ),
                )

            print(
                f"✓ SUCCESS after "
                f"{attempt} attempt(s) | "
                f"cost=${total_cost:.5f} | "
                f"time={total_latency:.1f}s"
            )

            return {
                "bug": bug_dir,
                "success": True,
                "attempts": attempt,
                "cost_usd": round(
                    total_cost,
                    5,
                ),
                "latency_sec": round(
                    total_latency,
                    1,
                ),
                "diagnosis": (
                    result[
                        "diagnosis"
                    ]
                ),
                "file_path": (
                    result[
                        "file_path"
                    ]
                ),
                "function_name": (
                    result[
                        "function_name"
                    ]
                ),
                "coverage": coverage,
                "stop_reason": (
                    "tests_passed"
                ),
            }

        # ---------------------------------------------
        # Patch applied but tests still failed.
        # ---------------------------------------------
        print(
            "Patch applied, but "
            "verification tests are "
            "still failing."
        )

        failed_fingerprints.add(
            fingerprint
        )

        attempt_history.append(
            {
                "diagnosis": (
                    result[
                        "diagnosis"
                    ]
                ),
                "file_path": (
                    result[
                        "file_path"
                    ]
                ),
                "function_name": (
                    result[
                        "function_name"
                    ]
                ),
                "note": (
                    "patch applied "
                    "successfully, but "
                    "verification failed"
                ),
                "verification_output": (
                    verification_output
                ),
            }
        )

        if attempt_id is not None:
            trace_db(
                save_attempt,
                run_id,
                bug_dir,
                attempt,
                status=(
                    "failed_verification"
                ),
                diagnosis=result.get(
                    "diagnosis"
                ),
                file_path=result.get(
                    "file_path"
                ),
                function_name=result.get(
                    "function_name"
                ),
                input_tokens=usage.get(
                    "input_tokens"
                ),
                output_tokens=usage.get(
                    "output_tokens"
                ),
                tool_turns=usage.get(
                    "tool_turns"
                ),
                cost_usd=attempt_cost,
                latency_sec=(
                    attempt_latency
                ),
                verification_output=(
                    verification_output
                ),
                stop_reason=(
                    "verification_failed"
                ),
            )

        # Critical benchmark behavior:
        # retry from original broken source.
        write_file(
            target_file,
            original_code,
            bug_dir,
        )

        print(
            "Rolled back failed repair; "
            "repository restored for "
            "next attempt."
        )

    print(
        f"✗ FAILED after "
        f"{attempts_executed} attempt(s) | "
        f"cost=${total_cost:.5f} | "
        f"time={total_latency:.1f}s | "
        f"reason={stop_reason}"
    )

    return {
        "bug": bug_dir,
        "success": False,
        "attempts": (
            attempts_executed
        ),
        "cost_usd": round(
            total_cost,
            5,
        ),
        "latency_sec": round(
            total_latency,
            1,
        ),
        "diagnosis": (
            result["diagnosis"]
            if result
            else None
        ),
        "file_path": (
            result["file_path"]
            if result
            else None
        ),
        "function_name": (
            result[
                "function_name"
            ]
            if result
            else None
        ),
        "coverage": coverage,
        "stop_reason": stop_reason,
    }

def main():
    init_db()

    bugs = [
        "bugs/bug_01_calculator",
        "bugs/bug_02_discount",
        "bugs/bug_03_grade",
        "bugs/bug_04_reverse",
        "bugs/bug_05_sum_range",
        "bugs/bug_06_mutable_default",
        "bugs/bug_07_word_count",
        "bugs/bug_08_factorial",
        "bugs/bug_09_ats_exact_match",
        "bugs/bug_10_prime_checker",
        "bugs/bug_11_safe_divide",
        "bugs/bug_12_invalid_input",
        "bugs/bug_13_list_index",
        "bugs/bug_14_dictionary",
        "bugs/bug_15_sets",
        "bugs/bug_16_string_processing",
        "bugs/bug_17_recursion",
        "bugs/bug_18_algorithm",
        "bugs/bug_19_empty_input",
        "bugs/bug_20_buzzword_detection",
    ]

    os.makedirs(
        "results",
        exist_ok=True,
    )

    os.makedirs(
        "logs",
        exist_ok=True,
    )

    run_timestamp = time.strftime(
        "%Y%m%d_%H%M%S"
    )

    start_run(
        run_id=run_timestamp,
        model=MODEL,
        benchmark="internal-20-bug",
        metadata={
            "max_attempts": 3,
            "bug_count": len(bugs),
        },
    )

    results = []
    run_status = "completed"

    try:
        for bug_dir in bugs:
            result = solve_bug(
                bug_dir,
                max_attempts=3,
                run_id=run_timestamp,
            )

            results.append(
                result
            )

            # Save final per-bug result immediately
            # so partial runs are still preserved.
            save_result(
                result,
                run_timestamp,
            )

            bug_name = (
                result["bug"]
                .split("/")[-1]
            )

            with open(
                f"results/{bug_name}.json",
                "w",
            ) as file:
                json.dump(
                    result,
                    file,
                    indent=2,
                )

    except Exception:
        run_status = "failed"
        raise

    finally:
        finish_run(
            run_timestamp,
            status=run_status,
        )

    with open(
        f"logs/run_{run_timestamp}.json",
        "w",
    ) as file:
        json.dump(
            {
                "timestamp": (
                    run_timestamp
                ),
                "results": results,
            },
            file,
            indent=2,
        )

    print(
        f"\n{'=' * 50}"
    )

    print("SUMMARY")

    print(
        "=" * 50
    )

    total = len(results)

    successes = sum(
        1
        for result in results
        if result["success"]
    )

    total_cost = sum(
        result["cost_usd"]
        for result in results
    )

    total_time = sum(
        result["latency_sec"]
        for result in results
    )

    for result in results:
        status = (
            "PASSED"
            if result["success"]
            else "FAILED"
        )

        coverage_text = (
            f", cov={result['coverage']}%"
            if result.get(
                "coverage"
            ) is not None
            else ""
        )

        print(
            f"{result['bug']}: "
            f"{status} "
            f"({result['attempts']} "
            f"attempt(s), "
            f"${result['cost_usd']:.5f}, "
            f"{result['latency_sec']}s"
            f"{coverage_text})"
        )

    success_rate = (
        successes / total * 100
        if total
        else 0
    )

    print(
        f"\nOverall: "
        f"{successes}/{total} "
        f"bugs fixed "
        f"({success_rate:.0f}%)"
    )

    print(
        f"Total cost: "
        f"${total_cost:.5f} | "
        f"Total time: "
        f"{total_time:.1f}s"
    )

    print(
        f"Run ID: "
        f"{run_timestamp}"
    )


if __name__ == "__main__":
    main()