// Helper utilities for the calculator
function add(a, b) {
  return a + b;
}

function formatResult(value) {
  return String(value);
}

module.exports = { add, formatResult };

function percentOf(value, p) {
  return value * p;
}

module.exports.percentOf = percentOf;
