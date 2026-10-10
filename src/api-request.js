// Performs a GET API request to a public REST endpoint using native fetch (Node 18+).
// Run with: node src/api-request.js

const API_URL = "https://jsonplaceholder.typicode.com/todos/1";

async function performApiRequest() {
  console.log(`Performing GET request to: ${API_URL}\n`);

  try {
    const response = await fetch(API_URL, {
      method: "GET",
      headers: {
        Accept: "application/json",
      },
    });

    console.log(`HTTP Status: ${response.status} ${response.statusText}`);

    if (!response.ok) {
      throw new Error(`Request failed with status ${response.status}`);
    }

    const data = await response.json();
    console.log("\nResponse body (JSON):");
    console.log(JSON.stringify(data, null, 2));
  } catch (error) {
    console.error("\nAPI request error:", error.message);
    process.exitCode = 1;
  }
}

performApiRequest();
