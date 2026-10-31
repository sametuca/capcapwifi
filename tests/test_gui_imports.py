#!/usr/bin/env python3
"""Syntax/import check for GUI modules (non-interactive, no display needed).

Ayrıca app.py'nin models/widgets/controller'dan istediği isimleri gerçekten
var mı diye doğrular – ekran açmadan yakalanabilecek en pahalı hata bu.
"""
import ast
import importlib
import os
import sys

GUI_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "gui"))
sys.path.insert(0, GUI_DIR)

errors = 0
modules = {}
for mod in ("models", "controller", "widgets"):
    try:
        modules[mod] = importlib.import_module(mod)
        print(f"  [OK] {mod}.py")
    except Exception as e:
        print(f"  [FAIL] {mod}.py  ->  {e}")
        errors += 1

# app.py requires a display – parse it and check its local imports.
app_path = os.path.join(GUI_DIR, "app.py")
with open(app_path) as f:
    src = f.read()

try:
    tree = ast.parse(src)
    print("  [OK] app.py (syntax)")
except SyntaxError as e:
    print(f"  [FAIL] app.py  ->  {e}")
    tree = None
    errors += 1

if tree is not None:
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.module not in modules:
            continue
        target = modules[node.module]
        for alias in node.names:
            if not hasattr(target, alias.name):
                print(f"  [FAIL] app.py: {node.module} içinde '{alias.name}' yok")
                errors += 1

sys.exit(1 if errors else 0)
