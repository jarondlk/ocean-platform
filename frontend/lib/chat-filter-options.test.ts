import assert from "node:assert/strict";
import test from "node:test";
import { selectionChoices } from "./chat-filter-options.ts";

test("saved selections stay explicit when another filter or corpus change removes them", () => {
  assert.deepEqual(selectionChoices({values: ["s1", "s2"], truncated: false}, "old-station"), [
    {value: "old-station", unavailable: true}, {value: "s1", unavailable: false}, {value: "s2", unavailable: false},
  ]);
  assert.deepEqual(selectionChoices(undefined, "old-station"), [{value: "old-station", unavailable: true}]);
  assert.deepEqual(selectionChoices({values: ["s1", "s1"], truncated: false}, "s1"), [{value: "s1", unavailable: false}]);
});
test("choices respect the source contract and preserve an explicit false control filter", () => {
  assert.deepEqual(selectionChoices({values: ["false", "true"], truncated: false}, "false", ["true", "false"]), [
    {value: "false", unavailable: false}, {value: "true", unavailable: false},
  ]);
  assert.deepEqual(selectionChoices({values: ["qcauto_target", "qcauto_nontarget"], truncated: false}, "", ["qcauto_target"]), [
    {value: "qcauto_target", unavailable: false},
  ]);
});
