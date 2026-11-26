import { defineConfig } from "vitest/config";

export default defineConfig({
  server: {
    fs: {
      // Vite replaces the default list when a custom deny list is provided.
      deny: [
        ".env",
        ".env.*",
        "*.{crt,pem,key,p12,pfx,cer,der}",
        ".npmrc",
        ".yarnrc.yml",
        "**/.git/**",
        "**/Assets/**",
      ],
    },
  },
  test: {
    include: ["tests/unit/**/*.test.ts", "tests/integration/**/*.test.ts"],
    setupFiles: ["tests/fixtures/chinese-copy.ts"],
  },
});
