#!/usr/bin/env python3
"""Syntax/import check for GUI modules (non-interactive, no display needed)."""
import sys, importlib.util, os

GUI_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "gui"))
sys.path.insert(0, GUI_DIR)

errors = 0
for mod in ("models", "controller", "widgets"):
    path = os.path.join(GUI_DIR, f"{mod}.py")
    try:
        module = __import__(mod)
        print(f"  [OK] {mod}.py")
    except Exception as e:
        print(f"  [FAIL] {mod}.py  ->  {e}")
        errors += 1

# app.py requires a display – just check syntax
import ast
with open(os.path.join(GUI_DIR, "app.py")) as f:
    src = f.read()
try:
    ast.parse(src)
    print("  [OK] app.py (syntax)")
except SyntaxError as e:
    print(f"  [FAIL] app.py  ->  {e}")
    errors += 1

sys.exit(errors)
