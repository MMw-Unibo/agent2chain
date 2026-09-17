import { createPendingTransactionCardAndWatch } from "./tx_cards.js";

function toHexWeiFromDecimal(value) {
  const input = String(value ?? "").trim();
  if (!/^\d+(\.\d+)?$/.test(input)) {
    throw new Error("Invalid amount format");
  }

  const [integerPartRaw, fractionalPartRaw = ""] = input.split(".");
  const integerPart = BigInt(integerPartRaw || "0");
  const fractionalPart = (fractionalPartRaw + "0".repeat(18)).slice(0, 18);
  const fractionalWei = BigInt(fractionalPart || "0");
  const wei = integerPart * (10n ** 18n) + fractionalWei;

  if (wei <= 0n) {
    throw new Error("Amount must be greater than zero");
  }

  return `0x${wei.toString(16)}`;
}

export function extractMetaMaskTxMarkers(rawReply) {
  const lines = String(rawReply || "").split("\n");
  const actions = [];
  const visibleLines = [];

  for (const line of lines) {
    if (!line.startsWith("__METAMASK_TX__")) {
      visibleLines.push(line);
      continue;
    }

    const payload = line.slice("__METAMASK_TX__".length).trim();
    if (!payload) {
      continue;
    }

    try {
      const parsed = JSON.parse(payload);
      if (parsed?.clientAction === "metamask_send_transaction" && parsed?.transactionData) {
        actions.push(parsed);
      }
    } catch {
      // Ignore malformed machine markers.
    }
  }

  return {
    replyText: visibleLines.join("\n").trim(),
    actions,
  };
}

async function ensureWalletChain(tx) {
  const chainIdHex = tx?.chainIdHex;
  const networkName = tx?.networkName;
  if (!chainIdHex) {
    return;
  }

  try {
    await window.ethereum.request({
      method: "wallet_switchEthereumChain",
      params: [{ chainId: chainIdHex }],
    });
  } catch (error) {
    if (error?.code === 4902) {
      const rpcUrls = Array.isArray(tx?.rpcUrls) ? tx.rpcUrls.filter(Boolean) : [];
      if (!rpcUrls.length) {
        throw new Error(
          `Network ${networkName || chainIdHex} is not configured in MetaMask, and no RPC URL was provided to add it.`
        );
      }

      await window.ethereum.request({
        method: "wallet_addEthereumChain",
        params: [
          {
            chainId: chainIdHex,
            chainName: tx?.chainName || networkName || `Chain ${chainIdHex}`,
            nativeCurrency: {
              name: tx?.symbol || "ETH",
              symbol: tx?.symbol || "ETH",
              decimals: 18,
            },
            rpcUrls,
            blockExplorerUrls: [],
          },
        ],
      });
      return;
    }
    throw error;
  }
}

export async function executeMetaMaskSendTransaction({
  actionPayload,
  walletState,
  addMessage,
  refreshWalletData,
}) {
  const tx = actionPayload?.transactionData || {};
  if (!walletState?.connected || !walletState?.account) {
    addMessage("ai", "Wallet not connected. Connect MetaMask and retry.");
    return;
  }

  const from = tx.from || walletState.account;
  const to = tx.to;
  const valueHex = tx.valueHex || (tx.amount ? toHexWeiFromDecimal(tx.amount) : "0x0");
  const data = tx.data;

  if (!to) {
    addMessage("ai", "Transaction data incomplete. Please retry your request.");
    return;
  }

  try {
    await ensureWalletChain(tx);

    addMessage("ai", "Opening MetaMask to confirm the transaction...");

    const txParams = {
      from,
      to,
      value: valueHex,
    };

    if (data) {
      txParams.data = data;
    }

    if (tx.gasEstimateHex) {
      txParams.gas = tx.gasEstimateHex;
    }
    if (tx.gasPriceWeiHex) {
      txParams.gasPrice = tx.gasPriceWeiHex;
    }

    const txHash = await window.ethereum.request({
      method: "eth_sendTransaction",
      params: [txParams],
    });

    const txChainId = tx.chainId
      ? Number(tx.chainId)
      : tx.chainIdHex
        ? Number.parseInt(String(tx.chainIdHex), 16)
        : walletState.chainId;

    const isContractInteraction = !!data && data !== "0x";
    createPendingTransactionCardAndWatch({
      txHash,
      chainId: txChainId,
      kind: isContractInteraction ? "contract" : "transfer",
      title: isContractInteraction ? "Contract interaction sent" : "Transaction sent",
      subtitle: "Waiting for confirmation...",
      rpcUrls: tx.rpcUrls,
      onSettled: async () => {
        await refreshWalletData().catch(() => {});
      },
    });

    addMessage("ai", `Transaction sent. Hash: ${txHash}`);
    await refreshWalletData().catch(() => {});
  } catch (error) {
    if (error?.code === 4001 || /user rejected/i.test(String(error?.message || ""))) {
      addMessage("ai", "Transaction rejected in MetaMask.");
      return;
    }
    addMessage("ai", `Transaction error: ${error.message || error}`);
  }
}
