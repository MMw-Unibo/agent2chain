from urllib.parse import quote

from utils.tool_utils import fetch_json_url, parse_csv_values, resolve_asset_id

async def getPrice(symbol: str, currency: str = "usd,eur") -> dict:
	"""Get current crypto price from CoinGecko in one or more fiat currencies."""
	try:
		crypto_id, original_input = resolve_asset_id(symbol, default_asset="ethereum")
		currencies = parse_csv_values(currency, default_values=["usd", "eur"])

		if not currencies:
			return {
				"error": "No valid currency found in input.",
				"source": "coingecko",
			}

		url = (
			"https://api.coingecko.com/api/v3/simple/price"
			f"?ids={quote(crypto_id)}&vs_currencies={quote(','.join(currencies))}"
		)

		payload = fetch_json_url(url, timeout=10)

		crypto_prices = payload.get(crypto_id)
		if not crypto_prices:
			return {
				"error": f"Unsupported cryptocurrency: {original_input}",
				"source": "coingecko",
			}

		prices = {
			currency_code: crypto_prices[currency_code]
			for currency_code in currencies
			if currency_code in crypto_prices
		}

		if not prices:
			return {
				"error": "No valid currency found for this request.",
				"source": "coingecko",
			}

		return {
			"crypto": crypto_id,
			"prices": prices,
			"source": "coingecko",
		}
	except Exception as error:
		return {
			"error": f"getPrice error: {error}",
			"source": "coingecko",
		}
