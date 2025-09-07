import eslint from "@eslint/js";
import vue from "eslint-plugin-vue";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  eslint.configs.recommended,
  ...tseslint.configs.recommended,
  ...vue.configs["flat/recommended"],
  {
    ignores: [
      "logs",
      "*.log",
      "npm-debug.log*",
      "yarn-debug.log*",
      "yarn-error.log*",
      "pnpm-debug.log*",
      "lerna-debug.log*",
      "node_modules",
      ".DS_Store",
      "dist",
      "dist-ssr",
      "coverage",
      "*.local",
      "__generated__",
      "*.config.js",
    ],
    languageOptions: {
      parserOptions: {
        parser: "@typescript-eslint/parser",
        projectService: true,
        ecmaVersion: 2022,
        extraFileExtensions: [".vue"],
      },
      globals: {
        ...globals.browser,
      },
    },
    rules: {
      "vue/multi-word-component-names": "off",
      "vue/max-attributes-per-line": "off",
    },
  },
);
