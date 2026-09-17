import { getChainInfoById } from "./chains.js";

const pendingSidebar = document.getElementById("pendingTxSidebar");
const pendingCards = new Map();

function shortenHash(value, head = 10, tail = 8) {
  const text = String(value || "");
  if (!text || text.length <= head + tail + 3) {
    return text;
  }
  return `${text.slice(0, head)}...${text.slice(-tail)}`;
}

function buildExplorerTxUrl(chainId, txHash) {
  const chainInfo = getChainInfoById(chainId);
  if (!chainInfo?.explorerUrl) {
    return null;
  }
  return `${chainInfo.explorerUrl}/tx/${txHash}`;
}

function jsonRpcRequest(url, method, params) {
  return fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      jsonrpc: "2.0",
      id: Date.now(),
      method,
      params,
    }),
  }).then(async (response) => {
    const payload = await response.json();
    if (!response.ok || payload?.error) {
      throw new Error(payload?.error?.message || `RPC request failed (${response.status})`);
    }
    return payload.result;
  });
}

async function waitForTransactionReceiptViaRpc(txHash, rpcUrls, maxAttempts = 360, pollDelayMs = 2500) {
  const urls = Array.isArray(rpcUrls) ? rpcUrls.filter(Boolean) : [];
  if (!urls.length) {
    return null;
  }

  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    for (const rpcUrl of urls) {
      try {
        const receipt = await jsonRpcRequest(rpcUrl, "eth_getTransactionReceipt", [txHash]);
        if (receipt) {
          return receipt;
        }
      } catch {
        
      }
    }

    await new Promise((resolve) => {
      window.setTimeout(resolve, pollDelayMs);
    });
  }

  return null;
}

async function watchTransactionConfirmation({ txHash, rpcUrls }) {
  const receiptFromRpc = await waitForTransactionReceiptViaRpc(txHash, rpcUrls);
  if (receiptFromRpc) {
    return receiptFromRpc.status === "0x1" || receiptFromRpc.status === 1 ? "confirmed" : "failed";
  }

  const ethersLib = window?.ethers;
  if (!ethersLib || !window.ethereum) {
    return "failed";
  }

  try {
    const provider = new ethersLib.providers.Web3Provider(window.ethereum, "any");
    const receipt = await provider.waitForTransaction(txHash);
    return receipt && Number(receipt.status) === 1 ? "confirmed" : "failed";
  } catch {
    return "failed";
  }
}

export function addPendingCard({ txHash, chainId, kind = "transfer", title, subtitle }) {
  if (!pendingSidebar || !txHash) {
    return null;
  }

  const existing = pendingCards.get(txHash);
  if (existing) {
    return existing;
  }

  const card = document.createElement("div");
  card.className = "pending-card";
  if (kind === "contract") {
    card.classList.add("contract-call");
  }

  const titleRow = document.createElement("div");
  titleRow.className = "title";
  let icon = "🔁";
  if (kind === "deploy") {
    icon = "🧱";
  } else if (kind === "contract") {
    icon = "⚙️";
  }
  titleRow.textContent = `${icon} ${title || "Transaction sent"}`;

  const hashRow = document.createElement("div");
  hashRow.className = "hash";
  const explorerUrl = buildExplorerTxUrl(chainId, txHash);
  if (explorerUrl) {
    hashRow.innerHTML = `Hash: <a href="${explorerUrl}" target="_blank" rel="noopener noreferrer">${shortenHash(
      txHash
    )}</a>`;
  } else {
    hashRow.innerHTML = `Hash: <code>${shortenHash(txHash)}</code>`;
  }

  const subtitleRow = document.createElement("div");
  subtitleRow.className = "subtitle";
  subtitleRow.textContent = subtitle || "Waiting for confirmation...";

  const statusRow = document.createElement("div");
  statusRow.className = "status-row";

  const badge = document.createElement("div");
  badge.className = "badge-waiting";
  badge.innerHTML = "<span>⏳</span><span>Waiting</span>";

  const actions = document.createElement("div");
  actions.className = "actions";

  const closeBtn = document.createElement("button");
  closeBtn.className = "close-btn";
  closeBtn.textContent = "Close";
  closeBtn.style.display = "none";
  closeBtn.addEventListener("click", () => {
    card.remove();
    pendingCards.delete(txHash);
  });

  actions.appendChild(closeBtn);
  statusRow.appendChild(badge);
  statusRow.appendChild(actions);

  card.appendChild(titleRow);
  card.appendChild(hashRow);
  card.appendChild(subtitleRow);
  card.appendChild(statusRow);

  pendingSidebar.insertBefore(card, pendingSidebar.firstChild);

  function setStatus(nextState, customText) {
    if (nextState === "confirmed") {
      badge.className = "badge-confirmed";
      badge.innerHTML = "<span>✅</span><span>Confirmed</span>";
      subtitleRow.textContent = customText || "Transaction confirmed.";
      closeBtn.style.display = "inline-flex";
      return;
    }

    if (nextState === "failed") {
      badge.className = "badge-failed";
      badge.innerHTML = "<span>❌</span><span>Failed</span>";
      subtitleRow.textContent = customText || "Transaction failed.";
      closeBtn.style.display = "inline-flex";
      return;
    }

    badge.className = "badge-waiting";
    badge.innerHTML = "<span>⏳</span><span>Waiting</span>";
    subtitleRow.textContent = customText || "Waiting for confirmation...";
    closeBtn.style.display = "none";
  }

  const api = {
    el: card,
    setStatus,
    close: () => closeBtn.click(),
  };

  pendingCards.set(txHash, api);
  return api;
}

export function createPendingTransactionCardAndWatch({
  txHash,
  chainId,
  kind,
  title,
  subtitle,
  rpcUrls,
  onSettled,
}) {
  const card = addPendingCard({ txHash, chainId, kind, title, subtitle });

  (async () => {
    const state = await watchTransactionConfirmation({ txHash, rpcUrls });
    card?.setStatus(state);
    try {
      await onSettled?.(state);
    } catch {
      // Callback failures should not break card updates.
    }
  })();

  return card;
}