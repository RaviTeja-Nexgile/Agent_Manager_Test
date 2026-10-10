const test = require("node:test");
const assert = require("node:assert");
const helpers = require("../src/utils/helpers");

test("add adds two numbers", () => {
  assert.strictEqual(helpers.add(2, 3), 5);
});

test("formatResult returns text", () => {
  assert.strictEqual(helpers.formatResult(5), "5");
});
