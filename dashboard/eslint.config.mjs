import nextCoreWebVitals from "eslint-config-next/core-web-vitals";
import nextTypescript from "eslint-config-next/typescript";
import { dirname } from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const eslintConfig = [...nextCoreWebVitals, ...nextTypescript, {
  rules: {
    // [Task 1-A · Fix 4-c-002] The 5 critical rules below were `"off"` —
    // this made the "0 lint errors" badge structurally meaningless
    // (DNA #22 PASS ≠ TRUE): ESLint passed anything. Now `"warn"` so the
    // build still passes but real issues surface. Promote to `"error"`
    // in a later phase once the existing violations are cleaned up.
    "@typescript-eslint/no-explicit-any": "warn",
    "@typescript-eslint/no-unused-vars": "warn",
    "no-unreachable": "warn",
    "prefer-const": "warn",
    "react-hooks/exhaustive-deps": "warn",

    // TypeScript rules (kept off — see justification per rule)
    "@typescript-eslint/no-non-null-assertion": "off", // shadcn/ui components rely on `!` for ref forwarding
    "@typescript-eslint/ban-ts-comment": "off", // allow targeted `// @ts-expect-error` for upstream lib quirks
    "@typescript-eslint/prefer-as-const": "off", // cosmetic; `as const` already preferred where useful
    "@typescript-eslint/no-unused-disable-directive": "off", // noisy with mixed plugin configs

    // React rules (kept off — see justification per rule)
    "react-hooks/purity": "off", // experimental rule; high false-positive rate with React 19
    "react/no-unescaped-entities": "off", // dashboard uses `&ldquo;` entities intentionally for Vietnamese
    "react/display-name": "off", // Next.js App Router infers display names from filename
    "react/prop-types": "off", // TS-only codebase; prop-types is for propTypes runtime
    "react-compiler/react-compiler": "off", // React Compiler not enabled in this project

    // Next.js rules (kept off — see justification per rule)
    "@next/next/no-img-element": "off", // dashboard uses local SVG/PNG assets, no next/image optimization needed
    "@next/next/no-html-link-for-pages": "off", // App Router uses `next/link`; legacy rule for pages router

    // General JavaScript rules (kept off — see justification per rule)
    "no-console": "off", // dashboard API routes log diagnostic info intentionally
    "no-debugger": "off", // keep dev ergonomics; CI does not run with NODE_ENV=development
    "no-empty": "off", // empty `catch {}` blocks are intentional fail-open (DNA #7)
    "no-irregular-whitespace": "off", // dashboard has Vietnamese diacritics; rule false-positives
    "no-case-declarations": "off", // intentional pattern in reducer-style switches
    "no-fallthrough": "off", // each case has explicit `return`
    "no-mixed-spaces-and-tabs": "off", // cosmetic; tsconfig already enforces formatting
    "no-redeclare": "off", // TS already catches re-declarations at compile time
    "no-undef": "off", // TS already catches undefined identifiers
    "no-useless-escape": "off", // cosmetic; some regex literals need escapes
  },
}, {
  ignores: ["node_modules/**", ".next/**", "out/**", "build/**", "next-env.d.ts", "examples/**", "skills"]
}];

export default eslintConfig;
