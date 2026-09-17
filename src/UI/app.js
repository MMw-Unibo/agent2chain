import { getChainName } from "./utils/chains.js";
import { deployCompiledContract, extractContractName, parseConstructorArgs } from "./utils/deploy_contract.js";
import { executeMetaMaskSendTransaction, extractMetaMaskTxMarkers } from "./utils/metamask_tx.js";
import { createPendingTransactionCardAndWatch } from "./utils/tx_cards.js";
import { extractKnowledgeLevelMarker, setKnowledgeLevel as setKnowledgeLevelNode, syncKnowledgeLevelFromServer,} from "./utils/knowledge_level.js";
import { renderMarkdown } from "./utils/text_utils.js";
import { renderWalletTooltip, shortAddress } from "./utils/wallet_utils.js";
import { attachInfoPanel } from "./utils/info_panel.js";

let walletState = {
  connected: false,
  account: null,
  chainId: null,
  networkName: null,
  balanceEth: null,
};

const connectBtn = document.getElementById("connectBtn");
const walletStatus = document.getElementById("walletStatus");
const mmStatusIcon = document.getElementById("mmStatusIcon");
const mmIconWrap = document.querySelector(".mm-icon-wrap");
const mmTooltip = document.getElementById("mmTooltip");
const knowledgeLevelValue = document.getElementById("knowledgeLevelValue");
const infoToggleBtn = document.getElementById("infoToggleBtn");
const infoPanel = document.getElementById("infoPanel");
const infoPanelBody = document.getElementById("infoPanelBody");
const chatContainer = document.getElementById("chatContainer");
const userInput = document.getElementById("userInput");
const sendBtn = document.getElementById("sendBtn");
const deployContractBtn = document.getElementById("deployContractBtn");
const scanContractBtn = document.getElementById("scanContractBtn");
const deployMenu = document.getElementById("deployMenu");
const closeDeployMenuBtn = document.getElementById("closeDeployMenuBtn");
const solFileInputDeploy = document.getElementById("solFileInputDeploy");
const solFileStatusDeploy = document.getElementById("solFileStatusDeploy");
const confirmDeployBtn = document.getElementById("confirmDeployBtn");
const solFilePreviewDeploy = document.getElementById("solFilePreviewDeploy");
const constructorArgsInputDeploy = document.getElementById("constructorArgsDeploy");
const scanMenu = document.getElementById("scanMenu");
const closeScanMenuBtn = document.getElementById("closeScanMenuBtn");
const solFileInputScan = document.getElementById("solFileInputScan");
const solFileStatusScan = document.getElementById("solFileStatusScan");
const solFilePreviewScan = document.getElementById("solFilePreviewScan");
const confirmScanBtn = document.getElementById("confirmScanBtn");

let uploadedDeployFileName = "";
let uploadedDeploySource = "";
let uploadedScanFileName = "";
let uploadedScanSource = "";

const infoPanelController = attachInfoPanel({
  toggleButton: infoToggleBtn,
  panel: infoPanel,
  panelBody: infoPanelBody,
  container: document.querySelector(".container"),
});

function setKnowledgeLevel(level) {
  setKnowledgeLevelNode(knowledgeLevelValue, level);
}

window.setKnowledgeLevel = setKnowledgeLevel;
setKnowledgeLevel("Beginner");

function addMessage(sender, text, options = {}) {
  const { markdown = false } = options;
  const node = document.createElement("div");
  node.className = `message ${sender}-message`;
  if (markdown) {
    node.innerHTML = renderMarkdown(text);
  } else {
    node.textContent = text;
  }
  chatContainer.appendChild(node);
  chatContainer.scrollTop = chatContainer.scrollHeight;
}

function setChatEnabled(enabled) {
  userInput.disabled = !enabled;
  sendBtn.disabled = !enabled;
  if (deployContractBtn) {
    deployContractBtn.disabled = !enabled;
  }
  if (scanContractBtn) {
    scanContractBtn.disabled = !enabled;
  }
}

function resetDeployState() {
  uploadedDeployFileName = "";
  uploadedDeploySource = "";

  if (solFileInputDeploy) {
    solFileInputDeploy.value = "";
  }
  if (solFileStatusDeploy) {
    solFileStatusDeploy.textContent = "No file uploaded";
    solFileStatusDeploy.style.color = "";
  }
  if (solFilePreviewDeploy) {
    solFilePreviewDeploy.textContent = "";
  }
  if (constructorArgsInputDeploy) {
    constructorArgsInputDeploy.value = "";
    constructorArgsInputDeploy.style.borderColor = "";
  }
  if (confirmDeployBtn) {
    confirmDeployBtn.disabled = true;
    confirmDeployBtn.textContent = "Deploy";
  }
}

function resetScanState() {
  uploadedScanFileName = "";
  uploadedScanSource = "";

  if (solFileInputScan) {
    solFileInputScan.value = "";
  }
  if (solFileStatusScan) {
    solFileStatusScan.textContent = "No file uploaded";
    solFileStatusScan.style.color = "";
  }
  if (solFilePreviewScan) {
    solFilePreviewScan.textContent = "";
  }
  if (confirmScanBtn) {
    confirmScanBtn.disabled = true;
    confirmScanBtn.textContent = "Start Auditing";
  }
}

function openDeployMenu() {
  if (!deployMenu) {
    return;
  }
  deployMenu.classList.remove("hidden");
  deployMenu.setAttribute("aria-hidden", "false");
}

function closeDeployMenu() {
  if (!deployMenu) {
    return;
  }
  deployMenu.classList.add("hidden");
  deployMenu.setAttribute("aria-hidden", "true");
  resetDeployState();
}

function openScanMenu() {
  if (!scanMenu) {
    return;
  }
  scanMenu.classList.remove("hidden");
  scanMenu.setAttribute("aria-hidden", "false");
}

function closeScanMenu() {
  if (!scanMenu) {
    return;
  }
  scanMenu.classList.add("hidden");
  scanMenu.setAttribute("aria-hidden", "true");
  resetScanState();
}

function setupDeployMenu() {
  if (!deployContractBtn || !deployMenu || !solFileInputDeploy || !confirmDeployBtn) {
    return;
  }

  closeDeployMenu();
  closeScanMenu();

  deployContractBtn.addEventListener("click", () => {
    if (!walletState.connected) {
      addMessage("ai", "Connect MetaMask before deploying a contract.");
      return;
    }
    openDeployMenu();
  });

  if (scanContractBtn) {
    scanContractBtn.addEventListener("click", () => {
      if (!walletState.connected) {
        addMessage("ai", "Connect MetaMask before running a smart contract audit.");
        return;
      }
      openScanMenu();
    });
  }

  if (closeDeployMenuBtn) {
    closeDeployMenuBtn.addEventListener("click", () => {
      closeDeployMenu();
    });
  }

  deployMenu.addEventListener("click", (event) => {
    if (event.target === deployMenu) {
      closeDeployMenu();
    }
  });

  if (closeScanMenuBtn) {
    closeScanMenuBtn.addEventListener("click", () => {
      closeScanMenu();
    });
  }

  if (scanMenu) {
    scanMenu.addEventListener("click", (event) => {
      if (event.target === scanMenu) {
        closeScanMenu();
      }
    });
  }

  solFileInputDeploy.addEventListener("change", () => {
    const file = solFileInputDeploy.files && solFileInputDeploy.files[0];
    const isValid = !!file && /\.sol$/i.test(file.name);

    if (!isValid) {
      uploadedDeployFileName = "";
      uploadedDeploySource = "";
      if (solFileStatusDeploy) {
        solFileStatusDeploy.textContent = "Invalid file. Please upload a .sol file";
        solFileStatusDeploy.style.color = "#c0392b";
      }
      if (solFilePreviewDeploy) {
        solFilePreviewDeploy.textContent = "";
      }
      confirmDeployBtn.disabled = true;
      return;
    }

    const reader = new FileReader();
    reader.onload = () => {
      const text = typeof reader.result === "string" ? reader.result : "";
      uploadedDeployFileName = file.name;
      uploadedDeploySource = text;

      if (solFileStatusDeploy) {
        solFileStatusDeploy.textContent = `${file.name} uploaded`;
        solFileStatusDeploy.style.color = "#15803d";
      }

      const previewLimit = 20 * 1024;
      if (solFilePreviewDeploy) {
        solFilePreviewDeploy.textContent =
          text.length > previewLimit
            ? `${text.slice(0, previewLimit)}\n\n... (preview truncated) ...`
            : text;
      }

      confirmDeployBtn.disabled = false;
    };
    reader.readAsText(file);
  });

  if (solFileInputScan && confirmScanBtn) {
    solFileInputScan.addEventListener("change", () => {
      const file = solFileInputScan.files && solFileInputScan.files[0];
      const isValid = !!file && /\.sol$/i.test(file.name);

      if (!isValid) {
        uploadedScanFileName = "";
        uploadedScanSource = "";
        if (solFileStatusScan) {
          solFileStatusScan.textContent = "Invalid file. Please upload a .sol file";
          solFileStatusScan.style.color = "#c0392b";
        }
        if (solFilePreviewScan) {
          solFilePreviewScan.textContent = "";
        }
        confirmScanBtn.disabled = true;
        return;
      }

      const reader = new FileReader();
      reader.onload = () => {
        const text = typeof reader.result === "string" ? reader.result : "";
        uploadedScanFileName = file.name;
        uploadedScanSource = text;

        if (solFileStatusScan) {
          solFileStatusScan.textContent = `${file.name} uploaded`;
          solFileStatusScan.style.color = "#15803d";
        }

        const previewLimit = 20 * 1024;
        if (solFilePreviewScan) {
          solFilePreviewScan.textContent =
            text.length > previewLimit
              ? `${text.slice(0, previewLimit)}\n\n... (preview truncated) ...`
              : text;
        }

        confirmScanBtn.disabled = false;
      };
      reader.readAsText(file);
    });
  }

  confirmDeployBtn.addEventListener("click", async () => {
    if (!uploadedDeployFileName || !uploadedDeploySource) {
      addMessage("ai", "Upload a Solidity file before deploying.");
      return;
    }

    let constructorArgs = [];
    try {
      constructorArgs = parseConstructorArgs(constructorArgsInputDeploy?.value || "");
      if (constructorArgsInputDeploy) {
        constructorArgsInputDeploy.style.borderColor = "";
      }
    } catch {
      if (constructorArgsInputDeploy) {
        constructorArgsInputDeploy.style.borderColor = "#dc2626";
      }
      closeDeployMenu();
      addMessage(
        "ai",
        "Deployment canceled: there was a problem with the constructor parameters. Check argument format and count."
      );
      return;
    }

    confirmDeployBtn.disabled = true;
    confirmDeployBtn.textContent = "Compiling...";

    const inferredName = extractContractName(uploadedDeploySource) || uploadedDeployFileName.replace(/\.sol$/i, "");
    addMessage("user", `Deploy contract ${inferredName}`);

    const isMetaMaskRejection = (err) => {
      const message = String(err?.message || err || "").toLowerCase();
      return (
        err?.code === 4001 ||
        err?.code === "ACTION_REJECTED" ||
        message.includes("user rejected") ||
        message.includes("rejected the transaction")
      );
    };

    const summarizeCompilationError = (rawError) => {
      const raw = String(rawError || "").trim();
      if (!raw) {
        return "Unknown compiler error.";
      }

      const cleaned = raw
        .split("\n")
        .map((line) => line.trim())
        .filter(Boolean)
        .filter((line) => !line.startsWith("Traceback"));

      const preferred =
        cleaned.find((line) => /ParserError|TypeError|DeclarationError|SyntaxError|CompilerError/i.test(line)) ||
        cleaned[0] ||
        raw;

      const compact = preferred.replace(/^ValueError:\s*/i, "").replace(/^Error:\s*/i, "");
      return compact.length > 220 ? `${compact.slice(0, 220)}...` : compact;
    };

    let deploymentStage = "compile";

    try {
      const response = await fetch("/api/deploy-contract", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          fileName: uploadedDeployFileName,
          source: uploadedDeploySource,
          contractName: inferredName,
          networkName: walletState.networkName,
        }),
      });

      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error || "Contract compilation failed");
      }

      if (payload.message) {
        addMessage("ai", payload.message, { markdown: true });
      }

      deploymentStage = "metamask";
      confirmDeployBtn.textContent = "Sending...";
      const deploymentResult = await deployCompiledContract({
        deployData: payload.deployData,
        constructorArgs,
        addMessage,
        onTransactionSent: ({ txHash, chainId, contractName }) => {
          createPendingTransactionCardAndWatch({
            txHash,
            chainId: chainId || walletState.chainId,
            kind: "deploy",
            title: `Deploy ${contractName || inferredName}`,
            subtitle: "Waiting for confirmation...",
            onSettled: async () => {
              await refreshWalletData().catch(() => {});
            },
          });
        },
      });

      await fetch("/api/register-deployed-contract", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          contractName: payload?.deployData?.contractName || inferredName,
          contractAddress: deploymentResult?.contractAddress,
          deployTxHash: deploymentResult?.txHash,
          networkName: payload?.deployData?.networkName || walletState.networkName,
          userAddress: walletState.account,
          fileName: payload?.deployData?.fileName || uploadedDeployFileName,
          constructorArgs,
          abi: payload?.deployData?.abi || [],
          bytecode: payload?.deployData?.bytecode || "",
        }),
      }).catch(() => {
        // Registry persistence should not block successful on-chain deployment.
      });

      await refreshWalletData().catch(() => {});
      closeDeployMenu();
    } catch (error) {
      const errorText = String(error?.message || error || "").toLowerCase();
      const isConstructorArgsProblem =
        errorText.includes("constructor") ||
        errorText.includes("missing argument") ||
        errorText.includes("too many arguments") ||
        errorText.includes("types/values length mismatch") ||
        errorText.includes("invalid arrayify value") ||
        errorText.includes("invalid tuple value") ||
        errorText.includes("cannot encode object for signature");

      closeDeployMenu();

      if (isConstructorArgsProblem) {
        addMessage(
          "ai",
          "Deployment canceled: invalid constructor parameters. Check argument order, types, and count."
        );
      } else if (deploymentStage === "compile") {
        addMessage("ai", `Compilation failed: ${summarizeCompilationError(error?.message || error)}`);
      } else if (isMetaMaskRejection(error)) {
        addMessage("ai", "Deployment canceled: you rejected the transaction in MetaMask.");
      } else {
        addMessage("ai", "Deployment failed after successful compilation. Please retry.");
      }
    }
  });

  if (confirmScanBtn) {
    confirmScanBtn.addEventListener("click", async () => {
      if (!uploadedScanFileName || !uploadedScanSource) {
        addMessage("ai", "Upload a Solidity file before scanning.");
        return;
      }

      confirmScanBtn.disabled = true;
      confirmScanBtn.textContent = "Scanning...";

      const inferredName = extractContractName(uploadedScanSource) || uploadedScanFileName.replace(/\.sol$/i, "");
      addMessage("user", `Scan contract ${inferredName} for vulnerabilities`);

      try {
        const response = await fetch("/api/scan-contract", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            fileName: uploadedScanFileName,
            source: uploadedScanSource,
            contractName: inferredName,
          }),
        });

        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload.error || "Scan failed");
        }

        addMessage("ai", payload.markdown || payload.message || "Scan completed.", { markdown: true });
        closeScanMenu();
      } catch (error) {
        closeScanMenu();
        addMessage("ai", `Scan error: ${error.message || error}`);
      } finally {
        if (confirmScanBtn) {
          confirmScanBtn.disabled = false;
          confirmScanBtn.textContent = "Start Auditing";
        }
      }
    });
  }
}

async function syncWalletStateToPrompt() {
  try {
    await fetch("/api/wallet-state", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ wallet: walletState }),
    });
  } catch {
    
  }
}

async function refreshWalletData() {
  const accounts = await window.ethereum.request({ method: "eth_accounts" });
  if (!accounts || accounts.length === 0) {
    walletState = { ...walletState, connected: false, account: null };
    walletStatus.textContent = "Wallet not connected";
    if (mmStatusIcon) mmStatusIcon.classList.add("dimmed");
    setChatEnabled(false);
    connectBtn.querySelector(".label").textContent = "Connect Wallet";
    await syncWalletStateToPrompt();
    return;
  }

  const account = accounts[0];
  const chainHex = await window.ethereum.request({ method: "eth_chainId" });
  const balanceHex = await window.ethereum.request({
    method: "eth_getBalance",
    params: [account, "latest"],
  });

  const chainId = Number.parseInt(chainHex, 16);
  const balanceWei = BigInt(balanceHex);
  const balanceEth = Number(balanceWei) / 1e18;

  walletState = {
    connected: true,
    account,
    chainId,
    networkName: getChainName(chainId),
    balanceEth: balanceEth.toFixed(6),
  };

  walletStatus.textContent = "Wallet connected";
  if (mmStatusIcon) mmStatusIcon.classList.remove("dimmed");
  setChatEnabled(true);
  connectBtn.querySelector(".label").textContent = "Disconnect Wallet";
  await syncWalletStateToPrompt();
}

async function connectWallet() {
  if (!window.ethereum) {
    addMessage("ai", "MetaMask extension not found.");
    infoPanelController.appendClientEvent({
      headline: "Wallet error",
      details: "MetaMask extension not found in browser",
      level: "error",
    });
    return;
  }

  if (walletState.connected) {
    walletState = {
      connected: false,
      account: null,
      chainId: null,
      networkName: null,
      balanceEth: null,
    };
    walletStatus.textContent = "Wallet disconnected";
    if (mmStatusIcon) mmStatusIcon.classList.add("dimmed");
    setChatEnabled(false);
    connectBtn.querySelector(".label").textContent = "Connect Wallet";
    await syncWalletStateToPrompt();
    addMessage("ai", "Wallet disconnected.");
    infoPanelController.appendClientEvent({
      headline: "Wallet disconnected",
      details: "User disconnected MetaMask from UI",
      level: "warn",
    });
    return;
  }

  try {
    connectBtn.querySelector(".label").textContent = "Connecting...";
    await window.ethereum.request({ method: "eth_requestAccounts" });
    await refreshWalletData();
    addMessage("ai", "MetaMask connected. Ask for anything blockchain-related.");
    infoPanelController.appendClientEvent({
      headline: "Wallet connected",
      details: `account=${shortAddress(walletState.account)} | chain=${walletState.networkName}`,
      level: "ok",
    });
  } catch (error) {
    addMessage("ai", `Error connecting wallet: ${error.message || error}`);
    infoPanelController.appendClientEvent({
      headline: "Wallet connection failed",
      details: String(error?.message || error || "Unknown wallet error"),
      level: "error",
    });
    connectBtn.querySelector(".label").textContent = "Connect Wallet";
  }
}

async function sendChatMessage() {
  const message = userInput.value.trim();
  if (!message) return;

  addMessage("user", message);
  userInput.value = "";
  setChatEnabled(false);

  const thinkingNode = document.createElement("div");
  thinkingNode.className = "message ai-message thinking-message";
  thinkingNode.textContent = "Thinking...";
  chatContainer.appendChild(thinkingNode);
  chatContainer.scrollTop = chatContainer.scrollHeight;

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, wallet: walletState }),
    });

    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Server error");
    }

    thinkingNode.remove();

    infoPanelController.appendRequestEvents({
      requestId: payload.requestId,
      events: payload.infoEvents,
    });

    const { replyText: txCleanReply, actions } = extractMetaMaskTxMarkers(payload.reply || "");
    const { replyText, level } = extractKnowledgeLevelMarker(txCleanReply);

    if (level !== null) {
      setKnowledgeLevel(level);
    }

    if (replyText) {
      addMessage("ai", replyText, {
        markdown: true,
      });
    } else if (!actions.length) {
      addMessage("ai", "No response from the agent.", {
        markdown: true,
      });
    }

    for (const action of actions) {
      await executeMetaMaskSendTransaction({
        actionPayload: action,
        walletState,
        addMessage,
        refreshWalletData,
      });
    }
  } catch (error) {
    thinkingNode.remove();
    addMessage("ai", `Chat error: ${error.message || error}`);
    infoPanelController.appendClientEvent({
      headline: "Chat request failed",
      details: String(error?.message || error || "Unknown chat error"),
      level: "error",
    });
  } finally {
    if (thinkingNode.isConnected) {
      thinkingNode.remove();
    }
    setChatEnabled(walletState.connected);
    if (walletState.connected) {
      userInput.focus();
    }
  }
}

connectBtn.addEventListener("click", connectWallet);
sendBtn.addEventListener("click", sendChatMessage);
userInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    sendChatMessage();
  }
});

if (window.ethereum) {
  window.ethereum.on("accountsChanged", async (accounts) => {
    const previousAccount = walletState.account;

    await refreshWalletData().catch(() => {});

    if (!accounts || accounts.length === 0) {
      if (previousAccount) {
        addMessage("ai", `🔄 Account changed from ${shortAddress(previousAccount)} to disconnected.`);
      }
      return;
    }

    const nextAccount = accounts[0];
    if (previousAccount && nextAccount && previousAccount.toLowerCase() !== nextAccount.toLowerCase()) {
      addMessage("ai", `🔄 Account changed from ${shortAddress(previousAccount)} to ${shortAddress(nextAccount)}.`);
    }
  });

  window.ethereum.on("chainChanged", async (chainIdHex) => {
    const previousChainId = walletState.chainId;
    const nextChainId = Number.parseInt(chainIdHex, 16);

    await refreshWalletData().catch(() => {});

    if (Number.isFinite(previousChainId) && Number.isFinite(nextChainId) && previousChainId !== nextChainId) {
      addMessage(
        "ai",
        `🌐 Chain changed from ${getChainName(previousChainId)} (${previousChainId}) to ${getChainName(nextChainId)} (${nextChainId}).`
      );
    }
  });
}

if (mmIconWrap && mmTooltip) {
  mmIconWrap.addEventListener("mouseenter", async () => {
    try {
      if (walletState.connected) {
        await refreshWalletData().catch(() => {});
        mmTooltip.innerHTML = renderWalletTooltip(walletState);
      } else {
        mmTooltip.textContent = "Wallet not connected";
      }
      mmTooltip.classList.remove("hidden");
    } catch {
      mmTooltip.textContent = "Wallet info unavailable";
      mmTooltip.classList.remove("hidden");
    }
  });

  mmIconWrap.addEventListener("mouseleave", () => {
    mmTooltip.classList.add("hidden");
  });
}

setChatEnabled(false);
setupDeployMenu();
syncKnowledgeLevelFromServer(setKnowledgeLevel);
