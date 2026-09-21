import { useEffect, useState } from "react";

function App() {
  const [health, setHealth] = useState<string>("checking...");

  useEffect(() => {
    // TODO: fetch("http://localhost:8000/health"), parse the JSON response,
    // and setHealth(...) with something derived from it (e.g. the
    // "status" field, or JSON.stringify(data) while you're just testing).
    // Wrap it so a failed fetch also updates `health` to something
    // visible ("error" o r the caught error's message) instead of
    // leaving the page stuck on "checking...".
    fetch("http://localhost:8000/health")
      .then((response) => response.json())
      .then((data) => setHealth(data.status))
      .catch((error: unknown) => {
        setHealth(error instanceof Error ? error.message : "error");
      });
  }, []);

  return (
    <div>
      <h1>CragMatch</h1>
      <p>Backend health: {health}</p>
    </div>
  );
} 

export default App;
