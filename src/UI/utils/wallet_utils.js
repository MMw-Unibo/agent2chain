import { getChainName } from "./chains.js";

export function shortAddress(address) {
  if (!address || address.length < 10) return address || "unknown";
  return `${address.slice(0, 6)}...${address.slice(-4)}`;
}

export function renderWalletTooltip(info) {
  if (!info || !info.connected || !info.account) {
    return "Wallet not connected";
  }

  const accountShort = `${info.account.slice(0, 6)}...${info.account.slice(-4)}`;
  const chainName = info.networkName || getChainName(info.chainId);
  return `
    <div><span class="label">Account:</span> <code>${accountShort}</code></div>
    <div><span class="label">Balance:</span> ${info.balanceEth} ETH</div>
    <div><span class="label">Network:</span> ${chainName} (Chain ID: ${info.chainId})</div>
  `;
}
