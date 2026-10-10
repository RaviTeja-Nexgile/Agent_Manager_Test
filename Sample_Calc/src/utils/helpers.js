// Helper utilities for the calculator
function add(a, b) {
  return a + b;
}

function formatResult(value) {
  return String(value);
}

module.exports = { add, formatResult };

// Returns the given percent of a value (e.g. percentOf(200, 10) returns 20).
function percentOf(value, percent) {
  return (value * percent) / 100;
}

module.exports.percentOf = percentOf;
