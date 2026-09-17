import sys
from pathlib import Path
from utils.tool_utils import resolve_chain, rpc_call_with_fallback

SRC_ROOT = Path(__file__).resolve().parents[2]
if str(SRC_ROOT) not in sys.path:
	sys.path.append(str(SRC_ROOT))

async def getGasPrice(chain: str = "ethereum") -> dict:
	"""Get current gas price from network RPC via eth_gasPrice."""
	try:
		normalized_chain, chain_data = resolve_chain(chain)
		if not chain_data:
			return {"error": f"Unknown network: {chain}", "source": "rpc"}

		gas_price_hex, last_error = rpc_call_with_fallback(
			chain_data["rpcUrls"],
			"eth_gasPrice",
			[],
			timeout=10,
		)

		if gas_price_hex is None:
			raise RuntimeError(f"All RPC endpoints failed: {last_error}")

		gas_price_wei = int(gas_price_hex, 16)
		gas_price_gwei = gas_price_wei / 1_000_000_000
		gas_price_native = gas_price_wei / 1_000_000_000_000_000_000

		return {
			"chain": normalized_chain,
			"gasPriceGwei": round(gas_price_gwei, 2),
			"gasPriceNative": gas_price_native,
			"nativeSymbol": chain_data["symbol"],
			"chainId": chain_data["chainId"],
			"source": "rpc",
		}
	except Exception as error:
		return {"error": f"getGasPrice error: {error}", "source": "rpc"}
