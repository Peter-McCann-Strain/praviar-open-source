#!/usr/bin/env python3
"""Fail-closed expand/contract gate for production database migrations.

The checker compares the Alembic graph embedded in the currently deployed
(``N-1``) API image with the candidate graph.  Every migration introduced
between those two immutable releases must be additive: destructive contract
operations, column renames/type changes, and new required columns without a
database default are rejected before the production migration job runs.

This is deliberately conservative.  A contract migration belongs in a later
release after the old application revision has been retired; it must not be
combined with the expand release that still needs to support N-1.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


class MigrationSafetyError(RuntimeError):
    """Raised when candidate migrations cannot prove N-1 compatibility."""


@dataclass(frozen=True)
class Revision:
    parents: tuple[str, ...]
    path: Path
    revision: str
    tree: ast.Module


_DESTRUCTIVE_SQL = (
    re.compile(r"\bDROP\b", re.IGNORECASE),
    re.compile(r"\bRENAME\b", re.IGNORECASE),
    re.compile(r"\bTRUNCATE\b", re.IGNORECASE),
    re.compile(r"\bDELETE\s+FROM\b", re.IGNORECASE),
    re.compile(r"\bREVOKE\b", re.IGNORECASE),
    re.compile(r"\bALTER\s+COLUMN\b[\s\S]*\bTYPE\b", re.IGNORECASE),
    re.compile(r"\bALTER\s+COLUMN\b[\s\S]*\bSET\s+NOT\s+NULL\b", re.IGNORECASE),
)


def _literal_assignment(tree: ast.Module, name: str, *, path: Path) -> object:
    assignments = [
        node.value
        for node in tree.body
        if isinstance(node, (ast.Assign, ast.AnnAssign))
        for target in (node.targets if isinstance(node, ast.Assign) else [node.target])
        if isinstance(target, ast.Name) and target.id == name
    ]
    if len(assignments) != 1:
        raise MigrationSafetyError(f"{path}: must declare exactly one literal {name}")
    try:
        return ast.literal_eval(assignments[0])
    except (TypeError, ValueError) as exc:
        raise MigrationSafetyError(f"{path}: {name} must be a literal") from exc


def _load_revisions(root: Path) -> dict[str, Revision]:
    if not root.is_dir():
        raise MigrationSafetyError(f"migration directory does not exist: {root}")
    revisions: dict[str, Revision] = {}
    for path in sorted(root.glob("*.py")):
        if path.name == "__init__.py":
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError) as exc:
            raise MigrationSafetyError(f"{path}: cannot parse migration") from exc
        revision_value = _literal_assignment(tree, "revision", path=path)
        if not isinstance(revision_value, str) or not revision_value:
            raise MigrationSafetyError(f"{path}: revision must be a non-empty string")
        down_value = _literal_assignment(tree, "down_revision", path=path)
        if down_value is None:
            parents: tuple[str, ...] = ()
        elif isinstance(down_value, str) and down_value:
            parents = (down_value,)
        elif (
            isinstance(down_value, (tuple, list))
            and down_value
            and all(isinstance(value, str) and value for value in down_value)
        ):
            parents = tuple(down_value)
        else:
            raise MigrationSafetyError(
                f"{path}: down_revision must be null, a revision, or revisions"
            )
        if revision_value in revisions:
            raise MigrationSafetyError(f"duplicate revision {revision_value!r}")
        revisions[revision_value] = Revision(
            parents=parents,
            path=path,
            revision=revision_value,
            tree=tree,
        )

    if not revisions:
        raise MigrationSafetyError(f"no Alembic revisions found in {root}")
    missing = sorted(
        {
            parent
            for revision in revisions.values()
            for parent in revision.parents
            if parent not in revisions
        }
    )
    if missing:
        raise MigrationSafetyError(
            f"{root}: graph references missing revisions: {', '.join(missing)}"
        )
    return revisions


def _heads(revisions: dict[str, Revision]) -> set[str]:
    referenced = {
        parent for revision in revisions.values() for parent in revision.parents
    }
    return set(revisions).difference(referenced)


def _ancestors(revisions: dict[str, Revision], head: str) -> set[str]:
    seen: set[str] = set()
    pending = [head]
    while pending:
        revision_id = pending.pop()
        if revision_id in seen:
            continue
        revision = revisions.get(revision_id)
        if revision is None:
            raise MigrationSafetyError(
                f"candidate graph does not contain required revision {revision_id}"
            )
        seen.add(revision_id)
        pending.extend(revision.parents)
    return seen


def _call_name(node: ast.Call, batch_aliases: set[str]) -> str | None:
    if not isinstance(node.func, ast.Attribute):
        return None
    owner = node.func.value
    if isinstance(owner, ast.Name) and (owner.id == "op" or owner.id in batch_aliases):
        return node.func.attr
    return None


def _keyword(call: ast.Call, name: str) -> ast.expr | None:
    return next((row.value for row in call.keywords if row.arg == name), None)


def _literal_string(node: ast.expr | None) -> str | None:
    if node is None:
        return None
    try:
        value = ast.literal_eval(node)
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, str) else None


def _column_contract(call: ast.Call) -> tuple[bool | None, bool]:
    # Top-level ``op.add_column`` receives (table, column); a batch operation
    # receives only (column).
    column = call.args[1] if len(call.args) > 1 else call.args[0] if call.args else None
    if not isinstance(column, ast.Call):
        return None, False
    nullable_node = _keyword(column, "nullable")
    nullable: bool | None = None
    if isinstance(nullable_node, ast.Constant) and isinstance(
        nullable_node.value, bool
    ):
        nullable = nullable_node.value
    has_default = _keyword(column, "server_default") is not None
    return nullable, has_default


def _extract_execute_sql(call: ast.Call) -> str | None:
    if not call.args:
        return None
    value = call.args[0]
    if isinstance(value, ast.Call) and value.args:
        value = value.args[0]
    return _literal_string(value)


def _batch_aliases(upgrade: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    aliases: set[str] = set()
    for node in ast.walk(upgrade):
        if not isinstance(node, ast.With):
            continue
        for item in node.items:
            context = item.context_expr
            if (
                isinstance(context, ast.Call)
                and isinstance(context.func, ast.Attribute)
                and isinstance(context.func.value, ast.Name)
                and context.func.value.id == "op"
                and context.func.attr == "batch_alter_table"
                and isinstance(item.optional_vars, ast.Name)
            ):
                aliases.add(item.optional_vars.id)
    return aliases


def _created_tables(
    upgrade: ast.FunctionDef | ast.AsyncFunctionDef, aliases: set[str]
) -> set[str]:
    result: set[str] = set()
    for node in ast.walk(upgrade):
        if (
            not isinstance(node, ast.Call)
            or _call_name(node, aliases) != "create_table"
        ):
            continue
        table = _literal_string(node.args[0] if node.args else None)
        if table:
            result.add(table)
    return result


def _upgrade_function(revision: Revision) -> ast.FunctionDef | ast.AsyncFunctionDef:
    functions = [
        node
        for node in revision.tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "upgrade"
    ]
    if len(functions) != 1:
        raise MigrationSafetyError(
            f"{revision.path}: must declare exactly one upgrade function"
        )
    return functions[0]


def _constraint_table_argument(call: ast.Call) -> str | None:
    return _literal_string(call.args[1] if len(call.args) > 1 else None)


MigrationFunction = ast.FunctionDef | ast.AsyncFunctionDef

_SAFE_BUILTIN_CALLS = {
    "bool",
    "dict",
    "float",
    "int",
    "len",
    "list",
    "range",
    "set",
    "sorted",
    "str",
    "tuple",
}
_SAFE_SQLALCHEMY_CONSTRUCTORS = {
    "ARRAY",
    "BigInteger",
    "Boolean",
    "CheckConstraint",
    "Column",
    "Date",
    "DateTime",
    "Enum",
    "Float",
    "ForeignKey",
    "ForeignKeyConstraint",
    "Index",
    "Integer",
    "JSON",
    "LargeBinary",
    "MetaData",
    "Numeric",
    "PrimaryKeyConstraint",
    "SmallInteger",
    "String",
    "Table",
    "Text",
    "Time",
    "UniqueConstraint",
    "UUID",
    "column",
    "literal",
    "table",
    "text",
}


def _location(revision: Revision, node: ast.AST) -> str:
    return f"{revision.path.name}:{getattr(node, 'lineno', 0)}"


def _inert_expression(node: ast.expr | None) -> bool:
    if node is None:
        return True
    if isinstance(node, (ast.Constant, ast.Name)):
        return True
    if isinstance(node, ast.Attribute):
        return _inert_expression(node.value)
    if isinstance(node, ast.Subscript):
        return _inert_expression(node.value) and _inert_expression(node.slice)
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return all(_inert_expression(value) for value in node.elts)
    if isinstance(node, ast.Dict):
        return all(_inert_expression(value) for value in node.keys) and all(
            _inert_expression(value) for value in node.values
        )
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return _inert_expression(node.left) and _inert_expression(node.right)
    if isinstance(node, ast.UnaryOp) and isinstance(
        node.op,
        (ast.UAdd, ast.USub),
    ):
        return _inert_expression(node.operand)
    return False


def _literal_value(node: ast.expr | None) -> bool:
    if node is None:
        return True
    try:
        ast.literal_eval(node)
    except (TypeError, ValueError):
        return False
    return True


def _approved_import(node: ast.Import | ast.ImportFrom) -> bool:
    if isinstance(node, ast.Import):
        return (
            len(node.names) == 1
            and node.names[0].name == "sqlalchemy"
            and node.names[0].asname == "sa"
        )
    allowed = {
        "__future__": {("annotations", None)},
        "alembic": {("op", None)},
        "collections.abc": {("Sequence", None)},
        "typing": {("Sequence", None)},
    }
    observed = {(alias.name, alias.asname) for alias in node.names}
    return bool(observed) and observed.issubset(allowed.get(node.module or "", set()))


def _function_definition_violation(
    revision: Revision,
    function: MigrationFunction,
) -> list[str]:
    location = _location(revision, function)
    violations: list[str] = []
    if function.decorator_list:
        violations.append(
            f"{location}: migration functions must not have import-time decorators"
        )
    defaults = [*function.args.defaults, *function.args.kw_defaults]
    if any(not _literal_value(default) for default in defaults):
        violations.append(
            f"{location}: migration function defaults must be literal and inert"
        )
    annotations = [
        function.returns,
        *(argument.annotation for argument in function.args.posonlyargs),
        *(argument.annotation for argument in function.args.args),
        *(argument.annotation for argument in function.args.kwonlyargs),
    ]
    if function.args.vararg is not None:
        annotations.append(function.args.vararg.annotation)
    if function.args.kwarg is not None:
        annotations.append(function.args.kwarg.annotation)
    if any(not _inert_expression(annotation) for annotation in annotations):
        violations.append(
            f"{location}: migration function annotations must be call-free"
        )
    return violations


def _module_policy_violations(revision: Revision) -> list[str]:
    violations: list[str] = []
    for index, node in enumerate(revision.tree.body):
        location = _location(revision, node)
        if (
            isinstance(node, ast.Expr)
            and index == 0
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            continue
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if not _approved_import(node):
                violations.append(
                    f"{location}: unproved import is forbidden in production migrations"
                )
            continue
        if isinstance(node, ast.Assign):
            if (
                not node.targets
                or any(not isinstance(target, ast.Name) for target in node.targets)
                or not _literal_value(node.value)
            ):
                violations.append(
                    f"{location}: module assignments must be simple literal constants"
                )
            continue
        if isinstance(node, ast.AnnAssign):
            if (
                not isinstance(node.target, ast.Name)
                or not _inert_expression(node.annotation)
                or not _literal_value(node.value)
            ):
                violations.append(
                    f"{location}: annotated module assignments must be literal and call-free"
                )
            continue
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            violations.extend(_function_definition_violation(revision, node))
            continue
        if isinstance(node, ast.Pass):
            continue
        violations.append(
            f"{location}: executable module-level {type(node).__name__} is forbidden"
        )
    return violations


def _module_functions(revision: Revision) -> dict[str, MigrationFunction]:
    functions: dict[str, MigrationFunction] = {}
    for node in revision.tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name in functions:
            raise MigrationSafetyError(
                f"{revision.path}: duplicate migration helper {node.name!r}"
            )
        functions[node.name] = node
    return functions


def _reachable_functions(revision: Revision) -> list[MigrationFunction]:
    functions = _module_functions(revision)
    upgrade = _upgrade_function(revision)
    pending = [upgrade]
    visited: set[str] = set()
    reachable: list[MigrationFunction] = []
    while pending:
        function = pending.pop()
        if function.name in visited:
            continue
        visited.add(function.name)
        reachable.append(function)
        for node in ast.walk(function):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in functions
            ):
                pending.append(functions[node.func.id])
    return reachable


def _unproved_call_violation(
    *,
    aliases: set[str],
    call: ast.Call,
    local_functions: set[str],
    revision: Revision,
) -> str | None:
    if _call_name(call, aliases) is not None:
        return None
    if isinstance(call.func, ast.Attribute) and call.func.attr in {
        "execute",
        "exec_driver_sql",
    }:
        return None
    if isinstance(call.func, ast.Name):
        if call.func.id in local_functions or call.func.id in _SAFE_BUILTIN_CALLS:
            return None
        detail = f"unproved imported or aliased callable {call.func.id!r}"
    elif (
        isinstance(call.func, ast.Attribute)
        and isinstance(call.func.value, ast.Name)
        and call.func.value.id == "sa"
        and call.func.attr in _SAFE_SQLALCHEMY_CONSTRUCTORS
    ):
        return None
    elif isinstance(call.func, ast.Attribute):
        detail = f"unproved method or imported-module call {ast.unparse(call.func)!r}"
    else:
        detail = f"dynamic callable expression {ast.unparse(call.func)!r}"
    line = getattr(call, "lineno", 0)
    return f"{revision.path.name}:{line}: {detail} is forbidden"


def _migration_violations(revision: Revision) -> list[str]:
    functions = _reachable_functions(revision)
    local_functions = set(_module_functions(revision))
    aliases_by_function = {
        function.name: _batch_aliases(function) for function in functions
    }
    created_tables = {
        table
        for function in functions
        for table in _created_tables(
            function,
            aliases_by_function[function.name],
        )
    }
    violations = _module_policy_violations(revision)
    always_destructive = {
        "drop_column",
        "drop_constraint",
        "drop_index",
        "drop_table",
        "drop_table_comment",
        "rename_table",
    }
    constraint_calls = {
        "create_check_constraint",
        "create_exclude_constraint",
        "create_foreign_key",
        "create_primary_key",
        "create_unique_constraint",
    }
    safe_operations = {
        "create_table_comment",
        "f",
        "inline_literal",
    }

    for function in functions:
        aliases = aliases_by_function[function.name]
        for node in ast.walk(function):
            if not isinstance(node, ast.Call):
                continue
            unproved = _unproved_call_violation(
                aliases=aliases,
                call=node,
                local_functions=local_functions,
                revision=revision,
            )
            if unproved:
                violations.append(unproved)
                continue
            name = _call_name(node, aliases)
            if (
                name is None
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"execute", "exec_driver_sql"}
            ):
                name = "execute"
            if name is None or name in {"batch_alter_table", "create_table"}:
                continue
            line = getattr(node, "lineno", 0)
            location = f"{revision.path.name}:{line}"
            if name in always_destructive:
                violations.append(f"{location}: op.{name} is a contract operation")
                continue
            if name == "alter_column":
                risky_keywords = {
                    row.arg
                    for row in node.keywords
                    if row.arg in {"new_column_name", "type_"}
                    or (
                        row.arg == "nullable"
                        and isinstance(row.value, ast.Constant)
                        and row.value.value is False
                    )
                    or (
                        row.arg == "server_default"
                        and isinstance(row.value, ast.Constant)
                        and row.value.value is None
                    )
                }
                if risky_keywords:
                    violations.append(
                        f"{location}: op.alter_column changes "
                        + ", ".join(sorted(risky_keywords))
                    )
                continue
            if name == "add_column":
                nullable, has_default = _column_contract(node)
                if nullable is False and not has_default:
                    violations.append(
                        f"{location}: required column lacks a server_default for N-1 writes"
                    )
                elif nullable is None:
                    violations.append(
                        f"{location}: add_column nullability cannot be proved statically"
                    )
                continue
            if name == "create_index":
                unique = _keyword(node, "unique")
                table = _literal_string(node.args[1] if len(node.args) > 1 else None)
                if unique is not None and not (
                    isinstance(unique, ast.Constant) and isinstance(unique.value, bool)
                ):
                    violations.append(
                        f"{location}: index uniqueness cannot be proved statically"
                    )
                elif (
                    isinstance(unique, ast.Constant)
                    and unique.value is True
                    and (not table or table not in created_tables)
                ):
                    violations.append(
                        f"{location}: unique index constrains an existing or unknown table"
                    )
                continue
            if name in constraint_calls:
                table = _constraint_table_argument(node)
                if not table or table not in created_tables:
                    violations.append(
                        f"{location}: op.{name} constrains an existing or unknown table"
                    )
                continue
            if name == "execute":
                sql = _extract_execute_sql(node)
                if sql is None:
                    violations.append(
                        f"{location}: dynamic op.execute SQL cannot prove expand-only behavior"
                    )
                else:
                    matched = next(
                        (
                            pattern.pattern
                            for pattern in _DESTRUCTIVE_SQL
                            if pattern.search(sql)
                        ),
                        None,
                    )
                    violations.append(
                        f"{location}: raw SQL is forbidden by the expand-only policy"
                        + (
                            f" (matched destructive pattern {matched!r})"
                            if matched
                            else ""
                        )
                    )
                continue
            if name not in safe_operations:
                violations.append(
                    f"{location}: op.{name} is not approved by the expand-only policy"
                )

    return violations


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_evidence(
    *,
    candidate_root: Path,
    previous_api_image: str,
    previous_root: Path,
    subject_git_sha: str,
) -> dict[str, object]:
    if re.fullmatch(r"[0-9a-f]{40}", subject_git_sha) is None:
        raise MigrationSafetyError(
            "subject git SHA must be 40 lowercase hex characters"
        )
    if re.fullmatch(r"[^@\s]+@sha256:[0-9a-f]{64}", previous_api_image) is None:
        raise MigrationSafetyError(
            "previous API image must be an immutable @sha256 digest reference"
        )

    previous = _load_revisions(previous_root)
    candidate = _load_revisions(candidate_root)
    previous_heads = _heads(previous)
    candidate_heads = _heads(candidate)
    if len(previous_heads) != 1 or len(candidate_heads) != 1:
        raise MigrationSafetyError(
            "N-1 and candidate Alembic graphs must each have exactly one head"
        )
    previous_head = next(iter(previous_heads))
    candidate_head = next(iter(candidate_heads))
    previous_ancestry = _ancestors(previous, previous_head)
    candidate_ancestry = _ancestors(candidate, candidate_head)
    missing_history = sorted(previous_ancestry.difference(candidate_ancestry))
    if missing_history:
        raise MigrationSafetyError(
            "candidate migration graph rewrites N-1 history: "
            + ", ".join(missing_history)
        )
    changed_history = sorted(
        revision_id
        for revision_id in previous_ancestry
        if _sha256(previous[revision_id].path) != _sha256(candidate[revision_id].path)
    )
    if changed_history:
        raise MigrationSafetyError(
            "candidate migration graph rewrites N-1 history bytes: "
            + ", ".join(changed_history)
        )

    introduced = sorted(
        candidate_ancestry.difference(previous_ancestry),
        key=lambda revision_id: candidate[revision_id].path.name,
    )
    violations = [
        violation
        for revision_id in introduced
        for violation in _migration_violations(candidate[revision_id])
    ]
    if violations:
        raise MigrationSafetyError(
            "candidate is not expand-only and cannot support N-1:\n- "
            + "\n- ".join(violations)
        )

    migrations = [
        {
            "path": candidate[revision_id].path.name,
            "revision": revision_id,
            "sha256": _sha256(candidate[revision_id].path),
        }
        for revision_id in introduced
    ]
    return {
        "candidate_head": candidate_head,
        "introduced_migrations": migrations,
        "n_minus_one_api_image": previous_api_image,
        "n_minus_one_head": previous_head,
        "policy": {
            "contract_changes_permitted": False,
            "expand_only": True,
            "n_minus_one_schema_compatibility": "expand_only_static",
        },
        "schema_version": 1,
        "status": "pass",
        "subject_git_sha": subject_git_sha,
    }


def _write_evidence(path: Path, evidence: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--previous-versions", type=Path, required=True)
    parser.add_argument("--candidate-versions", type=Path, required=True)
    parser.add_argument("--previous-api-image", required=True)
    parser.add_argument("--subject-git-sha", required=True)
    parser.add_argument("--evidence-out", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        evidence = build_evidence(
            candidate_root=args.candidate_versions,
            previous_api_image=args.previous_api_image,
            previous_root=args.previous_versions,
            subject_git_sha=args.subject_git_sha,
        )
        _write_evidence(args.evidence_out, evidence)
    except MigrationSafetyError as exc:
        raise SystemExit(f"migration expand/contract gate failed: {exc}") from exc
    print(
        "Migration gate passed: candidate schema is expand-only relative to "
        f"N-1 head {evidence['n_minus_one_head']}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
