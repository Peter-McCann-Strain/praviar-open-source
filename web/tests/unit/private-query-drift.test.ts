import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import ts from "typescript";
import { describe, expect, it } from "vitest";
import { PRIVATE_QUERY_ROOTS } from "@/components/auth/auth-query-cache-boundary";

const SOURCE_ROOT = path.join(process.cwd(), "src");

const TANSTACK_QUERY_HOOKS = [
  "useQuery",
  "useInfiniteQuery",
  "useQueries",
  "useSuspenseQuery",
  "useSuspenseInfiniteQuery",
  "useSuspenseQueries",
] as const;

const TANSTACK_MUTATION_HOOKS = ["useMutation"] as const;

const QUERY_CLIENT_METHODS = [
  "fetchQuery",
  "fetchInfiniteQuery",
  "prefetchQuery",
  "prefetchInfiniteQuery",
  "ensureQueryData",
  "ensureInfiniteQueryData",
] as const;

const IMPERATIVE_QUERY_CACHE_METHODS = [
  "getQueryData",
  "setQueryData",
] as const;

const BULK_QUERY_CACHE_METHODS = [
  "getQueriesData",
  "setQueriesData",
  "invalidateQueries",
] as const;

const QUERY_KEY_HELPERS = [
  {
    name: "analysisReviewStatusKey",
    root: "analyses",
    requiredRootSegments: ["analyses", "review-status"],
  },
  {
    name: "decisionsKey",
    root: "reviewer-decisions",
    requiredRootSegments: ["reviewer-decisions"],
  },
] as const;

const SOURCE_ANALYSIS_MARKERS = [
  "@tanstack/react-query",
  "@/lib/api-client",
  "@/lib/query-keys",
  "mutationKey",
  ".getQueryData",
  ".setQueryData",
  ".getQueriesData",
  ".setQueriesData",
  ".invalidateQueries",
  ...QUERY_KEY_HELPERS.map((helper) => helper.name),
] as const;

type QueryKeyStatus =
  | { status: "private"; root: string }
  | { status: "failure"; reason: string };

interface SourceQueryContext {
  importedApiClientNames: Set<string>;
  importedApiClientNamespaces: Set<string>;
  importedAuthScopedQueryKeyNames: Set<string>;
  importedAuthScopedMutationKeyNames: Set<string>;
  importedAuthScopedQueryMatcherNames: Set<string>;
  importedAuthScopedMutationMatcherNames: Set<string>;
  validHelperNames: Set<string>;
}

interface SourceAnalysis {
  sourceFile: ts.SourceFile;
  context: SourceQueryContext;
  queryCalls: ts.CallExpression[];
  mutationCalls: ts.CallExpression[];
  imperativeCacheCalls: ts.CallExpression[];
  apiClientCalls: ts.CallExpression[];
  helperDefinitions: ts.VariableDeclaration[];
}

let sourceAnalysisPromise: Promise<SourceAnalysis[]> | null = null;

async function listSourceFiles(root: string): Promise<string[]> {
  const entries = await readdir(root, { withFileTypes: true });
  const nested = await Promise.all(
    entries.map(async (entry) => {
      const fullPath = path.join(root, entry.name);
      if (entry.isDirectory()) {
        return listSourceFiles(fullPath);
      }
      if (entry.isFile() && /\.(ts|tsx)$/.test(entry.name)) {
        return [fullPath];
      }
      return [];
    }),
  );
  return nested.flat();
}

async function _parseSourceFile(file: string): Promise<ts.SourceFile> {
  return createSourceFile(file, await readFile(file, "utf8"));
}

function createSourceFile(file: string, sourceText: string): ts.SourceFile {
  return ts.createSourceFile(
    file,
    sourceText,
    ts.ScriptTarget.Latest,
    true,
    file.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS,
  );
}

async function sourceAnalyses(): Promise<SourceAnalysis[]> {
  sourceAnalysisPromise ??= listSourceFiles(SOURCE_ROOT).then((files) =>
    Promise.all(
      files.map(async (file) => {
        if (file.endsWith(path.join("src", "lib", "query-keys.ts"))) {
          return null;
        }
        const sourceText = await readFile(file, "utf8");
        if (
          !SOURCE_ANALYSIS_MARKERS.some((marker) => sourceText.includes(marker))
        ) {
          return null;
        }

        const sourceFile = createSourceFile(file, sourceText);
        const context = sourceQueryContext(sourceFile);
        return {
          sourceFile,
          context,
          queryCalls: findQueryCalls(sourceFile),
          mutationCalls: findMutationCalls(sourceFile),
          imperativeCacheCalls: findImperativeCacheCalls(sourceFile),
          apiClientCalls: findApiClientCalls(sourceFile, context),
          helperDefinitions: helperDefinitions(sourceFile),
        };
      }),
    ).then((analyses) =>
      analyses.filter(
        (analysis): analysis is SourceAnalysis => analysis !== null,
      ),
    ),
  );
  return sourceAnalysisPromise;
}

function nodeLabel(sourceFile: ts.SourceFile, node: ts.Node): string {
  const { line, character } = sourceFile.getLineAndCharacterOfPosition(
    node.getStart(sourceFile),
  );
  return `${path.relative(process.cwd(), sourceFile.fileName)}:${line + 1}:${character + 1}`;
}

function walk(node: ts.Node, visit: (child: ts.Node) => void): void {
  node.forEachChild((child) => {
    visit(child);
    walk(child, visit);
  });
}

interface TanStackQueryImports {
  hooks: Set<string>;
  mutationHooks: Set<string>;
  namespaces: Set<string>;
}

function localTanStackQueryImports(
  sourceFile: ts.SourceFile,
): TanStackQueryImports {
  const hooks = new Set<string>();
  const mutationHooks = new Set<string>();
  const namespaces = new Set<string>();

  for (const statement of sourceFile.statements) {
    if (!ts.isImportDeclaration(statement)) continue;
    if (
      !ts.isStringLiteral(statement.moduleSpecifier) ||
      statement.moduleSpecifier.text !== "@tanstack/react-query"
    ) {
      continue;
    }
    const bindings = statement.importClause?.namedBindings;
    if (!bindings) continue;

    if (ts.isNamespaceImport(bindings)) {
      namespaces.add(bindings.name.text);
      continue;
    }

    if (!ts.isNamedImports(bindings)) continue;

    for (const specifier of bindings.elements) {
      const imported = specifier.propertyName?.text ?? specifier.name.text;
      if (
        TANSTACK_QUERY_HOOKS.includes(
          imported as (typeof TANSTACK_QUERY_HOOKS)[number],
        )
      ) {
        hooks.add(specifier.name.text);
      }
      if (
        TANSTACK_MUTATION_HOOKS.includes(
          imported as (typeof TANSTACK_MUTATION_HOOKS)[number],
        )
      ) {
        mutationHooks.add(specifier.name.text);
      }
    }
  }

  walk(sourceFile, (node) => {
    if (!ts.isVariableDeclaration(node) || !ts.isIdentifier(node.name)) return;
    if (!node.initializer) return;

    const initializer = unwrapExpression(node.initializer);
    const aliasesNamedHook =
      ts.isIdentifier(initializer) && hooks.has(initializer.text);
    const aliasesNamespaceHook =
      ts.isPropertyAccessExpression(initializer) &&
      ts.isIdentifier(initializer.expression) &&
      namespaces.has(initializer.expression.text) &&
      TANSTACK_QUERY_HOOKS.includes(
        initializer.name.text as (typeof TANSTACK_QUERY_HOOKS)[number],
      );

    if (aliasesNamedHook || aliasesNamespaceHook) {
      hooks.add(node.name.text);
    }

    const aliasesNamedMutationHook =
      ts.isIdentifier(initializer) && mutationHooks.has(initializer.text);
    const aliasesNamespaceMutationHook =
      ts.isPropertyAccessExpression(initializer) &&
      ts.isIdentifier(initializer.expression) &&
      namespaces.has(initializer.expression.text) &&
      TANSTACK_MUTATION_HOOKS.includes(
        initializer.name.text as (typeof TANSTACK_MUTATION_HOOKS)[number],
      );

    if (aliasesNamedMutationHook || aliasesNamespaceMutationHook) {
      mutationHooks.add(node.name.text);
    }
  });

  return { hooks, mutationHooks, namespaces };
}

function importedAuthScopedQueryKeyNames(
  sourceFile: ts.SourceFile,
): Set<string> {
  const names = new Set<string>();

  for (const statement of sourceFile.statements) {
    if (!ts.isImportDeclaration(statement)) continue;
    if (
      !ts.isStringLiteral(statement.moduleSpecifier) ||
      statement.moduleSpecifier.text !== "@/lib/query-keys"
    ) {
      continue;
    }
    const bindings = statement.importClause?.namedBindings;
    if (!bindings || !ts.isNamedImports(bindings)) continue;

    for (const specifier of bindings.elements) {
      const imported = specifier.propertyName?.text ?? specifier.name.text;
      if (imported === "authScopedQueryKey") {
        names.add(specifier.name.text);
      }
    }
  }

  return names;
}

function importedAuthScopedMutationKeyNames(
  sourceFile: ts.SourceFile,
): Set<string> {
  const names = new Set<string>();

  for (const statement of sourceFile.statements) {
    if (!ts.isImportDeclaration(statement)) continue;
    if (
      !ts.isStringLiteral(statement.moduleSpecifier) ||
      statement.moduleSpecifier.text !== "@/lib/query-keys"
    ) {
      continue;
    }
    const bindings = statement.importClause?.namedBindings;
    if (!bindings || !ts.isNamedImports(bindings)) continue;

    for (const specifier of bindings.elements) {
      const imported = specifier.propertyName?.text ?? specifier.name.text;
      if (imported === "authScopedMutationKey") {
        names.add(specifier.name.text);
      }
    }
  }

  return names;
}

function importedAuthScopedQueryMatcherNames(
  sourceFile: ts.SourceFile,
): Set<string> {
  const names = new Set<string>();

  for (const statement of sourceFile.statements) {
    if (!ts.isImportDeclaration(statement)) continue;
    if (
      !ts.isStringLiteral(statement.moduleSpecifier) ||
      statement.moduleSpecifier.text !== "@/lib/query-keys"
    ) {
      continue;
    }
    const bindings = statement.importClause?.namedBindings;
    if (!bindings || !ts.isNamedImports(bindings)) continue;

    for (const specifier of bindings.elements) {
      const imported = specifier.propertyName?.text ?? specifier.name.text;
      if (imported === "matchesAuthScopedQueryKey") {
        names.add(specifier.name.text);
      }
    }
  }

  return names;
}

function importedAuthScopedMutationMatcherNames(
  sourceFile: ts.SourceFile,
): Set<string> {
  const names = new Set<string>();

  for (const statement of sourceFile.statements) {
    if (!ts.isImportDeclaration(statement)) continue;
    if (
      !ts.isStringLiteral(statement.moduleSpecifier) ||
      statement.moduleSpecifier.text !== "@/lib/query-keys"
    ) {
      continue;
    }
    const bindings = statement.importClause?.namedBindings;
    if (!bindings || !ts.isNamedImports(bindings)) continue;

    for (const specifier of bindings.elements) {
      const imported = specifier.propertyName?.text ?? specifier.name.text;
      if (imported === "matchesAuthScopedMutationKey") {
        names.add(specifier.name.text);
      }
    }
  }

  return names;
}

function importedApiClientBindings(sourceFile: ts.SourceFile): {
  names: Set<string>;
  namespaces: Set<string>;
} {
  const names = new Set<string>();
  const namespaces = new Set<string>();

  for (const statement of sourceFile.statements) {
    if (!ts.isImportDeclaration(statement)) continue;
    if (
      !ts.isStringLiteral(statement.moduleSpecifier) ||
      statement.moduleSpecifier.text !== "@/lib/api-client"
    ) {
      continue;
    }
    const bindings = statement.importClause?.namedBindings;
    if (!bindings) continue;

    if (ts.isNamespaceImport(bindings)) {
      namespaces.add(bindings.name.text);
      continue;
    }

    if (!ts.isNamedImports(bindings)) continue;
    for (const specifier of bindings.elements) {
      const imported = specifier.propertyName?.text ?? specifier.name.text;
      if (imported === "apiClient") {
        names.add(specifier.name.text);
      }
    }
  }

  return { names, namespaces };
}

function localDeclarationNames(sourceFile: ts.SourceFile): Array<{
  name: string;
  node: ts.Node;
}> {
  const declarations: Array<{ name: string; node: ts.Node }> = [];
  walk(sourceFile, (node) => {
    if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name)) {
      declarations.push({ name: node.name.text, node: node.name });
    } else if (ts.isFunctionDeclaration(node) && node.name) {
      declarations.push({ name: node.name.text, node: node.name });
    } else if (ts.isParameter(node) && ts.isIdentifier(node.name)) {
      declarations.push({ name: node.name.text, node: node.name });
    } else if (ts.isClassDeclaration(node) && node.name) {
      declarations.push({ name: node.name.text, node: node.name });
    }
  });
  return declarations;
}

function authScopedQueryKeyImportFailures(sourceFile: ts.SourceFile): string[] {
  const importedNames = importedAuthScopedQueryKeyNames(sourceFile);
  const importedMutationNames = importedAuthScopedMutationKeyNames(sourceFile);
  const importedMatcherNames = importedAuthScopedQueryMatcherNames(sourceFile);
  const importedMutationMatcherNames =
    importedAuthScopedMutationMatcherNames(sourceFile);
  const apiClientBindings = importedApiClientBindings(sourceFile);
  const guardedNames = new Set([
    ...importedNames,
    ...importedMutationNames,
    ...importedMatcherNames,
    ...importedMutationMatcherNames,
    ...apiClientBindings.names,
    ...apiClientBindings.namespaces,
  ]);
  if (!guardedNames.size) return [];

  return localDeclarationNames(sourceFile).flatMap(({ name, node }) =>
    guardedNames.has(name)
      ? [
          `${nodeLabel(sourceFile, node)} ${name} shadows an imported query/auth helper`,
        ]
      : [],
  );
}

function isQueryClientMethodCall(expression: ts.Expression): boolean {
  return (
    ts.isPropertyAccessExpression(expression) &&
    QUERY_CLIENT_METHODS.includes(
      expression.name.text as (typeof QUERY_CLIENT_METHODS)[number],
    )
  );
}

function isImperativeQueryCacheMethodCall(expression: ts.Expression): boolean {
  return (
    ts.isPropertyAccessExpression(expression) &&
    (IMPERATIVE_QUERY_CACHE_METHODS.includes(
      expression.name.text as (typeof IMPERATIVE_QUERY_CACHE_METHODS)[number],
    ) ||
      BULK_QUERY_CACHE_METHODS.includes(
        expression.name.text as (typeof BULK_QUERY_CACHE_METHODS)[number],
      ))
  );
}

function queryCacheMethodName(call: ts.CallExpression): string | null {
  const expression = call.expression;
  return ts.isPropertyAccessExpression(expression)
    ? expression.name.text
    : null;
}

function isQueryCall(
  expression: ts.Expression,
  imports: TanStackQueryImports,
): boolean {
  if (
    ts.isPropertyAccessExpression(expression) &&
    ts.isIdentifier(expression.expression) &&
    imports.namespaces.has(expression.expression.text) &&
    TANSTACK_QUERY_HOOKS.includes(
      expression.name.text as (typeof TANSTACK_QUERY_HOOKS)[number],
    )
  ) {
    return true;
  }

  return (
    (ts.isIdentifier(expression) && imports.hooks.has(expression.text)) ||
    isQueryClientMethodCall(expression)
  );
}

function isMutationCall(
  expression: ts.Expression,
  imports: TanStackQueryImports,
): boolean {
  if (
    ts.isPropertyAccessExpression(expression) &&
    ts.isIdentifier(expression.expression) &&
    imports.namespaces.has(expression.expression.text) &&
    TANSTACK_MUTATION_HOOKS.includes(
      expression.name.text as (typeof TANSTACK_MUTATION_HOOKS)[number],
    )
  ) {
    return true;
  }

  return (
    ts.isIdentifier(expression) && imports.mutationHooks.has(expression.text)
  );
}

function unwrapExpression(expression: ts.Expression): ts.Expression {
  let current = expression;
  while (
    ts.isAsExpression(current) ||
    ts.isSatisfiesExpression(current) ||
    ts.isParenthesizedExpression(current) ||
    ts.isNonNullExpression(current) ||
    ts.isTypeAssertionExpression(current)
  ) {
    current = current.expression;
  }
  return current;
}

function stringLiteralText(expression: ts.Expression): string | null {
  const unwrapped = unwrapExpression(expression);
  return ts.isStringLiteral(unwrapped) ? unwrapped.text : null;
}

function queryOptionsObject(
  options: ts.Expression,
): ts.ObjectLiteralExpression | null {
  const unwrapped = unwrapExpression(options);
  if (!ts.isObjectLiteralExpression(unwrapped)) return null;
  return unwrapped;
}

function queryKeyProperties(options: ts.Expression): ts.PropertyAssignment[] {
  const unwrapped = queryOptionsObject(options);
  if (!unwrapped) return [];
  return unwrapped.properties.flatMap((property) => {
    if (!ts.isPropertyAssignment(property)) return [];
    const name = property.name;
    const isQueryKey =
      (ts.isIdentifier(name) && name.text === "queryKey") ||
      (ts.isStringLiteral(name) && name.text === "queryKey");
    return isQueryKey ? [property] : [];
  });
}

function queryOptionShapeFailures(options: ts.Expression): string[] {
  const unwrapped = queryOptionsObject(options);
  if (!unwrapped) {
    return ["query options must be an object literal"];
  }
  const failures: string[] = [];
  if (
    unwrapped.properties.some((property) => ts.isSpreadAssignment(property))
  ) {
    failures.push(
      "query options must not use object spreads because they can override queryKey",
    );
  }
  if (queryKeyProperties(options).length > 1) {
    failures.push("query options must declare exactly one queryKey");
  }
  return failures;
}

function queryKeyProperty(options: ts.Expression): ts.Expression | null {
  const properties = queryKeyProperties(options);
  if (properties.length !== 1) return null;
  return properties[0].initializer;
}

function mutationKeyProperties(
  options: ts.Expression,
): ts.PropertyAssignment[] {
  const unwrapped = queryOptionsObject(options);
  if (!unwrapped) return [];
  return unwrapped.properties.flatMap((property) => {
    if (!ts.isPropertyAssignment(property)) return [];
    const name = property.name;
    const isMutationKey =
      (ts.isIdentifier(name) && name.text === "mutationKey") ||
      (ts.isStringLiteral(name) && name.text === "mutationKey");
    return isMutationKey ? [property] : [];
  });
}

function mutationOptionShapeFailures(options: ts.Expression): string[] {
  const unwrapped = queryOptionsObject(options);
  if (!unwrapped) {
    return ["mutation options must be an object literal"];
  }
  const failures: string[] = [];
  if (
    unwrapped.properties.some((property) => ts.isSpreadAssignment(property))
  ) {
    failures.push(
      "mutation options must not use object spreads because they can override mutationKey",
    );
  }
  if (mutationKeyProperties(options).length > 1) {
    failures.push("mutation options must declare at most one mutationKey");
  }
  return failures;
}

function mutationKeyProperty(options: ts.Expression): ts.Expression | null {
  const properties = mutationKeyProperties(options);
  if (properties.length !== 1) return null;
  return properties[0].initializer;
}

function propertyInitializer(
  object: ts.ObjectLiteralExpression,
  propertyName: string,
): ts.Expression | null {
  for (const property of object.properties) {
    if (ts.isPropertyAssignment(property)) {
      const name = property.name;
      if (
        (ts.isIdentifier(name) && name.text === propertyName) ||
        (ts.isStringLiteral(name) && name.text === propertyName)
      ) {
        return property.initializer;
      }
      continue;
    }

    if (
      ts.isShorthandPropertyAssignment(property) &&
      property.name.text === propertyName
    ) {
      return property.name;
    }
  }
  return null;
}

function isUndefinedExpression(expression: ts.Expression): boolean {
  const unwrapped = unwrapExpression(expression);
  return ts.isIdentifier(unwrapped) && unwrapped.text === "undefined";
}

function isTokenIdentifier(expression: ts.Expression): boolean {
  const unwrapped = unwrapExpression(expression);
  return ts.isIdentifier(unwrapped) && unwrapped.text === "token";
}

function isAllowedApiClientTokenExpression(expression: ts.Expression): boolean {
  const unwrapped = unwrapExpression(expression);
  if (isTokenIdentifier(unwrapped)) return true;

  if (!ts.isBinaryExpression(unwrapped)) return false;
  const operator = unwrapped.operatorToken.kind;
  const isNullishFallback =
    operator === ts.SyntaxKind.BarBarToken ||
    operator === ts.SyntaxKind.QuestionQuestionToken;
  return (
    isNullishFallback &&
    isTokenIdentifier(unwrapped.left) &&
    isUndefinedExpression(unwrapped.right)
  );
}

function queryFnExpression(options: ts.Expression): ts.Expression | null {
  const object = queryOptionsObject(options);
  return object ? propertyInitializer(object, "queryFn") : null;
}

function mutationFnExpression(options: ts.Expression): ts.Expression | null {
  const object = queryOptionsObject(options);
  return object ? propertyInitializer(object, "mutationFn") : null;
}

function isApiClientCall(
  expression: ts.Expression,
  context: SourceQueryContext,
): boolean {
  return (
    (ts.isIdentifier(expression) &&
      context.importedApiClientNames.has(expression.text)) ||
    (ts.isPropertyAccessExpression(expression) &&
      ts.isIdentifier(expression.expression) &&
      context.importedApiClientNamespaces.has(expression.expression.text) &&
      expression.name.text === "apiClient")
  );
}

function apiClientTokenFailuresInExpression(
  expression: ts.Expression | null,
  context: SourceQueryContext,
  messages: {
    missingOptions: string;
    badToken: string;
  },
): string[] {
  if (!expression) return [];

  const failures: string[] = [];
  walk(expression, (node) => {
    if (
      !ts.isCallExpression(node) ||
      !isApiClientCall(node.expression, context)
    ) {
      return;
    }

    const requestOptions = node.arguments[1]
      ? unwrapExpression(node.arguments[1])
      : null;
    if (!requestOptions || !ts.isObjectLiteralExpression(requestOptions)) {
      failures.push(messages.missingOptions);
      return;
    }

    const tokenInitializer = propertyInitializer(requestOptions, "token");
    if (
      !tokenInitializer ||
      !isAllowedApiClientTokenExpression(tokenInitializer)
    ) {
      failures.push(messages.badToken);
    }
  });

  return failures;
}

function apiClientTokenFailures(
  options: ts.Expression,
  context: SourceQueryContext,
): string[] {
  return apiClientTokenFailuresInExpression(
    queryFnExpression(options),
    context,
    {
      missingOptions: "apiClient in a private query must pass token options",
      badToken:
        "apiClient token option in a private query must be token, token || undefined, or token ?? undefined",
    },
  );
}

function mutationApiClientTokenFailures(
  options: ts.Expression,
  context: SourceQueryContext,
): string[] {
  return apiClientTokenFailuresInExpression(
    mutationFnExpression(options),
    context,
    {
      missingOptions: "apiClient in a private mutation must pass token options",
      badToken:
        "apiClient token option in a private mutation must be token, token || undefined, or token ?? undefined",
    },
  );
}

function apiClientCallTokenFailures(
  call: ts.CallExpression,
  context: SourceQueryContext,
): string[] {
  if (!isApiClientCall(call.expression, context)) return [];

  const requestOptions = call.arguments[1]
    ? unwrapExpression(call.arguments[1])
    : null;
  if (!requestOptions || !ts.isObjectLiteralExpression(requestOptions)) {
    return [
      "apiClient calls in private frontend source must pass token options",
    ];
  }

  const tokenInitializer = propertyInitializer(requestOptions, "token");
  if (!tokenInitializer) {
    return [
      "apiClient calls in private frontend source must pass a token option",
    ];
  }

  if (!isAllowedApiClientTokenExpression(tokenInitializer)) {
    return [
      "apiClient token option must be token, token || undefined, or token ?? undefined",
    ];
  }

  return [];
}

function tokenBindingFailures(sourceFile: ts.SourceFile): string[] {
  const failures: string[] = [];
  walk(sourceFile, (node) => {
    if (!ts.isVariableDeclaration(node) || !ts.isIdentifier(node.name)) return;
    if (node.name.text !== "token") return;

    const initializer = node.initializer
      ? unwrapExpression(node.initializer)
      : null;
    const sourcedFromAuthHook =
      initializer &&
      ts.isCallExpression(initializer) &&
      ts.isIdentifier(initializer.expression) &&
      initializer.expression.text === "useAuthToken";

    if (!sourcedFromAuthHook) {
      failures.push(
        `${nodeLabel(sourceFile, node.name)} token variable must come directly from useAuthToken()`,
      );
    }
  });
  return failures;
}

function queryKeyStatusForOptions(
  options: ts.Expression,
  context: SourceQueryContext,
): QueryKeyStatus {
  const shapeFailures = queryOptionShapeFailures(options);
  if (shapeFailures.length > 0) {
    return {
      status: "failure",
      reason: shapeFailures.join("; "),
    };
  }
  const queryKey = queryKeyProperty(options);
  if (!queryKey) {
    return {
      status: "failure",
      reason: "missing top-level queryKey",
    };
  }
  return queryKeyStatus(queryKey, context);
}

function arrayRoot(expression: ts.Expression): QueryKeyStatus {
  const rootExpression = unwrapExpression(expression);
  if (!ts.isArrayLiteralExpression(rootExpression)) {
    return {
      status: "failure",
      reason: "authScopedQueryKey first argument must be a literal array",
    };
  }

  const root = rootExpression.elements[0];
  if (!root) {
    return {
      status: "failure",
      reason: "authScopedQueryKey literal array must include a root",
    };
  }

  const rootText = stringLiteralText(root);
  if (!rootText) {
    return {
      status: "failure",
      reason: "authScopedQueryKey root must be a string literal",
    };
  }

  return { status: "private", root: rootText };
}

function authScopedQueryKeyStatus(
  expression: ts.CallExpression,
  context: SourceQueryContext,
): QueryKeyStatus {
  if (
    !ts.isIdentifier(expression.expression) ||
    !context.importedAuthScopedQueryKeyNames.has(expression.expression.text)
  ) {
    return {
      status: "failure",
      reason:
        "queryKey must call imported authScopedQueryKey or an approved helper",
    };
  }

  const [, tokenArgument] = expression.arguments;
  if (
    !tokenArgument ||
    !ts.isIdentifier(tokenArgument) ||
    tokenArgument.text !== "token"
  ) {
    return {
      status: "failure",
      reason:
        "authScopedQueryKey token argument must be the live token identifier",
    };
  }

  return arrayRoot(expression.arguments[0]);
}

function authScopedMutationKeyStatus(
  expression: ts.CallExpression,
  context: SourceQueryContext,
): QueryKeyStatus {
  if (
    !ts.isIdentifier(expression.expression) ||
    !context.importedAuthScopedMutationKeyNames.has(expression.expression.text)
  ) {
    return {
      status: "failure",
      reason: "private mutationKey must call imported authScopedMutationKey",
    };
  }

  const [, tokenArgument] = expression.arguments;
  if (
    !tokenArgument ||
    !ts.isIdentifier(tokenArgument) ||
    tokenArgument.text !== "token"
  ) {
    return {
      status: "failure",
      reason:
        "authScopedMutationKey token argument must be the live token identifier",
    };
  }

  return arrayRoot(expression.arguments[0]);
}

function helperRootStatus(
  expression: ts.CallExpression,
  context: SourceQueryContext,
): QueryKeyStatus | null {
  if (!ts.isIdentifier(expression.expression)) return null;
  const helperName = expression.expression.getText();
  const helper = QUERY_KEY_HELPERS.find(
    (candidate) => candidate.name === helperName,
  );
  if (!helper || !context.validHelperNames.has(helperName)) return null;

  const [, tokenArgument] = expression.arguments;
  if (
    !tokenArgument ||
    !ts.isIdentifier(tokenArgument) ||
    tokenArgument.text !== "token"
  ) {
    return {
      status: "failure",
      reason: `${helper.name} must be called with the live token identifier`,
    };
  }

  return { status: "private", root: helper.root };
}

function queryKeyStatus(
  expression: ts.Expression,
  context: SourceQueryContext,
): QueryKeyStatus {
  const unwrapped = unwrapExpression(expression);
  if (!ts.isCallExpression(unwrapped)) {
    return {
      status: "failure",
      reason:
        "private queryKey must be produced by authScopedQueryKey or an approved helper",
    };
  }

  return (
    helperRootStatus(unwrapped, context) ??
    authScopedQueryKeyStatus(unwrapped, context)
  );
}

function mutationKeyFailuresForOptions(
  options: ts.Expression,
  context: SourceQueryContext,
): string[] {
  const shapeFailures = mutationOptionShapeFailures(options);
  if (shapeFailures.length > 0) return shapeFailures;

  const mutationKey = mutationKeyProperty(options);
  if (!mutationKey) return [];

  const unwrapped = unwrapExpression(mutationKey);
  if (ts.isCallExpression(unwrapped)) {
    const status = authScopedMutationKeyStatus(unwrapped, context);
    return status.status === "failure" ? [status.reason] : [];
  }

  const root = literalQueryRoot(mutationKey);
  if (
    root &&
    PRIVATE_QUERY_ROOTS.includes(root as (typeof PRIVATE_QUERY_ROOTS)[number])
  ) {
    return [`private mutationKey for ${root} must use authScopedMutationKey`];
  }

  if (!root) {
    return [
      "mutationKey must use a literal public mutation root or authScopedMutationKey",
    ];
  }

  return [];
}

function findQueryCalls(sourceFile: ts.SourceFile): ts.CallExpression[] {
  const imports = localTanStackQueryImports(sourceFile);
  const calls: ts.CallExpression[] = [];

  walk(sourceFile, (node) => {
    if (ts.isCallExpression(node) && isQueryCall(node.expression, imports)) {
      calls.push(node);
    }
  });

  return calls;
}

function findMutationCalls(sourceFile: ts.SourceFile): ts.CallExpression[] {
  const imports = localTanStackQueryImports(sourceFile);
  const calls: ts.CallExpression[] = [];

  walk(sourceFile, (node) => {
    if (ts.isCallExpression(node) && isMutationCall(node.expression, imports)) {
      calls.push(node);
    }
  });

  return calls;
}

function findImperativeCacheCalls(
  sourceFile: ts.SourceFile,
): ts.CallExpression[] {
  const calls: ts.CallExpression[] = [];

  walk(sourceFile, (node) => {
    if (
      ts.isCallExpression(node) &&
      isImperativeQueryCacheMethodCall(node.expression)
    ) {
      calls.push(node);
    }
  });

  return calls;
}

function findApiClientCalls(
  sourceFile: ts.SourceFile,
  context = sourceQueryContext(sourceFile),
): ts.CallExpression[] {
  const calls: ts.CallExpression[] = [];

  walk(sourceFile, (node) => {
    if (
      ts.isCallExpression(node) &&
      isApiClientCall(node.expression, context)
    ) {
      calls.push(node);
    }
  });

  return calls;
}

function literalQueryRoot(expression: ts.Expression): string | null {
  const unwrapped = unwrapExpression(expression);
  if (!ts.isArrayLiteralExpression(unwrapped)) return null;
  const root = unwrapped.elements[0];
  return root ? stringLiteralText(root) : null;
}

function authScopedQueryMatcherStatus(
  expression: ts.CallExpression,
  context: SourceQueryContext,
  predicateParameterName: string,
): QueryKeyStatus {
  if (
    !ts.isIdentifier(expression.expression) ||
    !context.importedAuthScopedQueryMatcherNames.has(expression.expression.text)
  ) {
    return {
      status: "failure",
      reason:
        "bulk private cache access must call imported matchesAuthScopedQueryKey",
    };
  }

  const [queryKeyArgument, baseKeyArgument, tokenArgument] =
    expression.arguments;
  const queryKeySource = queryKeyArgument
    ? unwrapExpression(queryKeyArgument)
    : null;
  if (
    !queryKeySource ||
    !ts.isPropertyAccessExpression(queryKeySource) ||
    !ts.isIdentifier(queryKeySource.expression) ||
    queryKeySource.expression.text !== predicateParameterName ||
    queryKeySource.name.text !== "queryKey"
  ) {
    return {
      status: "failure",
      reason:
        "matchesAuthScopedQueryKey must inspect the candidate query.queryKey",
    };
  }

  if (
    !tokenArgument ||
    !ts.isIdentifier(tokenArgument) ||
    tokenArgument.text !== "token"
  ) {
    return {
      status: "failure",
      reason:
        "matchesAuthScopedQueryKey token argument must be the live token identifier",
    };
  }

  if (!baseKeyArgument) {
    return {
      status: "failure",
      reason: "matchesAuthScopedQueryKey must include a literal base key",
    };
  }

  return arrayRoot(baseKeyArgument);
}

function predicateParameterName(
  predicate: ts.ArrowFunction | ts.FunctionExpression,
): string | null {
  const [parameter] = predicate.parameters;
  return parameter && ts.isIdentifier(parameter.name)
    ? parameter.name.text
    : null;
}

function predicateReturnExpression(
  predicate: ts.ArrowFunction | ts.FunctionExpression,
): ts.Expression | null {
  if (!ts.isBlock(predicate.body)) {
    return predicate.body;
  }

  if (predicate.body.statements.length !== 1) {
    return null;
  }

  const [statement] = predicate.body.statements;
  return ts.isReturnStatement(statement) && statement.expression
    ? statement.expression
    : null;
}

function bulkPredicateStatus(
  predicate: ts.Expression,
  context: SourceQueryContext,
): QueryKeyStatus {
  const unwrapped = unwrapExpression(predicate);

  if (!ts.isArrowFunction(unwrapped) && !ts.isFunctionExpression(unwrapped)) {
    return {
      status: "failure",
      reason: "private bulk cache predicate must be an inline function",
    };
  }

  const parameterName = predicateParameterName(unwrapped);
  if (!parameterName) {
    return {
      status: "failure",
      reason:
        "private bulk cache predicate must name the candidate query parameter",
    };
  }

  const returnExpression = predicateReturnExpression(unwrapped);
  if (!returnExpression) {
    return {
      status: "failure",
      reason:
        "private bulk cache predicate must be an expression body or a single return statement",
    };
  }

  const unwrappedReturn = unwrapExpression(returnExpression);
  if (!ts.isCallExpression(unwrappedReturn)) {
    return {
      status: "failure",
      reason:
        "private bulk cache predicate must return matchesAuthScopedQueryKey",
    };
  }

  return authScopedQueryMatcherStatus(unwrappedReturn, context, parameterName);
}

function bulkCacheFilterFailures(
  call: ts.CallExpression,
  context: SourceQueryContext,
): string[] {
  const filters = call.arguments[0]
    ? unwrapExpression(call.arguments[0])
    : null;
  if (!filters || !ts.isObjectLiteralExpression(filters)) {
    return ["bulk cache access must use an object literal filter"];
  }
  if (filters.properties.some((property) => ts.isSpreadAssignment(property))) {
    return [
      "bulk cache access must not use object spreads because they can override queryKey or predicate",
    ];
  }

  const queryKey = propertyInitializer(filters, "queryKey");
  if (!queryKey) {
    return ["bulk cache access must include a literal queryKey filter"];
  }

  const root = literalQueryRoot(queryKey);
  if (!root) {
    return [
      "bulk cache access queryKey filter must start with a string literal root",
    ];
  }

  if (
    !PRIVATE_QUERY_ROOTS.includes(root as (typeof PRIVATE_QUERY_ROOTS)[number])
  ) {
    return [];
  }

  const predicate = propertyInitializer(filters, "predicate");
  if (!predicate) {
    return [
      `private bulk cache access for ${root} must use matchesAuthScopedQueryKey`,
    ];
  }

  const predicateStatus = bulkPredicateStatus(predicate, context);
  if (predicateStatus.status === "failure") {
    return [predicateStatus.reason];
  }
  if (predicateStatus.root !== root) {
    return [
      `private bulk cache access for ${root} must predicate the same private root`,
    ];
  }

  return [];
}

function imperativeCacheCallFailures(
  call: ts.CallExpression,
  context: SourceQueryContext,
): string[] {
  const methodName = queryCacheMethodName(call);
  if (
    methodName &&
    BULK_QUERY_CACHE_METHODS.includes(
      methodName as (typeof BULK_QUERY_CACHE_METHODS)[number],
    )
  ) {
    return bulkCacheFilterFailures(call, context);
  }

  const queryKey = call.arguments[0];
  if (!queryKey) {
    return ["imperative cache access must pass a query key"];
  }

  const unwrapped = unwrapExpression(queryKey);
  if (ts.isCallExpression(unwrapped)) {
    const status =
      helperRootStatus(unwrapped, context) ??
      authScopedQueryKeyStatus(unwrapped, context);
    return status.status === "failure" ? [status.reason] : [];
  }

  const root = literalQueryRoot(queryKey);
  if (
    root &&
    PRIVATE_QUERY_ROOTS.includes(root as (typeof PRIVATE_QUERY_ROOTS)[number])
  ) {
    return [
      `private cache access for ${root} must use authScopedQueryKey or an approved helper`,
    ];
  }

  if (!root) {
    return [
      "imperative cache access must use a literal public query root or an auth-scoped private key",
    ];
  }

  return [];
}

function queryKeyFailuresForSource(sourceText: string): string[] {
  const sourceFile = ts.createSourceFile(
    "fixture.tsx",
    sourceText,
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TSX,
  );
  const context = sourceQueryContext(sourceFile);
  const failures = tokenBindingFailures(sourceFile);

  failures.push(
    ...findQueryCalls(sourceFile).flatMap((call) => {
      const options = call.arguments[0];
      if (!options) {
        return ["query options must be an object literal"];
      }
      const status = queryKeyStatusForOptions(options, context);
      if (status.status === "failure") return [status.reason];
      return apiClientTokenFailures(options, context);
    }),
  );

  return failures;
}

function mutationFailuresForSource(sourceText: string): string[] {
  const sourceFile = ts.createSourceFile(
    "fixture.tsx",
    sourceText,
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TSX,
  );
  const context = sourceQueryContext(sourceFile);
  const failures = tokenBindingFailures(sourceFile);

  failures.push(
    ...findMutationCalls(sourceFile).flatMap((call) => {
      const options = call.arguments[0];
      if (!options) {
        return ["mutation options must be an object literal"];
      }
      return [
        ...mutationKeyFailuresForOptions(options, context),
        ...mutationApiClientTokenFailures(options, context),
      ];
    }),
  );

  return failures;
}

function imperativeCacheFailuresForSource(sourceText: string): string[] {
  const sourceFile = ts.createSourceFile(
    "fixture.tsx",
    sourceText,
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TSX,
  );
  const context = sourceQueryContext(sourceFile);
  const failures = tokenBindingFailures(sourceFile);

  failures.push(
    ...findImperativeCacheCalls(sourceFile).flatMap((call) =>
      imperativeCacheCallFailures(call, context),
    ),
  );

  return failures;
}

function apiClientFailuresForSource(sourceText: string): string[] {
  const sourceFile = ts.createSourceFile(
    "fixture.tsx",
    sourceText,
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TSX,
  );
  const context = sourceQueryContext(sourceFile);

  return findApiClientCalls(sourceFile).flatMap((call) =>
    apiClientCallTokenFailures(call, context),
  );
}

function helperDefinitions(
  sourceFile: ts.SourceFile,
): ts.VariableDeclaration[] {
  const definitions: ts.VariableDeclaration[] = [];
  walk(sourceFile, (node) => {
    if (
      ts.isVariableDeclaration(node) &&
      ts.isIdentifier(node.name) &&
      QUERY_KEY_HELPERS.some(
        (helper) => helper.name === node.name.getText(sourceFile),
      )
    ) {
      definitions.push(node);
    }
  });
  return definitions;
}

function returnedExpressions(initializer: ts.Expression): ts.Expression[] {
  const unwrapped = unwrapExpression(initializer);
  if (ts.isArrowFunction(unwrapped) || ts.isFunctionExpression(unwrapped)) {
    if (!ts.isBlock(unwrapped.body)) {
      return [unwrapped.body];
    }
    const expressions: ts.Expression[] = [];
    walk(unwrapped.body, (node) => {
      if (ts.isReturnStatement(node) && node.expression) {
        expressions.push(node.expression);
      }
    });
    return expressions;
  }

  return [];
}

function isTokenUndefinedCheck(expression: ts.Expression): boolean {
  const condition = unwrapExpression(expression);
  if (!ts.isBinaryExpression(condition)) return false;
  const operator = condition.operatorToken.kind;
  if (
    operator !== ts.SyntaxKind.EqualsEqualsEqualsToken &&
    operator !== ts.SyntaxKind.EqualsEqualsToken
  ) {
    return false;
  }

  const left = unwrapExpression(condition.left);
  const right = unwrapExpression(condition.right);
  const isUndefinedExpression = (value: ts.Expression) =>
    ts.isIdentifier(value) && value.text === "undefined";
  return (
    (ts.isIdentifier(left) &&
      left.text === "token" &&
      isUndefinedExpression(right)) ||
    (isUndefinedExpression(left) &&
      ts.isIdentifier(right) &&
      right.text === "token")
  );
}

function literalArrayHasRequiredSegments(
  expression: ts.Expression,
  requiredSegments: readonly string[],
): boolean {
  const unwrapped = unwrapExpression(expression);
  if (!ts.isArrayLiteralExpression(unwrapped)) return false;
  const literalSegments = new Set(
    unwrapped.elements.flatMap((element) => {
      const text = stringLiteralText(element);
      return text ? [text] : [];
    }),
  );
  return requiredSegments.every((segment) => literalSegments.has(segment));
}

function helperReturnStatus(
  expression: ts.Expression,
  helper: (typeof QUERY_KEY_HELPERS)[number],
  context: SourceQueryContext,
): QueryKeyStatus {
  const unwrapped = unwrapExpression(expression);

  if (ts.isCallExpression(unwrapped)) {
    return authScopedQueryKeyStatus(unwrapped, context);
  }

  if (
    ts.isConditionalExpression(unwrapped) &&
    isTokenUndefinedCheck(unwrapped.condition)
  ) {
    const whenTruePrefix = literalArrayHasRequiredSegments(
      unwrapped.whenTrue,
      helper.requiredRootSegments,
    );
    const whenFalsePrefix = literalArrayHasRequiredSegments(
      unwrapped.whenFalse,
      helper.requiredRootSegments,
    );
    const whenTrueStatus = ts.isCallExpression(
      unwrapExpression(unwrapped.whenTrue),
    )
      ? authScopedQueryKeyStatus(
          unwrapExpression(unwrapped.whenTrue) as ts.CallExpression,
          context,
        )
      : null;
    const whenFalseStatus = ts.isCallExpression(
      unwrapExpression(unwrapped.whenFalse),
    )
      ? authScopedQueryKeyStatus(
          unwrapExpression(unwrapped.whenFalse) as ts.CallExpression,
          context,
        )
      : null;

    const valid =
      (whenTruePrefix &&
        whenFalseStatus?.status === "private" &&
        whenFalseStatus.root === helper.root) ||
      (whenFalsePrefix &&
        whenTrueStatus?.status === "private" &&
        whenTrueStatus.root === helper.root);

    return valid
      ? { status: "private", root: helper.root }
      : {
          status: "failure",
          reason: `${helper.name} must return an auth-scoped key except for token === undefined prefix invalidation`,
        };
  }

  return {
    status: "failure",
    reason: `${helper.name} must return authScopedQueryKey(..., token)`,
  };
}

function helperDefinitionStatus(
  definition: ts.VariableDeclaration,
  context: SourceQueryContext,
): QueryKeyStatus {
  const helper = QUERY_KEY_HELPERS.find(
    (candidate) => candidate.name === definition.name.getText(),
  );
  if (!helper) {
    return {
      status: "failure",
      reason: `${definition.name.getText()} is not an approved query-key helper`,
    };
  }

  const source = definition.initializer;
  if (!source) {
    return {
      status: "failure",
      reason: `${definition.name.getText()} helper has no initializer`,
    };
  }

  const returns = returnedExpressions(source);
  if (returns.length === 0) {
    return {
      status: "failure",
      reason: `${definition.name.getText()} helper must return a query key`,
    };
  }

  const statuses = returns.map((expression) =>
    helperReturnStatus(expression, helper, context),
  );
  const failure = statuses.find((status) => status.status === "failure");
  if (failure) return failure;

  return { status: "private", root: helper.root };
}

function helperHasRequiredSegments(
  definition: ts.VariableDeclaration,
): boolean {
  const helper = QUERY_KEY_HELPERS.find(
    (candidate) => candidate.name === definition.name.getText(),
  );
  if (!helper || !definition.initializer) return false;

  const foundSegments = new Set<string>();
  walk(definition.initializer, (node) => {
    if (ts.isStringLiteral(node)) {
      foundSegments.add(node.text);
    }
  });

  return helper.requiredRootSegments.every((segment) =>
    foundSegments.has(segment),
  );
}

function sourceQueryContext(sourceFile: ts.SourceFile): SourceQueryContext {
  const apiClientBindings = importedApiClientBindings(sourceFile);
  const context: SourceQueryContext = {
    importedApiClientNames: apiClientBindings.names,
    importedApiClientNamespaces: apiClientBindings.namespaces,
    importedAuthScopedQueryKeyNames:
      importedAuthScopedQueryKeyNames(sourceFile),
    importedAuthScopedMutationKeyNames:
      importedAuthScopedMutationKeyNames(sourceFile),
    importedAuthScopedQueryMatcherNames:
      importedAuthScopedQueryMatcherNames(sourceFile),
    importedAuthScopedMutationMatcherNames:
      importedAuthScopedMutationMatcherNames(sourceFile),
    validHelperNames: new Set<string>(),
  };

  for (const definition of helperDefinitions(sourceFile)) {
    const status = helperDefinitionStatus(definition, context);
    if (status.status === "private") {
      context.validHelperNames.add(definition.name.getText(sourceFile));
    }
  }

  return context;
}

describe("private query drift guard", () => {
  it("requires private query calls to use a token-scoped query key", async () => {
    const analyses = await sourceAnalyses();
    const failures: string[] = [];

    for (const {
      sourceFile,
      context,
      queryCalls,
      mutationCalls,
      imperativeCacheCalls,
      apiClientCalls,
    } of analyses) {
      failures.push(...authScopedQueryKeyImportFailures(sourceFile));
      if (queryCalls.length > 0 || imperativeCacheCalls.length > 0) {
        failures.push(...tokenBindingFailures(sourceFile));
      }
      for (const call of queryCalls) {
        const options = call.arguments[0];
        if (!options) {
          failures.push(
            `${nodeLabel(sourceFile, call)} query options must be an object literal`,
          );
          continue;
        }

        const status = queryKeyStatusForOptions(options, context);
        if (status.status === "failure") {
          failures.push(`${nodeLabel(sourceFile, options)} ${status.reason}`);
        } else {
          failures.push(
            ...apiClientTokenFailures(options, context).map(
              (failure) => `${nodeLabel(sourceFile, options)} ${failure}`,
            ),
          );
        }
      }
      for (const call of mutationCalls) {
        const options = call.arguments[0];
        if (!options) {
          failures.push(
            `${nodeLabel(sourceFile, call)} mutation options must be an object literal`,
          );
          continue;
        }

        failures.push(
          ...mutationKeyFailuresForOptions(options, context).map(
            (failure) => `${nodeLabel(sourceFile, options)} ${failure}`,
          ),
          ...mutationApiClientTokenFailures(options, context).map(
            (failure) => `${nodeLabel(sourceFile, options)} ${failure}`,
          ),
        );
      }
      for (const call of imperativeCacheCalls) {
        failures.push(
          ...imperativeCacheCallFailures(call, context).map(
            (failure) => `${nodeLabel(sourceFile, call)} ${failure}`,
          ),
        );
      }
      for (const call of apiClientCalls) {
        failures.push(
          ...apiClientCallTokenFailures(call, context).map(
            (failure) => `${nodeLabel(sourceFile, call)} ${failure}`,
          ),
        );
      }
    }

    expect(failures).toEqual([]);
  });

  it("keeps query-key helper functions token-scoped", async () => {
    const analyses = await sourceAnalyses();
    const definitions: Array<{
      context: SourceQueryContext;
      definition: ts.VariableDeclaration;
    }> = [];

    for (const {
      context,
      helperDefinitions: definitionsInSource,
    } of analyses) {
      definitions.push(
        ...definitionsInSource.map((definition) => ({
          context,
          definition,
        })),
      );
    }

    const definitionNames = new Set(
      definitions.map(({ definition }) => definition.name.getText()),
    );
    const failures = QUERY_KEY_HELPERS.flatMap((helper) => {
      if (!definitionNames.has(helper.name)) {
        return [`${helper.name} is missing`];
      }
      return [];
    });

    for (const { context, definition } of definitions) {
      const status = helperDefinitionStatus(definition, context);
      if (status.status === "failure") {
        failures.push(status.reason);
      }
      if (!helperHasRequiredSegments(definition)) {
        failures.push(
          `${definition.name.getText()} is missing its required literal query segments`,
        );
      }
    }

    expect(failures).toEqual([]);
  });

  it("keeps every private query root in the boundary purge list", async () => {
    const analyses = await sourceAnalyses();
    const roots = new Set<string>();
    const failures: string[] = [];

    for (const {
      context,
      queryCalls,
      helperDefinitions: definitionsInSource,
    } of analyses) {
      for (const call of queryCalls) {
        const options = call.arguments[0];
        if (!options) continue;

        const status = queryKeyStatusForOptions(options, context);
        if (status.status === "private") {
          roots.add(status.root);
        }
      }

      for (const definition of definitionsInSource) {
        const status = helperDefinitionStatus(definition, context);
        if (status.status === "private") {
          roots.add(status.root);
        }
      }
    }

    const purgeRoots = new Set<string>(PRIVATE_QUERY_ROOTS);
    for (const root of roots) {
      if (!purgeRoots.has(root)) {
        failures.push(`${root} is missing from PRIVATE_QUERY_ROOTS`);
      }
    }

    expect(failures.sort()).toEqual([]);
  });

  it("rejects comments or nested values pretending to scope an unscoped query", () => {
    const failures = queryKeyFailuresForSource(`
      import { useQuery } from "@tanstack/react-query";
      export function useBadQuery(id: string, token: string | null) {
        return useQuery({
          // queryKey: authScopedQueryKey(["reports", id] as const, token)
          queryKey: ["reports", id],
          meta: { queryKey: authScopedQueryKey(["reports", id] as const, token) },
          queryFn: () => Promise.resolve(null),
        });
      }
    `);

    expect(failures).toContain(
      "private queryKey must be produced by authScopedQueryKey or an approved helper",
    );
  });

  it("rejects private auth-scoped query keys without the live token identifier", () => {
    const failures = queryKeyFailuresForSource(`
      import { useQuery } from "@tanstack/react-query";
      import { authScopedQueryKey } from "@/lib/query-keys";
      export function useBadQuery(id: string) {
        return useQuery({
          queryKey: authScopedQueryKey(["reports", id] as const, undefined),
          queryFn: () => Promise.resolve(null),
        });
      }
    `);

    expect(failures).toContain(
      "authScopedQueryKey token argument must be the live token identifier",
    );
  });

  it("rejects shadowed token variables that are not sourced from useAuthToken", () => {
    const failures = queryKeyFailuresForSource(`
      import { useQuery } from "@tanstack/react-query";
      import { authScopedQueryKey } from "@/lib/query-keys";
      import { apiClient } from "@/lib/api-client";
      export function useBadReport(id: string) {
        const liveToken = useAuthToken();
        const token = undefined as string | null;
        return useQuery({
          queryKey: authScopedQueryKey(["reports", id] as const, token),
          queryFn: ({ signal }) =>
            apiClient("/reports/" + id, { token: liveToken!, signal }),
          enabled: !!liveToken,
        });
      }
    `);

    expect(failures).toEqual(
      expect.arrayContaining([
        expect.stringContaining(
          "token variable must come directly from useAuthToken()",
        ),
        "apiClient token option in a private query must be token, token || undefined, or token ?? undefined",
      ]),
    );
  });

  it("rejects apiClient token expressions where a stale token can take precedence", () => {
    const failures = queryKeyFailuresForSource(`
      import { useQuery } from "@tanstack/react-query";
      import { authScopedQueryKey } from "@/lib/query-keys";
      import { apiClient } from "@/lib/api-client";
      export function useBadReport(id: string) {
        const token = useAuthToken();
        const oldToken = "stale-token";
        return useQuery({
          queryKey: authScopedQueryKey(["reports", id] as const, token),
          queryFn: ({ signal }) =>
            apiClient("/reports/" + id, { token: oldToken || token, signal }),
          enabled: !!token,
        });
      }
    `);

    expect(failures).toContain(
      "apiClient token option in a private query must be token, token || undefined, or token ?? undefined",
    );
  });

  it("rejects stale token options passed through aliased apiClient imports", () => {
    const failures = queryKeyFailuresForSource(`
      import { useQuery } from "@tanstack/react-query";
      import { authScopedQueryKey } from "@/lib/query-keys";
      import { apiClient as request } from "@/lib/api-client";
      export function useBadReport(id: string) {
        const token = useAuthToken();
        const oldToken = "stale-token";
        return useQuery({
          queryKey: authScopedQueryKey(["reports", id] as const, token),
          queryFn: ({ signal }) =>
            request("/reports/" + id, { token: oldToken, signal }),
          enabled: !!token,
        });
      }
    `);

    expect(failures).toContain(
      "apiClient token option in a private query must be token, token || undefined, or token ?? undefined",
    );
  });

  it("rejects computed private query roots that boundary purge cannot see", () => {
    const failures = queryKeyFailuresForSource(`
      import { useQuery } from "@tanstack/react-query";
      import { authScopedQueryKey } from "@/lib/query-keys";
      const ROOT = "reports";
      export function useBadQuery(id: string, token: string | null) {
        return useQuery({
          queryKey: authScopedQueryKey([ROOT, id] as const, token),
          queryFn: () => Promise.resolve(null),
        });
      }
    `);

    expect(failures).toContain(
      "authScopedQueryKey root must be a string literal",
    );
  });

  it("rejects query option spreads that can override a scoped queryKey", () => {
    const failures = queryKeyFailuresForSource(`
      import { useQuery } from "@tanstack/react-query";
      import { authScopedQueryKey } from "@/lib/query-keys";
      const unsafeOptions = { queryKey: ["reports", "analysis-1"] };
      export function useBadQuery(id: string, token: string | null) {
        return useQuery({
          queryKey: authScopedQueryKey(["reports", id] as const, token),
          ...unsafeOptions,
          queryFn: () => Promise.resolve(null),
        });
      }
    `);

    expect(failures).toContain(
      "query options must not use object spreads because they can override queryKey",
    );
  });

  it("rejects namespace-imported query hooks with unscoped keys", () => {
    const failures = queryKeyFailuresForSource(`
      import * as Query from "@tanstack/react-query";
      export function useBadQuery(id: string) {
        return Query.useQuery({
          queryKey: ["reports", id],
          queryFn: () => Promise.resolve(null),
        });
      }
    `);

    expect(failures).toContain(
      "private queryKey must be produced by authScopedQueryKey or an approved helper",
    );
  });

  it("rejects aliased query hooks with unscoped private keys", () => {
    const failures = queryKeyFailuresForSource(`
      import { useQuery } from "@tanstack/react-query";
      const privateQuery = useQuery;
      export function useBadAlias(id: string) {
        return privateQuery({
          queryKey: ["reports", id],
          queryFn: () => Promise.resolve(null),
        });
      }
    `);

    expect(failures).toContain(
      "private queryKey must be produced by authScopedQueryKey or an approved helper",
    );
  });

  it("rejects query wrappers that hide nonliteral private options", () => {
    const failures = queryKeyFailuresForSource(`
      import { useQuery } from "@tanstack/react-query";
      const privateQuery = (options: unknown) => useQuery(options as never);
      export function useBadWrapper(id: string) {
        return privateQuery({
          queryKey: ["reports", id],
          queryFn: () => Promise.resolve(null),
        });
      }
    `);

    expect(failures).toContain("query options must be an object literal");
  });

  it("rejects approved helpers that contain a scoped call but return an unscoped key", () => {
    const sourceFile = ts.createSourceFile(
      "fixture.ts",
      `
        import { authScopedQueryKey } from "@/lib/query-keys";
        const analysisReviewStatusKey = (analysisId: string, token?: string | null) => {
          authScopedQueryKey(["analyses", analysisId, "review-status"] as const, token);
          return ["analyses", analysisId, "review-status"] as const;
        };
      `,
      ts.ScriptTarget.Latest,
      true,
      ts.ScriptKind.TS,
    );
    const [definition] = helperDefinitions(sourceFile);
    const context = sourceQueryContext(sourceFile);

    expect(helperDefinitionStatus(definition, context)).toEqual({
      status: "failure",
      reason:
        "analysisReviewStatusKey must return authScopedQueryKey(..., token)",
    });
  });

  it("rejects raw private cache reads outside auth-scoped query keys", () => {
    const failures = imperativeCacheFailuresForSource(`
      import { useQueryClient } from "@tanstack/react-query";
      export function useBadCachedReport(id: string) {
        const token = useAuthToken();
        const queryClient = useQueryClient();
        return queryClient.getQueryData(["reports", id]);
      }
    `);

    expect(failures).toContain(
      "private cache access for reports must use authScopedQueryKey or an approved helper",
    );
  });

  it("rejects raw private cache writes outside auth-scoped query keys", () => {
    const failures = imperativeCacheFailuresForSource(`
      import { useQueryClient } from "@tanstack/react-query";
      export function useBadCachedAnalysis(id: string) {
        const token = useAuthToken();
        const queryClient = useQueryClient();
        queryClient.setQueryData(["analyses", id], { id });
      }
    `);

    expect(failures).toContain(
      "private cache access for analyses must use authScopedQueryKey or an approved helper",
    );
  });

  it("allows auth-scoped private cache access and literal public cache roots", () => {
    const failures = imperativeCacheFailuresForSource(`
      import { useQueryClient } from "@tanstack/react-query";
      import { authScopedQueryKey } from "@/lib/query-keys";
      export function useGoodCacheAccess(id: string) {
        const token = useAuthToken();
        const queryClient = useQueryClient();
        const report = queryClient.getQueryData(
          authScopedQueryKey(["reports", id] as const, token),
        );
        queryClient.setQueryData(["public-reference-data"], { version: "2026-06" });
        return report;
      }
    `);

    expect(failures).toEqual([]);
  });

  it("rejects raw private bulk cache reads outside auth-scoped filters", () => {
    const failures = imperativeCacheFailuresForSource(`
      import { useQueryClient } from "@tanstack/react-query";
      export function useBadBulkRead() {
        const token = useAuthToken();
        const queryClient = useQueryClient();
        return queryClient.getQueriesData({ queryKey: ["reports"] });
      }
    `);

    expect(failures).toContain(
      "private bulk cache access for reports must use matchesAuthScopedQueryKey",
    );
  });

  it("rejects raw private bulk cache writes outside auth-scoped filters", () => {
    const failures = imperativeCacheFailuresForSource(`
      import { useQueryClient } from "@tanstack/react-query";
      export function useBadBulkWrite() {
        const token = useAuthToken();
        const queryClient = useQueryClient();
        queryClient.setQueriesData({ queryKey: ["analyses"] }, { leaked: true });
      }
    `);

    expect(failures).toContain(
      "private bulk cache access for analyses must use matchesAuthScopedQueryKey",
    );
  });

  it("allows auth-scoped private bulk cache access and literal public bulk cache roots", () => {
    const failures = imperativeCacheFailuresForSource(`
      import { useQueryClient } from "@tanstack/react-query";
      import { matchesAuthScopedQueryKey } from "@/lib/query-keys";
      export function useGoodBulkRead() {
        const token = useAuthToken();
        const queryClient = useQueryClient();
        return queryClient.getQueriesData({
          queryKey: ["analyses"],
          predicate: (query) =>
            matchesAuthScopedQueryKey(query.queryKey, ["analyses"] as const, token),
        });
        queryClient.setQueriesData({ queryKey: ["public-reference-data"] }, { version: "2026-06" });
      }
    `);

    expect(failures).toEqual([]);
  });

  it("rejects raw private query invalidations outside auth-scoped filters", () => {
    const failures = imperativeCacheFailuresForSource(`
      import { useQueryClient } from "@tanstack/react-query";
      export function useBadInvalidation() {
        const queryClient = useQueryClient();
        queryClient.invalidateQueries({ queryKey: ["reports"] });
      }
    `);

    expect(failures).toContain(
      "private bulk cache access for reports must use matchesAuthScopedQueryKey",
    );
  });

  it("rejects private bulk predicates that mention the matcher but return true", () => {
    const failures = imperativeCacheFailuresForSource(`
      import { useQueryClient } from "@tanstack/react-query";
      import { matchesAuthScopedQueryKey } from "@/lib/query-keys";
      export function useBadBulkPredicate() {
        const token = useAuthToken();
        const queryClient = useQueryClient();
        return queryClient.getQueriesData({
          queryKey: ["reports"],
          predicate: (query) =>
            matchesAuthScopedQueryKey(query.queryKey, ["reports"] as const, token) || true,
        });
      }
    `);

    expect(failures).toContain(
      "private bulk cache predicate must return matchesAuthScopedQueryKey",
    );
  });

  it("rejects private bulk predicates that call the matcher before returning true", () => {
    const failures = imperativeCacheFailuresForSource(`
      import { useQueryClient } from "@tanstack/react-query";
      import { matchesAuthScopedQueryKey } from "@/lib/query-keys";
      export function useBadBulkPredicate() {
        const token = useAuthToken();
        const queryClient = useQueryClient();
        return queryClient.getQueriesData({
          queryKey: ["reports"],
          predicate: (query) => {
            matchesAuthScopedQueryKey(query.queryKey, ["reports"] as const, token);
            return true;
          },
        });
      }
    `);

    expect(failures).toContain(
      "private bulk cache predicate must be an expression body or a single return statement",
    );
  });

  it("rejects private bulk predicates that match a non-candidate query key", () => {
    const failures = imperativeCacheFailuresForSource(`
      import { useQueryClient } from "@tanstack/react-query";
      import { matchesAuthScopedQueryKey } from "@/lib/query-keys";
      export function useBadBulkPredicate() {
        const token = useAuthToken();
        const queryClient = useQueryClient();
        const currentScopeProbe = { queryKey: ["reports", "auth:current"] };
        return queryClient.getQueriesData({
          queryKey: ["reports"],
          predicate: (query) =>
            matchesAuthScopedQueryKey(
              currentScopeProbe.queryKey,
              ["reports"] as const,
              token,
            ),
        });
      }
    `);

    expect(failures).toContain(
      "matchesAuthScopedQueryKey must inspect the candidate query.queryKey",
    );
  });

  it("rejects raw private mutation keys outside auth-scoped mutation keys", () => {
    const failures = mutationFailuresForSource(`
      import { useMutation } from "@tanstack/react-query";
      import { apiClient } from "@/lib/api-client";
      export function useBadShare(token: string | null) {
        return useMutation({
          mutationKey: ["reports", "analysis-1", "share"],
          mutationFn: () =>
            apiClient("/reports/analysis-1/share", {
              method: "POST",
              token: token || undefined,
            }),
        });
      }
    `);

    expect(failures).toContain(
      "private mutationKey for reports must use authScopedMutationKey",
    );
  });

  it("rejects private auth-scoped mutation keys without the live token identifier", () => {
    const failures = mutationFailuresForSource(`
      import { useMutation } from "@tanstack/react-query";
      import { authScopedMutationKey } from "@/lib/query-keys";
      import { apiClient } from "@/lib/api-client";
      export function useBadShare(token: string | null) {
        return useMutation({
          mutationKey: authScopedMutationKey(["reports", "analysis-1", "share"] as const, undefined),
          mutationFn: () =>
            apiClient("/reports/analysis-1/share", {
              method: "POST",
              token: token || undefined,
            }),
        });
      }
    `);

    expect(failures).toContain(
      "authScopedMutationKey token argument must be the live token identifier",
    );
  });

  it("allows auth-scoped private mutation keys and literal public mutation roots", () => {
    const failures = mutationFailuresForSource(`
      import { useMutation } from "@tanstack/react-query";
      import { authScopedMutationKey } from "@/lib/query-keys";
      import { apiClient } from "@/lib/api-client";
      export function useGoodShare(token: string | null) {
        const privateMutation = useMutation({
          mutationKey: authScopedMutationKey(["reports", "analysis-1", "share"] as const, token),
          mutationFn: () =>
            apiClient("/reports/analysis-1/share", {
              method: "POST",
              token: token || undefined,
            }),
        });
        const publicMutation = useMutation({
          mutationKey: ["public-reference-data", "warm"],
          mutationFn: () => Promise.resolve({ ok: true }),
        });
        return { privateMutation, publicMutation };
      }
    `);

    expect(failures).toEqual([]);
  });

  it("rejects useMutation apiClient calls where a stale token can take precedence", () => {
    const failures = mutationFailuresForSource(`
      import { useMutation } from "@tanstack/react-query";
      import { apiClient } from "@/lib/api-client";
      export function useBadMutation(token: string | null) {
        const oldToken = "stale-token";
        return useMutation({
          mutationFn: () =>
            apiClient("/reports/r1/share", {
              method: "POST",
              token: oldToken || token,
            }),
        });
      }
    `);

    expect(failures).toContain(
      "apiClient token option in a private mutation must be token, token || undefined, or token ?? undefined",
    );
  });

  it("keeps apiClient late private responses tied to the current auth boundary", async () => {
    const source = await readFile(
      path.join(SOURCE_ROOT, "lib", "api-client.ts"),
      "utf8",
    );

    expect(source).toContain("function assertAuthBoundaryStillCurrent(");
    expect(source).toMatch(
      /const data(?:: unknown)? = await response\.json\(\);\s+assertAuthBoundaryStillCurrent\(token\);/,
    );
    expect(
      source.match(/assertAuthBoundaryStillCurrent\(token\);/g)?.length,
    ).toBeGreaterThanOrEqual(4);
  });

  it("rejects direct apiClient calls without explicit token options", () => {
    const failures = apiClientFailuresForSource(`
      import { apiClient } from "@/lib/api-client";
      export async function saveReport(id: string) {
        return apiClient("/reports/" + id, { method: "POST" });
      }
    `);

    expect(failures).toContain(
      "apiClient calls in private frontend source must pass a token option",
    );
  });

  it("rejects direct apiClient calls where a stale token can take precedence", () => {
    const failures = apiClientFailuresForSource(`
      import { apiClient } from "@/lib/api-client";
      export async function saveReport(id: string, token: string | null) {
        const oldToken = "stale-token";
        return apiClient("/reports/" + id, {
          method: "POST",
          token: oldToken || token,
        });
      }
    `);

    expect(failures).toContain(
      "apiClient token option must be token, token || undefined, or token ?? undefined",
    );
  });

  it("rejects useMutation apiClient calls with missing token options", () => {
    const failures = apiClientFailuresForSource(`
      import { useMutation } from "@tanstack/react-query";
      import { apiClient } from "@/lib/api-client";
      export function useBadMutation() {
        return useMutation({
          mutationFn: () => apiClient("/reports/r1/share", { method: "POST" }),
        });
      }
    `);

    expect(failures).toContain(
      "apiClient calls in private frontend source must pass a token option",
    );
  });

  it("allows direct apiClient calls with live-token-shaped options", () => {
    const failures = apiClientFailuresForSource(`
      import { apiClient } from "@/lib/api-client";
      export async function saveReport(id: string, token: string | null) {
        return apiClient("/reports/" + id, {
          method: "POST",
          token: token ?? undefined,
        });
      }
    `);

    expect(failures).toEqual([]);
  });
});
