// Floating terminal widget that reproduces agent-demo2.py's interactive flow in the browser.
(function () {
  const QUESTIONS = [
    { key: "origin", prompt: "Departure city" },
    { key: "budget", prompt: "Total budget (e.g. $2000 per person, flexible)" },
    { key: "duration", prompt: "Trip length (e.g. 7 days)" },
    { key: "timing", prompt: "When are you thinking of traveling? (dates or season)" },
    { key: "travelers", prompt: "Who's going? (e.g. 2 adults, solo, family with kids)" },
    {
      key: "interests",
      prompt:
        "What kind of trip? (beach, adventure, culture, food, nightlife, nature, relaxation, family-friendly...)",
    },
    { key: "climate", prompt: "Preferred climate (warm, cold, mild, no preference)", default: "no preference" },
    { key: "notes", prompt: "Anything else? (visa constraints, must-avoid, accessibility needs)", default: "none" },
  ];

  let body;
  let step;
  let trip;
  let running;

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function printLine(text, className) {
    const line = el("div", "term-line" + (className ? " " + className : ""), text);
    body.appendChild(line);
    body.scrollTop = body.scrollHeight;
    return line;
  }

  function printHeaderBanner() {
    printLine("=".repeat(56), "term-system");
    printLine("  Claude Travel Agent — let's plan your next vacation", "term-heading");
    printLine("=".repeat(56), "term-system");
  }

  function askCurrentQuestion() {
    const q = QUESTIONS[step];
    if (!q) return;

    const row = el("div", "term-input-row");
    const suffix = q.default ? ` [${q.default}]` : "";
    const promptSpan = el("span", "term-prompt", `${q.prompt}${suffix}: `);
    const input = el("input", "term-input");
    input.type = "text";
    input.autocomplete = "off";
    input.spellcheck = false;

    row.appendChild(promptSpan);
    row.appendChild(input);
    body.appendChild(row);
    body.scrollTop = body.scrollHeight;
    input.focus();

    input.addEventListener("keydown", (evt) => {
      if (evt.key !== "Enter" || running) return;
      const raw = input.value.trim();
      const value = raw || q.default || "";
      input.disabled = true;

      const finalLine = el("div", "term-line");
      finalLine.appendChild(el("span", "term-prompt", `${q.prompt}${suffix}: `));
      finalLine.appendChild(el("span", "term-answer", value));
      body.replaceChild(finalLine, row);

      trip[q.key] = value;
      step += 1;

      if (step < QUESTIONS.length) {
        askCurrentQuestion();
      } else {
        submitTrip();
      }
    });
  }

  async function submitTrip() {
    running = true;
    printLine("");
    printLine("Thinking through your options...", "term-system");
    printLine("");

    const outputLine = el("div", "term-line term-answer");
    body.appendChild(outputLine);
    body.scrollTop = body.scrollHeight;

    try {
      const res = await fetch("/api/plan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(trip),
      });

      if (!res.ok || !res.body) {
        const errText = await res.text().catch(() => "");
        printLine(`\n[error] ${res.status}: ${errText || "request failed"}`, "term-error");
        finishRun();
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let text = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        text += decoder.decode(value, { stream: true });
        outputLine.textContent = text;
        body.scrollTop = body.scrollHeight;
      }
    } catch (err) {
      printLine(`\n[error] ${err.message || err}`, "term-error");
    }

    finishRun();
  }

  function finishRun() {
    running = false;
    printLine("");
    const restartRow = el("div", "term-input-row");
    restartRow.appendChild(el("span", "term-prompt", "Plan another trip? (y/n): "));
    const input = el("input", "term-input");
    input.type = "text";
    input.autocomplete = "off";
    restartRow.appendChild(input);
    body.appendChild(restartRow);
    body.scrollTop = body.scrollHeight;
    input.focus();

    input.addEventListener("keydown", (evt) => {
      if (evt.key !== "Enter") return;
      const answer = input.value.trim().toLowerCase();
      input.disabled = true;

      const finalLine = el("div", "term-line");
      finalLine.appendChild(el("span", "term-prompt", "Plan another trip? (y/n): "));
      finalLine.appendChild(el("span", "term-answer", answer || "n"));
      body.replaceChild(finalLine, restartRow);

      if (answer.startsWith("y")) {
        startSession();
      } else {
        printLine("Safe travels! ✈️", "term-system");
      }
    });
  }

  function startSession() {
    step = 0;
    trip = {};
    running = false;
    body.innerHTML = "";
    printHeaderBanner();
    askCurrentQuestion();
  }

  window.TravelAgentWidget = {
    init(bodyElement) {
      body = bodyElement;
    },
    start() {
      if (!body.hasChildNodes()) {
        startSession();
      }
    },
  };
})();
