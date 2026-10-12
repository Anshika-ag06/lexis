import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mcl_symtable import SymbolTable


def test_declare_and_lookup():
    st = SymbolTable()
    result = st.declare("x", "int", line=1)
    assert result is None  # fresh declaration succeeds
    sym = st.lookup("x")
    assert sym is not None
    assert sym.type == "int"
    assert sym.line == 1


def test_redeclaration_in_same_scope_is_reported():
    st = SymbolTable()
    st.declare("x", "int", line=1)
    existing = st.declare("x", "bool", line=2)
    assert existing is not None
    assert existing.line == 1


def test_lookup_undeclared_returns_none():
    st = SymbolTable()
    assert st.lookup("nope") is None


def test_nested_scope_shadowing_and_visibility():
    st = SymbolTable()
    st.declare("x", "int", line=1)
    st.enter_scope()
    # same name in an inner scope is allowed (shadowing), not a redeclaration
    result = st.declare("x", "bool", line=2)
    assert result is None
    inner = st.lookup("x")
    assert inner.type == "bool"
    st.exit_scope()
    # after leaving the inner scope, the outer 'x' is visible again
    outer = st.lookup("x")
    assert outer.type == "int"


def test_inner_scope_sees_outer_declarations():
    st = SymbolTable()
    st.declare("y", "int", line=1)
    st.enter_scope()
    assert st.lookup("y") is not None
    st.exit_scope()
