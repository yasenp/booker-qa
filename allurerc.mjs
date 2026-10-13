import { readFileSync } from "node:fs";
import { defineConfig } from "allure";

const base = JSON.parse(readFileSync(new URL("./allurerc.json", import.meta.url), "utf8"));
const mode = process.env.ALLURE_RUN_MODE ?? "live";
if (!["live", "offline"].includes(mode)) {
  throw new Error("ALLURE_RUN_MODE must be live or offline");
}

export default defineConfig({
  ...base,
  historyPath: `./reports/history/${mode}.jsonl`,
  appendHistory: true,
  globalAttachments: ["./docs/idempotency-coverage.md", `./reports/${mode}/coverage.json`],
});
