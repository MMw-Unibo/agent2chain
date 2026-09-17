import re
import sys
from pathlib import Path
from utils.tool_utils import resolve_chain, rpc_call_with_fallback

TX_HASH_RE = re.compile(r"^0x([A-Fa-f0-9]{64})$")

SRC_ROOT = Path(__file__).resolve().parents[2]
if str(SRC_ROOT) not in sys.path:
	sys.path.append(str(SRC_ROOT))

async def getTransactionDetails(hash: str, networkName: str = "ethereum") -> dict:
	"""Get transaction details from the specified blockchain network."""
	try:
		if not hash or not TX_HASH_RE.match(hash):
			return {"error": "Invalid or missing transaction hash.", "source": "rpc"}

		chain_key, chain_data = resolve_chain(networkName)
		if not chain_data:
			return {"error": f"Unknown network: {networkName}", "source": "rpc"}

		tx, last_error = rpc_call_with_fallback(
			chain_data["rpcUrls"],
			"eth_getTransactionByHash",
			[hash],
			timeout=12,
		)

		receipt = None
		if tx:
			receipt, _ = rpc_call_with_fallback(
				chain_data["rpcUrls"],
				"eth_getTransactionReceipt",
				[hash],
				timeout=12,
			)

		if tx is None and last_error is not None:
			return {"error": f"RPC error: {last_error}", "source": "rpc"}

		if not tx:
			return {
				"error": f"No transaction found with hash {hash} on {chain_key}",
				"source": "rpc",
			}

		value_wei = int(tx.get("value", "0x0"), 16)
		gas_price_wei = int(tx.get("gasPrice", "0x0"), 16) if tx.get("gasPrice") else None
		gas_limit = int(tx.get("gas", "0x0"), 16) if tx.get("gas") else None
		gas_used = int(receipt.get("gasUsed", "0x0"), 16) if receipt and receipt.get("gasUsed") else None
		block_number = int(tx.get("blockNumber", "0x0"), 16) if tx.get("blockNumber") else None

		status = "pending"
		if receipt and receipt.get("status") is not None:
			status = "success" if int(receipt["status"], 16) == 1 else "failed"

		return {
			"network": chain_key,
			"txHash": tx.get("hash"),
			"from": tx.get("from"),
			"to": tx.get("to") or "contract-creation",
			"value": value_wei / 1_000_000_000_000_000_000,
			"valueSymbol": chain_data["symbol"],
			"gasPriceGwei": (gas_price_wei / 1_000_000_000) if gas_price_wei is not None else None,
			"gasLimit": gas_limit,
			"gasUsed": gas_used,
			"blockNumber": block_number,
			"status": status,
			"explorerUrl": (
				f"{chain_data['explorerUrl']}/tx/{tx.get('hash')}" if chain_data.get("explorerUrl") else None
			),
			"source": "rpc",
		}
	except Exception as error:
		return {"error": f"getTransactionDetails error: {error}", "source": "rpc"}
