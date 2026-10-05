import assert from "node:assert/strict";
import test from "node:test";

import { formatConnectedDuration } from "../src/features/instagram/accountDates.ts";

test("formats connection duration in days and hours", () => {
  assert.equal(
    formatConnectedDuration(
      "2026-01-01T00:00:00Z",
      "2026-01-02T03:00:00Z",
    ),
    "1 dia e 3 horas",
  );
});

test("formats connection duration in hours when less than a day", () => {
  assert.equal(
    formatConnectedDuration(
      "2026-01-01T00:00:00Z",
      "2026-01-01T05:00:00Z",
    ),
    "5 horas",
  );
});

test("reports unavailable connection duration for missing or invalid timestamps", () => {
  assert.equal(formatConnectedDuration(null, null), "Duração indisponível");
  assert.equal(
    formatConnectedDuration("not-a-date", "2026-01-01T00:00:00Z"),
    "Duração indisponível",
  );
});
