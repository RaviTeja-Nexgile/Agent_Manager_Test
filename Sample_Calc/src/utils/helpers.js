// Helper utilities for the calculator
function add(a, b) {
  return a + b;
}

function formatResult(value) {
  return String(value);
}

module.exports = { add, formatResult };

function percentOf(value, percent) {
  return (value * percent) / 100;
}

module.exports.percentOf = percentOf;
