"""Comprobación estática: ningún módulo usa un nombre que no existe (el error que Python solo avisa al ejecutar esa línea).
Es lo que protege al partir o mover código: si olvidas un import, esta prueba falla en 1 segundo."""
import ast, builtins, glob, os, unittest
from _common import ROOT


def bound_names(tree):
    names = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)): names.add(n.name)
        elif isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)): names.add(n.id)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for a in n.names: names.add((a.asname or a.name).split('.')[0])
        elif isinstance(n, ast.ExceptHandler) and n.name: names.add(n.name)
        elif isinstance(n, ast.arg): names.add(n.arg)
        elif isinstance(n, (ast.Global, ast.Nonlocal)): names.update(n.names)
    return names


def undefined_names(path):
    src = open(path, encoding='utf-8').read(); tree = ast.parse(src, path)
    module_level = set()
    for n in tree.body:                                   # nombres definidos a nivel de módulo (incluye los de if/try/for/with de primer nivel)
        for m in ast.walk(n):
            if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and m in tree.body: module_level.add(m.name)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)): module_level.add(n.name); continue
        for m in ast.walk(n):
            if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)): continue
        module_level |= {x for x in bound_names(ast.Module(body=[n], type_ignores=[])) if True} if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) else set()
    # globals declarados dentro de funciones también existen a nivel de módulo
    for n in ast.walk(tree):
        if isinstance(n, ast.Global): module_level.update(n.names)
    known = module_level | set(dir(builtins)) | {'__file__', '__name__', '__doc__'}
    bad = []

    def visit(node, scope_names):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                inner = scope_names | bound_names(child)
                visit(child, inner)
            elif isinstance(child, ast.ClassDef):
                visit(child, scope_names | bound_names(child))
            else:
                if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load) and child.id not in scope_names: bad.append((child.id, child.lineno))
                visit(child, scope_names)
    visit(tree, known)
    return sorted(set(bad), key=lambda x: x[1])


class StaticTest(unittest.TestCase):
    def test_no_undefined_names(self):
        files = [f for f in glob.glob(os.path.join(ROOT, '*.py')) + glob.glob(os.path.join(ROOT, 'djcore', '*.py'))]
        self.assertTrue(files)
        for f in files:
            bad = undefined_names(f)
            self.assertEqual(bad, [], f'{os.path.relpath(f, ROOT)}: nombres sin definir {bad[:8]}')

    def test_checker_detects_a_missing_name(self):
        import tempfile
        p = os.path.join(tempfile.mkdtemp(), 'x.py'); open(p, 'w').write('import os\ndef f():\n    return os.getcwd() + otra_cosa\n')
        self.assertEqual([n for n, _ in undefined_names(p)], ['otra_cosa'])
