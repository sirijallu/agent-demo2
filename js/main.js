(function () {
  const toggleBtn = document.getElementById("agent-toggle");
  const closeBtn = document.getElementById("agent-close");
  const ctaBtn = document.getElementById("open-agent-cta");
  const win = document.getElementById("agent-window");
  const body = document.getElementById("agent-body");

  window.TravelAgentWidget.init(body);

  function openWindow() {
    win.classList.remove("hidden");
    win.setAttribute("aria-hidden", "false");
    window.TravelAgentWidget.start();
  }

  function closeWindow() {
    win.classList.add("hidden");
    win.setAttribute("aria-hidden", "true");
  }

  toggleBtn.addEventListener("click", () => {
    win.classList.contains("hidden") ? openWindow() : closeWindow();
  });
  closeBtn.addEventListener("click", closeWindow);
  ctaBtn.addEventListener("click", openWindow);
})();
