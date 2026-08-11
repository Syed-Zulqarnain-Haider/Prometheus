/** Vitest's `globals: true` mode exposes describe/it/expect without imports (see
 *  vitest.config.ts). This reference makes them visible to `tsc --noEmit` too, without
 *  adding a `types` array to tsconfig - which would switch off automatic @types inclusion
 *  for everything else. */
/// <reference types="vitest/globals" />
