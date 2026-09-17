const MAX_PANEL_ITEMS = 120;

function formatTimeLabel(timestamp) {
  if (!timestamp) {
    return "";
  }

  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) {
    return "";
  }

  return date.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function createEventNode(event) {
  const node = document.createElement("article");
  node.className = `info-item level-${event.level || "info"}`;

  const header = document.createElement("div");
  header.className = "info-item-header";

  const title = document.createElement("div");
  title.className = "info-item-title";
  title.textContent = event.headline || "Event";

  const time = document.createElement("time");
  time.className = "info-item-time";
  time.textContent = formatTimeLabel(event.timestamp);

  header.appendChild(title);
  header.appendChild(time);
  node.appendChild(header);

  if (event.details) {
    const details = document.createElement("div");
    details.className = "info-item-details";
    details.textContent = event.details;
    node.appendChild(details);
  }

  return node;
}

function trimPanelItems(panelBody) {
  while (panelBody.children.length > MAX_PANEL_ITEMS) {
    panelBody.removeChild(panelBody.firstElementChild);
  }
}

function setToggleState(toggleButton, panelVisible) {
  if (!toggleButton) {
    return;
  }

  const showLabel = "Show Info Panel";
  const hideLabel = "Hide Info Panel";
  const label = panelVisible ? hideLabel : showLabel;
  const icon = toggleButton.querySelector("#infoToggleIcon");

  if (icon) {
    icon.src = panelVisible ? "./img/eye-off-2.png" : "./img/visible-eye.svg";
    icon.alt = label;
  }

  toggleButton.setAttribute("aria-label", label);
  toggleButton.title = label;
}

export function attachInfoPanel({
  toggleButton,
  panel,
  panelBody,
  container,
}) {
  if (!panel || !panelBody || !toggleButton || !container) {
    return {
      appendRequestEvents() {},
      appendClientEvent() {},
    };
  }

  const positionPanel = () => {
    if (panel.classList.contains("hidden")) {
      return;
    }

    const rect = container.getBoundingClientRect();
    const top = Math.max(12, rect.top);
    const left = rect.right + 14;
    const availableWidth = Math.max(0, window.innerWidth - left - 18);

    if (availableWidth < 260) {
      panel.classList.add("hidden");
      setToggleState(toggleButton, false);
      return;
    }

    panel.style.top = `${top}px`;
    panel.style.left = `${left}px`;
    panel.style.width = `${Math.min(390, availableWidth)}px`;
    panel.style.height = `${Math.max(240, rect.height)}px`;
  };

  const togglePanel = () => {
    const hidden = panel.classList.toggle("hidden");
    setToggleState(toggleButton, !hidden);
    if (!hidden) {
      positionPanel();
    }
  };

  toggleButton.addEventListener("click", togglePanel);
  window.addEventListener("resize", positionPanel);
  window.addEventListener("scroll", positionPanel);

  setToggleState(toggleButton, false);

  const appendRequestEvents = ({ requestId, events }) => {
    const safeEvents = Array.isArray(events) ? events : [];

    const requestLabel = document.createElement("div");
    requestLabel.className = "info-request-label";
    requestLabel.textContent = requestId
      ? `Request ${requestId.slice(0, 8)}`
      : "Request";
    panelBody.appendChild(requestLabel);

    if (!safeEvents.length) {
      const emptyNode = document.createElement("div");
      emptyNode.className = "info-item level-info";
      emptyNode.textContent = "No key events captured for this request.";
      panelBody.appendChild(emptyNode);
      trimPanelItems(panelBody);
      panelBody.scrollTop = panelBody.scrollHeight;
      return;
    }

    for (const event of safeEvents) {
      panelBody.appendChild(createEventNode(event));
    }

    trimPanelItems(panelBody);
    panelBody.scrollTop = panelBody.scrollHeight;
  };

  const appendClientEvent = ({ headline, details, level = "info" }) => {
    panelBody.appendChild(
      createEventNode({
        headline,
        details,
        level,
        timestamp: new Date().toISOString(),
      })
    );
    trimPanelItems(panelBody);
    panelBody.scrollTop = panelBody.scrollHeight;
  };

  return {
    appendRequestEvents,
    appendClientEvent,
  };
}
