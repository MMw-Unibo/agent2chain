import sys
from pathlib import Path
from utils.tool_utils import fetch_etherscan_v2, resolve_chain

SRC_ROOT = Path(__file__).resolve().parents[2]
if str(SRC_ROOT) not in sys.path:
	sys.path.append(str(SRC_ROOT))

def _map_transaction(tx: dict, symbol: str, explorer_url: str | None) -> dict:
	tx_hash = tx.get("hash") or tx.get("transactionHash")
	value_wei_str = tx.get("value") or "0"
	try:
		value_native = int(value_wei_str) / 1_000_000_000_000_000_000
	except Exception:
		value_native = 0.0

	status = "success"
	if str(tx.get("isError", "0")) not in ("0", "", "None"):
		status = "failed"

	link = f"{explorer_url}/tx/{tx_hash}" if (explorer_url and tx_hash) else None

	return {
		"hash": tx_hash,
		"from": tx.get("from"),
		"to": tx.get("to") or tx.get("contractAddress") or "contract-creation",
		"value": value_native,
		"valueSymbol": symbol,
		"status": status,
		"timestamp": tx.get("timeStamp"),
		"explorerUrl": link,
	}


async def getTransactions(
	address: str,
	networkName: str = "ethereum",
	limit: int = 5,
) -> dict:
	"""Return latest transactions for an address using explorer APIs."""
	try:
		safe_limit = max(1, min(int(limit), 20))
		chain_key, chain_data = resolve_chain(networkName)
		if not chain_data:
			return {"error": f"Unknown network: {networkName}", "source": "etherscan-v2"}

		if not chain_data.get("apiUrl"):
			return {
				"error": f"Transaction history not supported on {chain_key}.",
				"source": "etherscan-v2",
			}

		normal_data = fetch_etherscan_v2(
			chain_data["chainId"],
			{
				"module": "account",
				"action": "txlist",
				"address": address,
				"startblock": "0",
				"endblock": "99999999",
				"page": "1",
				"offset": str(safe_limit),
				"sort": "desc",
			},
		)

		results = normal_data.get("result") if isinstance(normal_data.get("result"), list) else []
		source = "normal"

		if not results:
			internal_data = fetch_etherscan_v2(
				chain_data["chainId"],
				{
					"module": "account",
					"action": "txlistinternal",
					"address": address,
					"startblock": "0",
					"endblock": "99999999",
					"page": "1",
					"offset": str(safe_limit),
					"sort": "desc",
				},
			)
			if isinstance(internal_data.get("result"), list):
				results = internal_data["result"]
				source = "internal"

		if not results:
			return {
				"address": address,
				"network": chain_key,
				"count": 0,
				"transactions": [],
				"source": "etherscan-v2",
			}

		transactions = [
			_map_transaction(tx, chain_data["symbol"], chain_data.get("explorerUrl"))
			for tx in results[:safe_limit]
		]

		return {
			"address": address,
			"network": chain_key,
			"count": len(transactions),
			"mode": source,
			"transactions": transactions,
			"source": "etherscan-v2",
		}
	except Exception as error:
		return {"error": f"getTransactions error: {error}", "source": "etherscan-v2"}
