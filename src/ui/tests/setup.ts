/**
 * Test setup — global mocks for Bun test environment.
 */

// Mock process.stdout.columns for terminal width tests
if (!process.stdout.columns) {
  Object.defineProperty(process.stdout, "columns", { value: 80, writable: true })
}
if (!process.stdout.rows) {
  Object.defineProperty(process.stdout, "rows", { value: 24, writable: true })
}
