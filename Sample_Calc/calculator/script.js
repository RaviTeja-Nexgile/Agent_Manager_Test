const display = document.getElementById("display");
const historyList = document.getElementById("historyList");
const clearHistoryBtn = document.getElementById("clearHistory");

let currentInput = "";
let previousInput = "";
let operator = null;
let shouldResetDisplay = false;

const history = [];
const MAX_HISTORY = 5;

const OPERATOR_SYMBOLS = {
  add: "+",
  subtract: "-",
  multiply: "×",
  divide: "÷",
  percent: "%",
};

function renderHistory() {
  historyList.innerHTML = "";
  history.forEach((entry) => {
    const li = document.createElement("li");
    li.textContent = entry;
    historyList.appendChild(li);
  });
}

function addToHistory(expression, result) {
  history.push(`${expression} = ${result}`);
  if (history.length > MAX_HISTORY) {
    history.shift();
  }
  renderHistory();
}

function clearHistory() {
  history.length = 0;
  renderHistory();
}

function updateDisplay(value) {
  display.textContent = value;
}

function appendNumber(number) {
  if (shouldResetDisplay) {
    currentInput = "";
    shouldResetDisplay = false;
  }
  if (number === "." && currentInput.includes(".")) return;
  currentInput += number;
  updateDisplay(currentInput);
}

function chooseOperator(op) {
  if (currentInput === "" && previousInput === "") return;
  if (currentInput === "" && previousInput !== "") {
    operator = op;
    return;
  }
  if (previousInput !== "" && currentInput !== "") {
    compute();
  }
  operator = op;
  previousInput = currentInput;
  currentInput = "";
}

function compute() {
  if (operator === null || currentInput === "") return;
  const a = parseFloat(previousInput);
  const b = parseFloat(currentInput);
  const expression = `${previousInput} ${OPERATOR_SYMBOLS[operator]} ${currentInput}`;
  let result;

  switch (operator) {
    case "add":
      result = a + b;
      break;
    case "subtract":
      result = a - b;
      break;
    case "multiply":
      result = a * b;
      break;
    case "divide":
      result = b === 0 ? "Error" : a / b;
      break;
    case "percent":
      result = a * (b / 100);
      break;
    default:
      return;
  }

  addToHistory(expression, result);
  previousInput = "";
  operator = null;
  currentInput = String(result);
  shouldResetDisplay = true;
  updateDisplay(currentInput);
}

function clear() {
  currentInput = "";
  previousInput = "";
  operator = null;
  shouldResetDisplay = false;
  updateDisplay("0");
}

function backspace() {
  if (shouldResetDisplay) return;
  currentInput = currentInput.slice(0, -1);
  updateDisplay(currentInput || "0");
}

clearHistoryBtn.addEventListener("click", clearHistory);

document.querySelectorAll(".btn").forEach((button) => {
  button.addEventListener("click", () => {
    if (button.dataset.value !== undefined) {
      appendNumber(button.dataset.value);
    } else if (button.dataset.action) {
      const action = button.dataset.action;
      switch (action) {
        case "clear":
          clear();
          break;
        case "backspace":
          backspace();
          break;
        case "equals":
          compute();
          break;
        default:
          chooseOperator(action);
      }
    }
  });
});

// Keyboard support
document.addEventListener("keydown", (event) => {
  const key = event.key;
  if (/[0-9.]/.test(key)) {
    appendNumber(key);
  } else if (key === "+") {
    chooseOperator("add");
  } else if (key === "-") {
    chooseOperator("subtract");
  } else if (key === "*") {
    chooseOperator("multiply");
  } else if (key === "/") {
    event.preventDefault();
    chooseOperator("divide");
  } else if (key === "%") {
    chooseOperator("percent");
  } else if (key === "Enter" || key === "=") {
    compute();
  } else if (key === "Backspace") {
    backspace();
  } else if (key === "Escape") {
    clear();
  }
});
