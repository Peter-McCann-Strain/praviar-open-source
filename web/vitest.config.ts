import { defineConfig } from "vitest/config";
import path from "path";

export default defineConfig({
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.tsx"],
    include: ["tests/**/*.test.{ts,tsx}", "src/**/*.test.{ts,tsx}"],
    exclude: ["node_modules", "dist", "src/_archive/**"],
    coverage: {
      reporter: ["text", "html"],
      include: ["src/**/*.{ts,tsx}"],
      exclude: [
        "src/**/*.d.ts",
        "src/components/ui/**",
        "src/app/**", // Page components — tested via E2E
        "src/types/**", // Type-only files — no runtime logic
      ],
      thresholds: {
        lines: 75,
        functions: 67,
        branches: 60,
        statements: 70,
      },
    },
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
      "@praviar/shared-types": path.resolve(
        __dirname,
        "../packages/shared-types/src",
      ),
      "@praviar/showcase-fixture": path.resolve(
        __dirname,
        "../packages/showcase-fixture/typescript/index.ts",
      ),
      "server-only": path.resolve(__dirname, "./tests/server-only.ts"),
    },
  },
});
