// Floating concierge widget that reproduces agent-demo2.py's interactive flow in the browser.
(function () {
  const QUESTIONS = [
    { key: "origin", label: "From", prompt: "Where are you flying from?" },
    { key: "budget", label: "Budget", prompt: "What's your total budget? (e.g. $2000 per person, flexible)" },
    { key: "duration", label: "Length", prompt: "How long is the trip? (e.g. 7 days)" },
    { key: "timing", label: "When", prompt: "When are you thinking of traveling? (dates or season)" },
    { key: "travelers", label: "Travelers", prompt: "Who's going? (e.g. 2 adults, solo, family with kids)" },
    {
      key: "interests",
      label: "Trip style",
      prompt: "What kind of trip? (beach, adventure, culture, food, nightlife, nature, relaxation, family-friendly...)",
    },
    { key: "climate", label: "Climate", prompt: "Preferred climate?", default: "no preference" },
    { key: "notes", label: "Notes", prompt: "Anything else? (visa constraints, must-avoid, accessibility needs)", default: "none" },
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

  function scrollDown() {
    body.scrollTop = body.scrollHeight;
  }

  // Renders **bold** spans safely via DOM nodes (no innerHTML with model output).
  function appendInline(parent, text) {
    const parts = text.split("**");
    parts.forEach((part, i) => {
      if (!part) return;
      if (i % 2 === 1) {
        parent.appendChild(el("strong", null, part));
      } else {
        parent.appendChild(document.createTextNode(part));
      }
    });
  }

  // Minimal line-based formatter for the streamed itinerary: headings, bullets, rules.
  function renderResult(container, text) {
    container.textContent = "";
    for (const rawLine of text.split("\n")) {
      const line = rawLine.trimEnd();
      if (!line.trim()) continue;
      let node;
      if (/^###\s+/.test(line)) {
        node = el("h4", "cw-h3");
        appendInline(node, line.replace(/^###\s+/, ""));
      } else if (/^##\s+/.test(line)) {
        node = el("h3", "cw-h2");
        appendInline(node, line.replace(/^##\s+/, ""));
      } else if (/^#\s+/.test(line)) {
        node = el("h2", "cw-h1");
        appendInline(node, line.replace(/^#\s+/, ""));
      } else if (/^(---+|\*\*\*+)$/.test(line.trim())) {
        node = el("hr", "cw-rule");
      } else if (/^[-*•]\s+/.test(line.trim())) {
        node = el("p", "cw-bullet");
        appendInline(node, line.trim().replace(/^[-*•]\s+/, ""));
      } else {
        node = el("p", "cw-para");
        appendInline(node, line);
      }
      container.appendChild(node);
    }
  }

  function askCurrentQuestion() {
    const q = QUESTIONS[step];
    if (!q) return;

    const block = el("div", "cw-question");
    const hint = q.default ? ` — leave blank for "${q.default}"` : "";
    block.appendChild(el("label", "cw-question-text", q.prompt + hint));
    const input = el("input", "cw-input");
    input.type = "text";
    input.autocomplete = "off";
    input.spellcheck = false;
    input.placeholder = q.default || "Type your answer and press Enter";
    block.appendChild(input);
    body.appendChild(block);
    scrollDown();
    input.focus();

    input.addEventListener("keydown", (evt) => {
      if (evt.key !== "Enter" || running) return;
      const raw = input.value.trim();
      const value = raw || q.default || "";
      if (!value) return;

      const row = el("div", "cw-answered");
      row.appendChild(el("span", "cw-answered-label", q.label));
      row.appendChild(el("span", "cw-answered-value", value));
      body.replaceChild(row, block);

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
    const status = el("div", "cw-status", "Planning your trip — one moment…");
    body.appendChild(status);
    scrollDown();

    const result = el("div", "cw-result");
    body.appendChild(result);

    try {
      const res = await fetch("/api/plan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(trip),
      });

      if (!res.ok || !res.body) {
        let errText = await res.text().catch(() => "");
        if (!errText || errText.trimStart().startsWith("<")) errText = "request failed";
        status.remove();
        body.appendChild(el("div", "cw-error", `Something went wrong (${res.status}): ${errText}`));
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
        renderResult(result, text);
        scrollDown();
      }
      status.remove();
    } catch (err) {
      status.remove();
      body.appendChild(el("div", "cw-error", `Something went wrong: ${err.message || err}`));
    }

    finishRun();
  }

  function finishRun() {
    running = false;
    const again = el("button", "cw-again", "Plan another trip");
    again.addEventListener("click", startSession);
    body.appendChild(again);
    scrollDown();
  }

  function startSession() {
    step = 0;
    trip = {};
    running = false;
    body.textContent = "";
    body.appendChild(
      el("p", "cw-greeting", "Hello! A few quick questions and I'll put together destinations, an itinerary, and flight options for you.")
    );
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
