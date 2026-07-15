// Floating concierge widget: a welcome menu that branches into trip planning
// (agentic RAG via /api/plan) or a quick policy lookup (/api/policy).
(function () {
  const QUESTIONS = [
    {
      key: "origin",
      label: "From",
      prompt: "Where are you flying from?",
      chips: ["Dallas", "New York", "San Francisco", "Chicago"],
    },
    {
      key: "budget",
      label: "Budget",
      prompt: "What's your total budget?",
      chips: ["$1,000 per person", "$2,000 per person", "$5,000 per person", "Flexible"],
    },
    {
      key: "duration",
      label: "Length",
      prompt: "How long is the trip?",
      chips: ["Long weekend (3 days)", "5 days", "7 days", "2 weeks"],
    },
    {
      key: "timing",
      label: "When",
      prompt: "When are you thinking of traveling?",
      chips: ["This summer", "Fall", "Winter holidays", "Flexible"],
    },
    {
      key: "travelers",
      label: "Travelers",
      prompt: "Who's going?",
      chips: ["Solo", "Couple", "Family with kids", "Group of friends"],
    },
    {
      key: "interests",
      label: "Trip style",
      prompt: "What kind of trip? Pick any that fit, or type your own.",
      multi: true,
      chips: ["Beach", "Adventure", "Culture", "Food", "Nature", "Relaxation", "Nightlife", "Family-friendly"],
    },
    {
      key: "climate",
      label: "Climate",
      prompt: "Preferred climate?",
      default: "no preference",
      chips: ["Warm", "Mild", "Cold", "No preference"],
    },
    {
      key: "notes",
      label: "Notes",
      prompt: "Anything else? Add any constraints or requests.",
      default: "none",
      chips: [
        "Vegetarian-friendly food",
        "Wheelchair accessible",
        "Avoid long-haul flights",
        "None",
      ],
    },
  ];

  // Short chip label -> full question sent to /api/policy.
  const POLICY_TOPICS = [
    { label: "Cancellation & refunds", question: "What is Wanderly's cancellation and refund policy?" },
    { label: "Baggage allowance", question: "What is Wanderly's baggage policy — carry-on, checked, and fees?" },
    { label: "Travel insurance", question: "What does Wanderly's travel insurance cover, and what's excluded?" },
    { label: "Changing my dates", question: "Can I change my trip dates, and what does it cost?" },
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

  // Minimal line-based formatter for streamed markdown: headings, bullets, rules.
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

  // Streams a text/plain response body into a result container.
  async function streamInto(url, payload, result, status) {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!res.ok || !res.body) {
      let errText = await res.text().catch(() => "");
      if (!errText || errText.trimStart().startsWith("<")) errText = "request failed";
      if (status) status.remove();
      body.appendChild(el("div", "cw-error", `Something went wrong (${res.status}): ${errText}`));
      return false;
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
    if (status) status.remove();
    return true;
  }

  function backButton(label, handler) {
    const btn = el("button", "cw-back", label || "← Back to menu");
    btn.type = "button";
    btn.addEventListener("click", handler || showMenu);
    return btn;
  }

  // ---------- Welcome menu ----------

  function showMenu() {
    running = false;
    body.textContent = "";
    body.appendChild(el("p", "cw-greeting", "Hi! I'm your Wanderly concierge. How can I help?"));

    const menu = el("div", "cw-menu");

    const plan = el("button", "cw-menu-btn");
    plan.type = "button";
    plan.appendChild(el("span", "cw-menu-title", "🧳  Plan a trip"));
    plan.appendChild(el("span", "cw-menu-sub", "Destinations, itinerary & flights"));
    plan.addEventListener("click", startTripSession);

    const policies = el("button", "cw-menu-btn");
    policies.type = "button";
    policies.appendChild(el("span", "cw-menu-title", "📋  Check our policies"));
    policies.appendChild(el("span", "cw-menu-sub", "Cancellation, baggage & insurance"));
    policies.addEventListener("click", showPolicyMenu);

    menu.appendChild(plan);
    menu.appendChild(policies);
    body.appendChild(menu);
    scrollDown();
  }

  // ---------- Policy lookup ----------

  function showPolicyMenu() {
    running = false;
    body.textContent = "";
    body.appendChild(
      el("p", "cw-greeting", "What would you like to know? Pick a topic or type your own question.")
    );

    const block = el("div", "cw-question");
    block.appendChild(el("label", "cw-question-text", "Our policies"));
    const input = el("input", "cw-input");
    input.type = "text";
    input.autocomplete = "off";
    input.placeholder = "e.g. Can I cancel two weeks before my trip?";
    block.appendChild(input);

    const chipRow = el("div", "cw-chips");
    POLICY_TOPICS.forEach((topic) => {
      const btn = el("button", "cw-chip", topic.label);
      btn.type = "button";
      btn.addEventListener("click", () => askPolicy(topic.question));
      chipRow.appendChild(btn);
    });
    block.appendChild(chipRow);

    body.appendChild(block);
    block.appendChild(backButton());
    input.focus();

    input.addEventListener("keydown", (evt) => {
      if (evt.key !== "Enter") return;
      const q = input.value.trim();
      if (q) askPolicy(q);
    });
    scrollDown();
  }

  async function askPolicy(question) {
    if (running) return;
    running = true;
    body.textContent = "";

    const row = el("div", "cw-answered");
    row.appendChild(el("span", "cw-answered-label", "You asked"));
    row.appendChild(el("span", "cw-answered-value", question));
    body.appendChild(row);

    const status = el("div", "cw-status", "Checking our policies");
    body.appendChild(status);
    const result = el("div", "cw-result");
    body.appendChild(result);
    scrollDown();

    try {
      await streamInto("/api/policy", { question }, result, status);
    } catch (err) {
      status.remove();
      body.appendChild(el("div", "cw-error", `Something went wrong: ${err.message || err}`));
    }

    running = false;
    const actions = el("div", "cw-actions");
    const another = el("button", "cw-again", "Ask another question");
    another.addEventListener("click", showPolicyMenu);
    actions.appendChild(another);
    actions.appendChild(backButton());
    body.appendChild(actions);
    scrollDown();
  }

  // ---------- Trip planning ----------

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

    function submitAnswer(value) {
      if (running || !value) return;
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
    }

    if (q.chips && q.chips.length) {
      const chipRow = el("div", "cw-chips");
      const selected = new Set();

      q.chips.forEach((chip) => {
        const btn = el("button", "cw-chip", chip);
        btn.type = "button";
        btn.addEventListener("click", () => {
          if (running) return;
          if (q.multi) {
            if (selected.has(chip)) {
              selected.delete(chip);
              btn.classList.remove("selected");
            } else {
              selected.add(chip);
              btn.classList.add("selected");
            }
            input.value = Array.from(selected).join(", ");
            input.focus();
          } else {
            submitAnswer(chip === "None" ? q.default || chip : chip);
          }
        });
        chipRow.appendChild(btn);
      });

      if (q.multi) {
        const done = el("button", "cw-chip cw-chip-action", "Continue →");
        done.type = "button";
        done.addEventListener("click", () => {
          submitAnswer(input.value.trim() || q.default || "");
        });
        chipRow.appendChild(done);
      }

      block.appendChild(chipRow);
    }

    body.appendChild(block);
    if (step === 0) block.appendChild(backButton());
    scrollDown();
    input.focus();

    input.addEventListener("keydown", (evt) => {
      if (evt.key !== "Enter") return;
      submitAnswer(input.value.trim() || q.default || "");
    });
  }

  async function submitTrip() {
    running = true;
    const status = el("div", "cw-status", "Planning your trip — one moment");
    body.appendChild(status);
    scrollDown();

    const result = el("div", "cw-result");
    body.appendChild(result);

    try {
      await streamInto("/api/plan", trip, result, status);
    } catch (err) {
      status.remove();
      body.appendChild(el("div", "cw-error", `Something went wrong: ${err.message || err}`));
    }

    running = false;
    const actions = el("div", "cw-actions");
    const again = el("button", "cw-again", "Plan another trip");
    again.addEventListener("click", startTripSession);
    actions.appendChild(again);
    actions.appendChild(backButton());
    body.appendChild(actions);
    scrollDown();
  }

  function startTripSession() {
    step = 0;
    trip = {};
    running = false;
    body.textContent = "";
    body.appendChild(
      el("p", "cw-greeting", "A few quick questions and I'll put together destinations, an itinerary, and flight options.")
    );
    askCurrentQuestion();
  }

  window.TravelAgentWidget = {
    init(bodyElement) {
      body = bodyElement;
    },
    start() {
      if (!body.hasChildNodes()) {
        showMenu();
      }
    },
  };
})();
