export const CHAIN_INFO_BY_ID = {
  1: {
    name: "ethereum",
    explorerUrl: "https://etherscan.io",
  },
  10: {
    name: "optimism",
    explorerUrl: "https://optimistic.etherscan.io",
  },
  56: {
    name: "bsc",
    explorerUrl: "https://bscscan.com",
  },
  137: {
    name: "polygon",
    explorerUrl: "https://polygonscan.com",
  },
  42161: {
    name: "arbitrum one",
    explorerUrl: "https://arbiscan.io",
  },
  43114: {
    name: "avalanche",
    explorerUrl: "https://snowtrace.io",
  },
  8453: {
    name: "base",
    explorerUrl: "https://basescan.org",
  },
  11155111: {
    name: "sepolia",
    explorerUrl: "https://sepolia.etherscan.io",
  },
  1337: {
    name: "ganache",
    explorerUrl: "",
  },
  5777: {
    name: "ganache-legacy",
    explorerUrl: "",
  },
};

export const CHAIN_NAMES = Object.fromEntries(
  Object.entries(CHAIN_INFO_BY_ID).map(([chainId, info]) => [chainId, info.name])
);

export function getChainInfoById(chainId) {
  return CHAIN_INFO_BY_ID[Number(chainId)] || null;
}

export function getChainName(chainId) {
  return CHAIN_NAMES[chainId] || `chain-${chainId}`;
}
