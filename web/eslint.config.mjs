import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";
import react from "eslint-plugin-react";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    plugins: {
      react,
    },
    settings: {
      react: {
        version: "detect",
      },
    },
    rules: {
      "@typescript-eslint/no-explicit-any": "error",
      "@typescript-eslint/no-non-null-asserted-optional-chain": "error",
      // Ratchet the measured production ceiling; lower as remaining hotspots are split.
      complexity: ["error", 55],
      "react/display-name": "error",
      // Ignore identifiers prefixed with _ (intentionally unused parameters/vars)
      "@typescript-eslint/no-unused-vars": [
        "warn",
        {
          argsIgnorePattern: "^_",
          varsIgnorePattern: "^_",
          caughtErrorsIgnorePattern: "^_",
        },
      ],
    },
  },
  // Test files: relax rules that are unavoidable when mocking third-party APIs
  {
    files: ["tests/**/*.{ts,tsx}"],
    rules: {
      "@typescript-eslint/no-explicit-any": "off",
      "@typescript-eslint/no-non-null-asserted-optional-chain": "off",
      complexity: "off",
      "react/display-name": "off",
    },
  },
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    "**/.next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    // Vendored / generated files:
    "public/rdkit/**",
    "coverage/**",
    "**/test-results/**",
    "**/playwright-report*/**",
    ".turbo/**",
    ".vercel/**",
    ".pytest_cache/**",
    ".ruff_cache/**",
  ]),
]);

export default eslintConfig;
