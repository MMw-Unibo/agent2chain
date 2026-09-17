import os

SUPPORTED_CHAINS = {
	"ethereum-mainnet": {
		"chainId": 1,
		"symbol": "ETH",
		"rpcUrlTemplate": "https://mainnet.infura.io/v3/{INFURA_API_KEY}",
		"explorerUrl": "https://etherscan.io",
		"apiUrl": "https://api.etherscan.io/api",
		"fallbackRpcUrls": ["https://ethereum-rpc.publicnode.com", "https://cloudflare-eth.com"],
	},
	"ethereum-sepolia": {
		"chainId": 11155111,
		"symbol": "ETH",
		"rpcUrlTemplate": "https://sepolia.infura.io/v3/{INFURA_API_KEY}",
		"explorerUrl": "https://sepolia.etherscan.io",
		"apiUrl": "https://api-sepolia.etherscan.io/api",
		"fallbackRpcUrls": ["https://ethereum-sepolia-rpc.publicnode.com"],
	},
	"arbitrum-one": {
		"chainId": 42161,
		"symbol": "ETH",
		"rpcUrlTemplate": "https://arbitrum-mainnet.infura.io/v3/{INFURA_API_KEY}",
		"explorerUrl": "https://arbiscan.io",
		"apiUrl": "https://api.arbiscan.io/api",
		"fallbackRpcUrls": ["https://arbitrum-one-rpc.publicnode.com"],
	},
	"arbitrum-sepolia": {
		"chainId": 421614,
		"symbol": "ETH",
		"rpcUrlTemplate": "https://arbitrum-sepolia.infura.io/v3/{INFURA_API_KEY}",
		"explorerUrl": "https://sepolia.arbiscan.io",
		"apiUrl": "https://api-sepolia.arbiscan.io/api",
		"fallbackRpcUrls": ["https://arbitrum-sepolia-rpc.publicnode.com"],
	},
	"avalanche-c-chain": {
		"chainId": 43114,
		"symbol": "AVAX",
		"rpcUrl": "https://api.avax.network/ext/bc/C/rpc",
		"explorerUrl": "https://snowtrace.io",
		"apiUrl": "https://api.snowtrace.io/api",
	},
	"avalanche-fuji": {
		"chainId": 43113,
		"symbol": "AVAX",
		"rpcUrl": "https://api.avax-test.network/ext/bc/C/rpc",
		"explorerUrl": "https://testnet.snowtrace.io",
		"apiUrl": "https://api-testnet.snowtrace.io/api",
	},
	"base-mainnet": {
		"chainId": 8453,
		"symbol": "ETH",
		"rpcUrlTemplate": "https://base-mainnet.infura.io/v3/{INFURA_API_KEY}",
		"explorerUrl": "https://basescan.org",
		"apiUrl": "https://api.basescan.org/api",
		"fallbackRpcUrls": ["https://base-rpc.publicnode.com"],
	},
	"base-sepolia": {
		"chainId": 84532,
		"symbol": "ETH",
		"rpcUrlTemplate": "https://base-sepolia.infura.io/v3/{INFURA_API_KEY}",
		"explorerUrl": "https://sepolia.basescan.org",
		"apiUrl": "https://api-sepolia.basescan.org/api",
		"fallbackRpcUrls": ["https://base-sepolia-rpc.publicnode.com"],
	},
	"polygon-mainnet": {
		"chainId": 137,
		"symbol": "MATIC",
		"rpcUrlTemplate": "https://polygon-mainnet.infura.io/v3/{INFURA_API_KEY}",
		"explorerUrl": "https://polygonscan.com",
		"apiUrl": "https://api.polygonscan.com/api",
		"fallbackRpcUrls": ["https://polygon-rpc.com", "https://polygon-bor-rpc.publicnode.com"],
	},
	"polygon-amoy": {
		"chainId": 80002,
		"symbol": "MATIC",
		"rpcUrlTemplate": "https://polygon-amoy.infura.io/v3/{INFURA_API_KEY}",
		"explorerUrl": "https://amoy.polygonscan.com",
		"apiUrl": "https://api-amoy.polygonscan.com/api",
		"fallbackRpcUrls": ["https://rpc-amoy.polygon.technology"],
	},
	"optimism-mainnet": {
		"chainId": 10,
		"symbol": "ETH",
		"rpcUrlTemplate": "https://optimism-mainnet.infura.io/v3/{INFURA_API_KEY}",
		"explorerUrl": "https://optimistic.etherscan.io",
		"apiUrl": "https://api-optimistic.etherscan.io/api",
		"fallbackRpcUrls": ["https://optimism-rpc.publicnode.com"],
	},
	"optimism-sepolia": {
		"chainId": 11155420,
		"symbol": "ETH",
		"rpcUrlTemplate": "https://optimism-sepolia.infura.io/v3/{INFURA_API_KEY}",
		"explorerUrl": "https://sepolia-optimistic.etherscan.io",
		"apiUrl": "https://api-sepolia-optimistic.etherscan.io/api",
		"fallbackRpcUrls": ["https://optimism-sepolia-rpc.publicnode.com"],
	},
	"bsc-mainnet": {
		"chainId": 56,
		"symbol": "BNB",
		"rpcUrl": "https://bsc-dataseed.binance.org",
		"explorerUrl": "https://bscscan.com",
		"apiUrl": "https://api.bscscan.com/api",
	},
	"bsc-testnet": {
		"chainId": 97,
		"symbol": "tBNB",
		"rpcUrl": "https://data-seed-prebsc-1-s1.binance.org:8545",
		"explorerUrl": "https://testnet.bscscan.com",
		"apiUrl": "https://api-testnet.bscscan.com/api",
	},
	"ganache": {
		"chainId": 1337,
		"symbol": "ETH",
		"rpcUrl": "http://127.0.0.1:7545",
		"explorerUrl": None,
		"apiUrl": None,
	},
	"ganache-legacy": {
		"chainId": 5777,
		"symbol": "ETH",
		"rpcUrl": "http://127.0.0.1:7545",
		"explorerUrl": None,
		"apiUrl": None,
	},
}


CHAIN_ALIASES = {
	"ethereum": "ethereum-mainnet",
	"sepolia": "ethereum-sepolia",
	"arbitrum": "arbitrum-one",
	"avalanche": "avalanche-c-chain",
	"base": "base-mainnet",
	"polygon": "polygon-mainnet",
	"optimism": "optimism-mainnet",
	"bsc": "bsc-mainnet",
	"ganache-local": "ganache",
	"local-ganache": "ganache",
	"chain-1337": "ganache",
	"chain-5777": "ganache-legacy",
}


def resolve_chain(network_name: str):
	normalized = network_name.strip().lower()
	chain_key = CHAIN_ALIASES.get(normalized, normalized)
	chain = SUPPORTED_CHAINS.get(chain_key)
	if not chain:
		return None, None

	rpc_urls = []
	infura_key = os.getenv("INFURA_API_KEY")

	if "rpcUrlTemplate" in chain and infura_key:
		rpc_urls.append(chain["rpcUrlTemplate"].format(INFURA_API_KEY=infura_key))

	if "rpcUrl" in chain:
		rpc_urls.append(chain["rpcUrl"])

	rpc_urls.extend(chain.get("fallbackRpcUrls", []))

	override_env_key = f"{chain_key.upper().replace('-', '_')}_RPC_URL"
	override_rpc = os.getenv(override_env_key)
	if override_rpc:
		rpc_urls = [override_rpc] + rpc_urls

	deduped_rpc_urls = []
	for url in rpc_urls:
		if url and url not in deduped_rpc_urls:
			deduped_rpc_urls.append(url)

	resolved_chain = {**chain, "rpcUrls": deduped_rpc_urls}
	return chain_key, resolved_chain
