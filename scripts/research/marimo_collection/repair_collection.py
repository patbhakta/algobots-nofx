"""Audit real marimo graphs and recover sequential notebooks without executing them.

Requires marimo==0.25.1. Originals are never overwritten: writes a new collection.
Helper modules and backup directories are excluded from notebook counts.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import textwrap

from marimo._ast.load import load_app


def original_notebook(path, roots):
    matches = [p for root in roots for p in root.rglob(path.stem.removeprefix('stage-') + '.ipynb')]
    if len(matches) != 1:
        return None
    cells = json.loads(matches[0].read_text())['cells']
    code, markdown = [], []
    for cell in cells:
        source = ''.join(cell.get('source', []))
        if cell['cell_type'] == 'markdown':
            markdown.append(source)
        elif cell['cell_type'] == 'code':
            # Installation and shell setup remain visible instructions, never
            # implicit environment mutations when running recovered analysis.
            lines = []
            for line in source.splitlines():
                if line.lstrip().startswith(('%', '!')):
                    lines.append(' ' * (len(line) - len(line.lstrip())) + '# SETUP (run separately): ' + line.lstrip())
                else:
                    lines.append(line)
            code.append('\n'.join(lines))
    result = '\n\n'.join(code)
    # Bounded source corrections, each tied to a known malformed source cell.
    if path.stem == 'stage-HyPE_Hypothetical_Prompt_Embeddings':
        result = result.replace('index=faiss.IndexFlatL2(len(vectors[0]))  #', 'index=faiss.IndexFlatL2(len(vectors[0])),  #')
    if path.stem == 'stage-letta_memgpt_patterns':
        import re
        result = re.sub(r'print\(f".*?len\(TOOLS_(?:EDIT|SEARCH)\).*?defined"\),\n\]', '# Removed premature print and stray closing bracket from source.', result)
    if path.stem == 'stage-memory_compaction':
        result = result.replace('    ),\n\n\n# Memory 3:', '    ),\n)\n\n# Memory 3:')
    if path.stem == 'stage-multi_agent_shared_memory':
        start = result.index('    def read(')
        end = result.index('\nclass Agent:', start)
        methods = textwrap.dedent(result[start:end])
        names = [n.name for n in ast.parse(methods).body if isinstance(n, ast.FunctionDef)]
        result = result[:start] + methods + '\n' + '\n'.join(f'SharedMemoryPool.{name} = {name}' for name in names) + result[end:]
    return result, markdown


def extract(source):
    """Recover code and markdown in source order, including failed conversion cells."""
    codes, markdown = [], []
    for node in ast.parse(source).body:
        if isinstance(node, ast.FunctionDef) and any('app.cell' in ast.unparse(d) for d in node.decorator_list):
            body = node.body[:-1] if isinstance(node.body[-1], ast.Return) else node.body
            if len(body) == 1 and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Call) and ast.unparse(body[0].value.func) == 'mo.md':
                try: markdown.append(ast.literal_eval(body[0].value.args[0]))
                except (ValueError, TypeError): pass
            else:
                codes.append('\n'.join(ast.unparse(n) for n in body))
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) and ast.unparse(node.value.func) == 'app._unparsable_cell':
            codes.append(textwrap.dedent(ast.literal_eval(node.value.args[0])))
    return '\n\n'.join(codes), markdown


def wrapper(code, markdown, error):
    # A sequential fallback retains the original computation; it is not counted
    # as a native reactive conversion. Execution is always explicit.
    result = '''import marimo
app = marimo.App(width="medium")

@app.cell
def _():
    import marimo as mo
    return (mo,)

@app.cell
def _(mo):
    mo.md("## Recovered sequential notebook\\nThe original conversion failed graph validation. Edit the recovered code and press Run. Dependencies and provider credentials must be available in this runtime.")
    return
'''
    for md in markdown:
        result += f'\n@app.cell(hide_code=True)\ndef _(mo):\n    mo.md({md!r})\n    return\n'
    result += f'''
@app.cell
def _(mo):
    recovered_code = mo.ui.code_editor(value={code!r}, language="python", label="Recovered notebook code")
    run_recovered = mo.ui.run_button(label="Run recovered notebook")
    mo.vstack([recovered_code, run_recovered])
    return recovered_code, run_recovered

@app.cell
def _(mo, recovered_code, run_recovered):
    mo.stop(not run_recovered.value)
    import os
    import subprocess
    import sys
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory(prefix="marimo-recovered-") as _tmp:
        _script = Path(_tmp) / "notebook.py"
        _tail = "\\nimport matplotlib.pyplot as _plt\\nfrom pathlib import Path as _Path\\nfor _n in _plt.get_fignums():\\n    _plt.figure(_n).savefig(_Path(" + repr(_tmp) + ") / (str(_n) + '.png'))\\n"
        _runner = "import ast, asyncio, inspect\\n_result = eval(compile(" + repr(recovered_code.value) + ", '<notebook>', 'exec', flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT))\\nif inspect.isawaitable(_result): asyncio.run(_result)\\n"
        _script.write_text(_runner + _tail)
        try:
            _run = subprocess.run([sys.executable, str(_script)], capture_output=True, text=True, timeout=90, env={{**os.environ, "MPLBACKEND": "Agg"}})
            _outputs = [mo.md(f"Exit status: **{{_run.returncode}}**"), mo.plain_text(_run.stdout + _run.stderr)]
            _outputs += [mo.image(_p.read_bytes()) for _p in sorted(Path(_tmp).glob("*.png"))]
            mo.output.replace(mo.vstack(_outputs))
        except subprocess.TimeoutExpired:
            mo.output.replace(mo.md("Execution exceeded 90 seconds; reduce the workload before retrying."))
    return

if __name__ == "__main__":
    app.run()
'''
    return result


def add_ui(source):
    if 'mo.ui.' in source:
        return source
    # Isolated private import avoids colliding with the notebook's marimo alias.
    controls = '''\n\n@app.cell(hide_code=True)
def _():
    import marimo as _studio_mo
    studio_notes = _studio_mo.ui.text_area(label="Research notes", placeholder="Record parameters, observations and follow-up questions")
    _studio_mo.vstack([_studio_mo.md("### Research notebook"), studio_notes])
    return (studio_notes,)
'''
    index = source.find('\nif __name__')
    return source[:index] + controls + source[index:] if index >= 0 else source + controls


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--original-root', type=Path, action='append', default=[])
    args = parser.parse_args()
    records = []
    for path in sorted(args.source.rglob('*.py')):
        relative = path.relative_to(args.source)
        if any(p.startswith('.') or '.bak-' in p for p in relative.parts):
            continue
        source = path.read_text()
        if 'marimo.App(' not in source:
            records.append(dict(path=str(relative), status='helper_module', sha256=hashlib.sha256(source.encode()).hexdigest()))
            continue
        output = args.destination / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        error = None
        try:
            app = load_app(path)
            app._maybe_initialize()
            result, status = add_ui(source), 'true_app'
        except Exception as exc:
            error = str(exc)
            recovered = original_notebook(path, args.original_root)
            code, markdown = recovered if recovered else extract(source)
            try:
                compile(code, str(relative), 'exec', flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
                status = 'wrapped'
            except SyntaxError as invalid:
                status = 'unfixable'
                error += '\nRecovered code: ' + str(invalid)
            result = wrapper(code, markdown, error)
        output.write_text('\n'.join(line.rstrip() for line in result.splitlines()).rstrip() + '\n')
        # Validation loads/compiles the dependency graph, never the workload.
        app = load_app(output)
        app._maybe_initialize()
        records.append(dict(path=str(relative), status=status, error=error, sha256=hashlib.sha256(source.encode()).hexdigest()))
    from collections import Counter
    report = dict(counts=dict(Counter(r['status'] for r in records)), stage_counts=dict(Counter(r['status'] for r in records if r['path'].startswith('stage-'))), notebooks=records)
    args.destination.mkdir(parents=True, exist_ok=True)
    (args.destination / 'audit.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({k:v for k,v in report.items() if k != 'notebooks'}, indent=2))

if __name__ == '__main__':
    main()
