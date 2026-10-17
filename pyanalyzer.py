
import ast
from pathlib import Path


def parse_python_file(file_path: str | Path) -> ast.Module:
    """Parse a Python source file and return its AST.

    Args:
        file_path: Path to the Python source file.

    Returns:
        The parsed AST module.

    Raises:
        SyntaxError: If the source code contains invalid Python syntax.
        OSError: If the file cannot be read.
        UnicodeError: If the file cannot be decoded.
    """
    path = Path(file_path)
    source = path.read_text(encoding="utf-8")
    return ast.parse(source, filename=str(path))

"""misson 2——————————————————"""


def extract_definitions(file_path: str | Path) -> dict:
    """Extract top-level functions and classes from a Python file."""
    tree = parse_python_file(file_path)

    functions = []
    classes = []

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append({
                "name": node.name,
                "kind": "async_function" if isinstance(node, ast.AsyncFunctionDef) else "function",
                "lineno": node.lineno,
                "end_lineno": node.end_lineno,
            })

        elif isinstance(node, ast.ClassDef):
            methods = []
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    methods.append({
                        "name": item.name,
                        "kind": "async_function" if isinstance(item, ast.AsyncFunctionDef) else "method",
                        "lineno": item.lineno,
                        "end_lineno": item.end_lineno,
                    })

            classes.append({
                "name": node.name,
                "lineno": node.lineno,
                "end_lineno": node.end_lineno,
                "methods": methods,
            })

    return {
        "file": str(file_path),
        "functions": functions,
        "classes": classes,
    }
