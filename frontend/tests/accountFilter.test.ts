import assert from "node:assert/strict";
import test from "node:test";

import {
  filterInstagramAccounts,
  toggleAllInstagramAccounts,
  toggleInstagramAccountSelection,
} from "../src/features/analytics/filterInstagramAccounts.ts";

const accounts = [
  { id: "1", username: "lunaa.ol21" },
  { id: "2", username: "mirella.cabri26" },
  { id: "3", username: "flashpost_demo" },
];

test("filters matching usernames when search starts with @", () => {
  assert.deepEqual(filterInstagramAccounts(accounts, "@lun"), [accounts[0]]);
});

test("filters by the first letters without requiring an @", () => {
  assert.deepEqual(filterInstagramAccounts(accounts, "mire"), [accounts[1]]);
});

test("returns all accounts for a blank search", () => {
  assert.deepEqual(filterInstagramAccounts(accounts, "  "), accounts);
});

test("toggles one account without changing the other selected accounts", () => {
  assert.deepEqual(toggleInstagramAccountSelection(["1"], "2"), ["1", "2"]);
  assert.deepEqual(toggleInstagramAccountSelection(["1", "2"], "1"), ["2"]);
});

test("selects every account and clears an already complete selection", () => {
  assert.deepEqual(toggleAllInstagramAccounts(["1", "2"], ["1"]), ["1", "2"]);
  assert.deepEqual(toggleAllInstagramAccounts(["1", "2"], ["1", "2"]), []);
});
