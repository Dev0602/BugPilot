import os

def read_file(filepath: str, base_dir: str) -> str:
    """Reads and returns the contents of a file as a string."""
    full_path = os.path.join(base_dir, filepath)
    with open(full_path, "r") as f:
        return f.read()


def write_file(filepath: str, new_contents: str, base_dir: str) -> None:
    """Overwrites a file with new contents."""
    full_path = os.path.join(base_dir, filepath)
    with open(full_path, "w") as f:
        f.write(new_contents)
        
def list_directory(base_dir):
    """Lists all files in a bug's directory (excluding cache/hidden files)."""
    files = []
    for f in os.listdir(base_dir):
        if not f.startswith('.') and not f.startswith('__') and os.path.isfile(os.path.join(base_dir, f)):
            files.append(f)
    return sorted(files)

def search_code(base_dir, keyword):
    """
    Searches all .py files in base_dir for lines containing keyword.
    Returns a list of {file, line_number, line_text} matches.
    """
    matches = []
    for filename in list_directory(base_dir):
        if not filename.endswith(".py"):
            continue
        filepath = os.path.join(base_dir, filename)
        with open(filepath, "r") as f:
            for i, line in enumerate(f, start=1):
                if keyword.lower() in line.lower():
                    matches.append({
                        "file": filename,
                        "line_number": i,
                        "line_text": line.strip(),
                    })
    return matches


def get_function_signature(base_dir, function_name):
    """
    Finds a function definition by name across all .py files in base_dir
    and returns just its signature line (the `def ...:` line), not the body.
    """
    for filename in list_directory(base_dir):
        if not filename.endswith(".py"):
            continue
        filepath = os.path.join(base_dir, filename)
        with open(filepath, "r") as f:
            for line in f:
                stripped = line.strip()
                if stripped.startswith(f"def {function_name}("):
                    return f"{filename}: {stripped}"
    return f"Function '{function_name}' not found."