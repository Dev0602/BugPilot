import pytest

from backend.app.tools import (
    get_function_signature,
    list_directory,
    read_file,
    read_file_range,
    search_code,
    write_file,
)


def test_read_and_write_file(tmp_path):
    file_path = tmp_path / "example.py"

    file_path.write_text(
        "value = 1\n",
        encoding="utf-8",
    )

    write_file(
        "example.py",
        "value = 42\n",
        str(tmp_path),
    )

    content = read_file(
        "example.py",
        str(tmp_path),
    )

    assert content == "value = 42\n"

def test_read_file_range(tmp_path):
    path = tmp_path / "sample.py"

    path.write_text(
        "line1\n"
        "line2\n"
        "line3\n"
        "line4\n",
        encoding="utf-8",
    )

    result = read_file_range(
        "sample.py",
        str(tmp_path),
        start_line=2,
        end_line=3,
    )

    assert "2: line2" in result
    assert "3: line3" in result
    assert "1: line1" not in result
    assert "4: line4" not in result


def test_path_traversal_is_rejected_on_read(tmp_path):
    with pytest.raises(ValueError):
        read_file(
            "../outside.py",
            str(tmp_path),
        )


def test_path_traversal_is_rejected_on_write(tmp_path):
    with pytest.raises(ValueError):
        write_file(
            "../outside.py",
            "bad = True\n",
            str(tmp_path),
        )


def test_list_directory_non_recursive(tmp_path):
    (tmp_path / "root.py").write_text(
        "x = 1\n",
        encoding="utf-8",
    )

    nested = tmp_path / "package"
    nested.mkdir()

    (nested / "nested.py").write_text(
        "y = 2\n",
        encoding="utf-8",
    )

    files = list_directory(
        str(tmp_path),
        path=".",
        recursive=False,
    )

    assert "root.py" in files

    assert not any(
        item.endswith("package/nested.py")
        for item in files
    )


def test_list_directory_recursive(tmp_path):
    nested = tmp_path / "package"
    nested.mkdir()

    deeper = nested / "inner"
    deeper.mkdir()

    (tmp_path / "root.py").write_text(
        "root = True\n",
        encoding="utf-8",
    )

    (nested / "nested.py").write_text(
        "nested = True\n",
        encoding="utf-8",
    )

    (deeper / "deep.py").write_text(
        "deep = True\n",
        encoding="utf-8",
    )

    files = list_directory(
        str(tmp_path),
        recursive=True,
        max_depth=3,
    )

    assert "root.py" in files
    assert "package/nested.py" in files
    assert "package/inner/deep.py" in files


def test_list_directory_ignores_pycache(tmp_path):
    cache = tmp_path / "__pycache__"
    cache.mkdir()

    (cache / "hidden.py").write_text(
        "hidden = True\n",
        encoding="utf-8",
    )

    (tmp_path / "visible.py").write_text(
        "visible = True\n",
        encoding="utf-8",
    )

    files = list_directory(
        str(tmp_path),
        recursive=True,
        max_depth=3,
    )

    assert "visible.py" in files

    assert not any(
        "__pycache__" in item
        for item in files
    )


def test_list_directory_ignores_coverage_file(tmp_path):
    (tmp_path / ".coverage").write_text(
        "coverage-data",
        encoding="utf-8",
    )

    (tmp_path / "app.py").write_text(
        "value = 1\n",
        encoding="utf-8",
    )

    files = list_directory(
        str(tmp_path),
        recursive=True,
        max_depth=2,
    )

    assert "app.py" in files
    assert ".coverage" not in files


def test_search_code_finds_nested_match(tmp_path):
    package = tmp_path / "package"
    package.mkdir()

    source = package / "service.py"

    source.write_text(
        "def calculate_total(items):\n"
        "    return sum(items)\n",
        encoding="utf-8",
    )

    matches = search_code(
        str(tmp_path),
        "calculate_total",
    )

    assert len(matches) >= 1

    assert any(
        match["file"] == "package/service.py"
        and match["line_number"] == 1
        for match in matches
    )


def test_search_code_returns_empty_for_missing_keyword(
    tmp_path,
):
    (tmp_path / "app.py").write_text(
        "value = 42\n",
        encoding="utf-8",
    )

    matches = search_code(
        str(tmp_path),
        "does_not_exist_anywhere",
    )

    assert matches == []


def test_get_function_signature_top_level(tmp_path):
    source = tmp_path / "app.py"

    source.write_text(
        "def calculate_total(items):\n"
        "    return sum(items)\n",
        encoding="utf-8",
    )

    result = get_function_signature(
        str(tmp_path),
        "calculate_total",
    )

    assert "app.py:1" in result
    assert "calculate_total" in result
    assert "def calculate_total(items):" in result


def test_get_function_signature_class_method(tmp_path):
    source = tmp_path / "calculator.py"

    source.write_text(
        "class Calculator:\n"
        "    def add(self, a, b):\n"
        "        return a + b\n",
        encoding="utf-8",
    )

    result = get_function_signature(
        str(tmp_path),
        "add",
    )

    assert "calculator.py" in result
    assert "Calculator.add" in result
    assert "def add(self, a, b):" in result


def test_get_function_signature_async_function(tmp_path):
    source = tmp_path / "service.py"

    source.write_text(
        "async def fetch_data(url):\n"
        "    return url\n",
        encoding="utf-8",
    )

    result = get_function_signature(
        str(tmp_path),
        "fetch_data",
    )

    assert "fetch_data" in result
    assert "async def fetch_data(url):" in result