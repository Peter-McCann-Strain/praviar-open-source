#!/usr/bin/env python3
"""Fail on Python runtime cycles and declared package-boundary violations."""

from __future__ import annotations

import argparse
from collections.abc import Iterable

import grimp

# Each source namespace is forbidden from directly depending on the listed
# higher-level namespaces. These contracts keep domain/data primitives usable
# without pulling in orchestration, delivery, or worker layers.
PACKAGE_BOUNDARY_CONTRACTS: dict[str, dict[str, tuple[str, ...]]] = {
    "api": {
        "api.auth": ("api.routes", "api.workers"),
        "api.db": ("api.routes", "api.services", "api.workers"),
        "api.schemas": ("api.routes", "api.services", "api.workers"),
        "api.services": ("api.routes",),
    },
    "praviar_pipeline": {
        "praviar_pipeline.clients": (
            "praviar_pipeline.agents",
            "praviar_pipeline.rendering",
        ),
        "praviar_pipeline.models": (
            "praviar_pipeline.agents",
            "praviar_pipeline.pipeline",
            "praviar_pipeline.rendering",
        ),
        "praviar_pipeline.utils": (
            "praviar_pipeline.agents",
            "praviar_pipeline.pipeline",
            "praviar_pipeline.rendering",
        ),
    },
}


def _strongly_connected_components(
    modules: Iterable[str],
    edges: dict[str, set[str]],
) -> list[list[str]]:
    index = 0
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[list[str]] = []

    def visit(module: str) -> None:
        nonlocal index
        indices[module] = index
        lowlinks[module] = index
        index += 1
        stack.append(module)
        on_stack.add(module)

        for imported in edges.get(module, set()):
            if imported not in indices:
                visit(imported)
                lowlinks[module] = min(lowlinks[module], lowlinks[imported])
            elif imported in on_stack:
                lowlinks[module] = min(lowlinks[module], indices[imported])

        if lowlinks[module] != indices[module]:
            return

        component: list[str] = []
        while stack:
            member = stack.pop()
            on_stack.remove(member)
            component.append(member)
            if member == module:
                break
        components.append(sorted(component))

    for module in sorted(modules):
        if module not in indices:
            visit(module)
    return components


def find_runtime_cycles(package: str) -> tuple[int, int, list[list[str]]]:
    graph = grimp.build_graph(
        package,
        exclude_type_checking_imports=True,
        cache_dir=None,
    )
    modules = set(graph.modules)
    edges = {
        module: set(graph.find_modules_directly_imported_by(module)) & modules
        for module in modules
    }
    cycles = sorted(
        (
            component
            for component in _strongly_connected_components(modules, edges)
            if len(component) > 1
        ),
        key=lambda component: (-len(component), component),
    )
    return len(modules), graph.count_imports(), cycles


def _is_in_namespace(module: str, namespace: str) -> bool:
    return module == namespace or module.startswith(f"{namespace}.")


def find_runtime_boundary_violations(package: str) -> list[tuple[str, str]]:
    """Return forbidden direct runtime imports for the package's contracts."""
    contracts = PACKAGE_BOUNDARY_CONTRACTS.get(package, {})
    if not contracts:
        return []
    graph = grimp.build_graph(
        package,
        exclude_type_checking_imports=True,
        cache_dir=None,
    )
    violations: set[tuple[str, str]] = set()
    for importer in graph.modules:
        for source_namespace, forbidden_namespaces in contracts.items():
            if not _is_in_namespace(importer, source_namespace):
                continue
            for imported in graph.find_modules_directly_imported_by(importer):
                if any(
                    _is_in_namespace(imported, forbidden)
                    for forbidden in forbidden_namespaces
                ):
                    violations.add((importer, imported))
    return sorted(violations)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("package", help="Importable root package to inspect")
    args = parser.parse_args()

    module_count, import_count, cycles = find_runtime_cycles(args.package)
    boundary_violations = find_runtime_boundary_violations(args.package)
    if cycles:
        print(
            f"{args.package}: {len(cycles)} runtime import cycle(s) across "
            f"{sum(len(component) for component in cycles)} modules"
        )
        for component in cycles:
            print("  - " + " -> ".join(component))
    if boundary_violations:
        print(
            f"{args.package}: {len(boundary_violations)} forbidden runtime boundary import(s)"
        )
        for importer, imported in boundary_violations:
            print(f"  - {importer} -> {imported}")

    if cycles or boundary_violations:
        return 1

    print(
        f"{args.package}: 0 runtime import cycles and 0 boundary violations "
        f"({module_count} modules, {import_count} imports, "
        f"{len(PACKAGE_BOUNDARY_CONTRACTS.get(args.package, {}))} contracts)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
