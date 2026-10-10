// Helper utilities for the calculator
function add(a, b) {
  return Math.round((Number(a) + Number(b)) * 100) / 100;
}

function formatResult(value) {
  return String(value);
}

module.exports = { add, formatResult };
