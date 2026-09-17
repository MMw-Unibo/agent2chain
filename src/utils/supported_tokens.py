"""DeFi support map for chain/protocol/token/operation routing.

This module is intentionally designed as a central registry extendable
with new chains, protocols, tokens, and operations as needed.
"""

from __future__ import annotations

from typing import Any

from utils.supported_chains import resolve_chain


DEFI_OPERATION_CATALOG: dict[str, dict[str, Any]] = {
    "stake": {
        "label": "Stake",
        "kind": "staking",
        "requiresApproval": False,
        "defaultRisk": "medium",
    },
    "deposit": {
        "label": "Deposit",
        "kind": "lending",
        "requiresApproval": True,
        "defaultRisk": "medium",
    },
    "lend": {
        "label": "Lend",
        "kind": "lending",
        "requiresApproval": True,
        "defaultRisk": "medium",
    },
    "borrow": {
        "label": "Borrow",
        "kind": "lending",
        "requiresApproval": False,
        "defaultRisk": "high",
    },
    "repay": {
        "label": "Repay",
        "kind": "lending",
        "requiresApproval": True,
        "defaultRisk": "medium",
    },
    "withdraw": {
        "label": "Withdraw",
        "kind": "lending",
        "requiresApproval": False,
        "defaultRisk": "medium",
    },
    "claim-rewards": {
        "label": "Claim Rewards",
        "kind": "staking",
        "requiresApproval": False,
        "defaultRisk": "low",
    },
}


# Chain -> Protocol -> Config
# Structure:
# {
#   <chain_key>: {
#     "protocols": {
#       <protocol_id>: {
#         "displayName": str,
#         "category": str,
#         "docsUrl": str | None,
#         "contracts": {<ref>: <address or None>},
#         "operations": {
#            <operation>: {
#              "contractRef": <contracts key>,
#              "method": <abi method signature>,
#              "approvalTargetRef": <contracts key or None>,
#              "notes": str,
#            }
#         },
#         "tokens": {
#            <symbol>: {
#              "address": str | None,
#              "decimals": int | None,
#              "isNative": bool,
#              "operations": [<operation>, ...],
#              "notes": str | None,
#            }
#         }
#       }
#     }
#   }
# }
SUPPORTED_DEFI_ASSETS: dict[str, dict[str, Any]] = {
    "ethereum-mainnet": {
        "protocols": {
            "aave-v3": {
                "displayName": "Aave V3",
                "category": "lending",
                "docsUrl": "https://docs.aave.com/",
                "contracts": {
                    "pool": "0x87870Bca3F3fD6335C3f4ce8392D69350B4fA4E2",
                    "poolDataProvider": None,
                    "wrappedNativeGateway": None,
                },
                "operations": {
                    "deposit": {
                        "contractRef": "pool",
                        "method": "supply(address,uint256,address,uint16)",
                        "approvalTargetRef": "pool",
                        "notes": "For ERC20 assets.",
                    },
                    "borrow": {
                        "contractRef": "pool",
                        "method": "borrow(address,uint256,uint256,uint16,address)",
                        "approvalTargetRef": None,
                        "notes": "Requires collateral health-factor checks.",
                    },
                    "repay": {
                        "contractRef": "pool",
                        "method": "repay(address,uint256,uint256,address)",
                        "approvalTargetRef": "pool",
                        "notes": "Repay variable/stable debt depending on rate mode.",
                    },
                    "withdraw": {
                        "contractRef": "pool",
                        "method": "withdraw(address,uint256,address)",
                        "approvalTargetRef": None,
                        "notes": "Withdraw supplied collateral.",
                    },
                },
                "tokens": {
                    "WETH": {
                        "address": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
                        "decimals": 18,
                        "isNative": False,
                        "operations": ["deposit", "borrow", "repay", "withdraw"],
                        "notes": None,
                    },
                    "USDC": {
                        "address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                        "decimals": 6,
                        "isNative": False,
                        "operations": ["deposit", "borrow", "repay", "withdraw"],
                        "notes": None,
                    },
                    "DAI": {
                        "address": "0x6B175474E89094C44Da98b954EedeAC495271d0F",
                        "decimals": 18,
                        "isNative": False,
                        "operations": ["deposit", "borrow", "repay", "withdraw"],
                        "notes": None,
                    },
                },
            },
            "lido": {
                "displayName": "Lido",
                "category": "staking",
                "docsUrl": "https://docs.lido.fi/",
                "contracts": {
                    "steth": "0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84",
                },
                "operations": {
                    "stake": {
                        "contractRef": "steth",
                        "method": "submit(address)",
                        "approvalTargetRef": None,
                        "notes": "ETH staking via payable submit().",
                    },
                },
                "tokens": {
                    "ETH": {
                        "address": None,
                        "decimals": 18,
                        "isNative": True,
                        "operations": ["stake"],
                        "notes": "Native ETH input for staking.",
                    },
                },
            },
            "compound-v3": {
                "displayName": "Compound V3",
                "category": "lending",
                "docsUrl": "https://docs.compound.finance/",
                "contracts": {
                    "comet-usdc": "0xc3d688B66703497DAA19211EEdff47f25384cdc3",
                },
                "operations": {
                    "deposit": {
                        "contractRef": "comet-usdc",
                        "method": "supply(address,uint256)",
                        "approvalTargetRef": "comet-usdc",
                        "notes": "Supply supported collateral/base asset.",
                    },
                    "borrow": {
                        "contractRef": "comet-usdc",
                        "method": "withdraw(address,uint256)",
                        "approvalTargetRef": None,
                        "notes": "Borrow base asset by withdrawing from account liquidity.",
                    },
                    "repay": {
                        "contractRef": "comet-usdc",
                        "method": "supply(address,uint256)",
                        "approvalTargetRef": "comet-usdc",
                        "notes": "Repay debt by supplying base asset.",
                    },
                    "withdraw": {
                        "contractRef": "comet-usdc",
                        "method": "withdraw(address,uint256)",
                        "approvalTargetRef": None,
                        "notes": "Withdraw supplied collateral.",
                    },
                },
                "tokens": {
                    "USDC": {
                        "address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                        "decimals": 6,
                        "isNative": False,
                        "operations": ["deposit", "borrow", "repay", "withdraw"],
                        "notes": "Main base market token.",
                    },
                },
            },
        }
    },
    "ethereum-sepolia": {
        "protocols": {
            "aave-v3": {
                "displayName": "Aave V3",
                "category": "lending",
                "docsUrl": "https://docs.aave.com/",
                "contracts": {
                    "pool": "0x6Ae43d3271ff6888e7Fc43Fd7321a503ff738951",
                    "poolDataProvider": "0x3e9708d80f7B3e43118013075F7e95CE3AB31F31",
                    "wrappedNativeGateway": "0x387d311e47e80b498169e6fb51d3193167d89F7D",
                },
                "operations": {
                    "deposit": {
                        "contractRef": "pool",
                        "method": "supply(address,uint256,address,uint16)",
                        "approvalTargetRef": "pool",
                        "notes": "Sepolia test market via Aave V3 pool.",
                    },
                    "borrow": {
                        "contractRef": "pool",
                        "method": "borrow(address,uint256,uint256,uint16,address)",
                        "approvalTargetRef": None,
                        "notes": "Sepolia test market via Aave V3 pool.",
                    },
                    "repay": {
                        "contractRef": "pool",
                        "method": "repay(address,uint256,uint256,address)",
                        "approvalTargetRef": "pool",
                        "notes": "Sepolia test market via Aave V3 pool.",
                    },
                    "withdraw": {
                        "contractRef": "pool",
                        "method": "withdraw(address,uint256,address)",
                        "approvalTargetRef": None,
                        "notes": "Sepolia test market via Aave V3 pool.",
                    },
                },
                "tokens": {
                    "WETH": {
                        "address": "0xC558DBdd856501FCd9aaF1E62eae57A9F0629a3c",
                        "decimals": 18,
                        "isNative": False,
                        "operations": ["deposit", "borrow", "repay", "withdraw"],
                        "notes": "Aave V3 Sepolia WETH underlying.",
                    },
                    "USDC": {
                        "address": "0x94a9D9AC8a22534E3FaCa9F4e7F2E2cf85d5E4C8",
                        "decimals": 6,
                        "isNative": False,
                        "operations": ["deposit", "borrow", "repay", "withdraw"],
                        "notes": "Aave V3 Sepolia USDC underlying.",
                    },
                    "DAI": {
                        "address": "0xFF34B3d4Aee8ddCd6F9AFFFB6Fe49bD371b8a357",
                        "decimals": 18,
                        "isNative": False,
                        "operations": ["deposit", "borrow", "repay", "withdraw"],
                        "notes": "Aave V3 Sepolia DAI underlying.",
                    },
                },
            },
            "local-defi": {
                "displayName": "Sepolia Custom DeFi",
                "category": "sandbox",
                "docsUrl": None,
                "contracts": {
                    "defiRouter": None,
                    "stakingVault": None,
                },
                "operations": {
                    "stake": {
                        "contractRef": "defiRouter",
                        "method": "stake(address,uint256)",
                        "approvalTargetRef": "defiRouter",
                        "notes": "Use this for your own deployed test contracts.",
                    },
                    "deposit": {
                        "contractRef": "defiRouter",
                        "method": "deposit(address,uint256)",
                        "approvalTargetRef": "defiRouter",
                        "notes": "Use this for your own deployed test contracts.",
                    },
                    "lend": {
                        "contractRef": "defiRouter",
                        "method": "lend(address,uint256)",
                        "approvalTargetRef": "defiRouter",
                        "notes": "Use this for your own deployed test contracts.",
                    },
                    "borrow": {
                        "contractRef": "defiRouter",
                        "method": "borrow(address,uint256)",
                        "approvalTargetRef": None,
                        "notes": "Use this for your own deployed test contracts.",
                    },
                    "claim-rewards": {
                        "contractRef": "stakingVault",
                        "method": "harvestTokenRewards(address)",
                        "approvalTargetRef": None,
                        "notes": "Harvest staking rewards accrued for the selected ERC20 token.",
                    },
                },
                "tokens": {
                    "ETH": {
                        "address": None,
                        "decimals": 18,
                        "isNative": True,
                        "operations": ["stake", "deposit"],
                        "notes": "Native Sepolia ETH.",
                    },
                    "TKA": {
                        "address": None,
                        "decimals": 18,
                        "isNative": False,
                        "operations": ["stake", "deposit", "lend", "borrow", "claim-rewards"],
                        "notes": "Set your custom Sepolia ERC20 test token address.",
                    },
                },
            },
        }
    },
    "arbitrum-one": {
        "protocols": {
            "aave-v3": {
                "displayName": "Aave V3",
                "category": "lending",
                "docsUrl": "https://docs.aave.com/",
                "contracts": {
                    "pool": "0x794a61358D6845594F94dc1DB02A252b5b4814aD",
                    "poolDataProvider": None,
                    "wrappedNativeGateway": None,
                },
                "operations": {
                    "deposit": {
                        "contractRef": "pool",
                        "method": "supply(address,uint256,address,uint16)",
                        "approvalTargetRef": "pool",
                        "notes": None,
                    },
                    "borrow": {
                        "contractRef": "pool",
                        "method": "borrow(address,uint256,uint256,uint16,address)",
                        "approvalTargetRef": None,
                        "notes": None,
                    },
                    "repay": {
                        "contractRef": "pool",
                        "method": "repay(address,uint256,uint256,address)",
                        "approvalTargetRef": "pool",
                        "notes": None,
                    },
                    "withdraw": {
                        "contractRef": "pool",
                        "method": "withdraw(address,uint256,address)",
                        "approvalTargetRef": None,
                        "notes": None,
                    },
                },
                "tokens": {
                    "USDC": {
                        "address": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
                        "decimals": 6,
                        "isNative": False,
                        "operations": ["deposit", "borrow", "repay", "withdraw"],
                        "notes": None,
                    },
                    "WETH": {
                        "address": "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
                        "decimals": 18,
                        "isNative": False,
                        "operations": ["deposit", "borrow", "repay", "withdraw"],
                        "notes": None,
                    },
                },
            }
        }
    },
    "polygon-mainnet": {
        "protocols": {
            "aave-v3": {
                "displayName": "Aave V3",
                "category": "lending",
                "docsUrl": "https://docs.aave.com/",
                "contracts": {
                    "pool": "0x794a61358D6845594F94dc1DB02A252b5b4814aD",
                    "poolDataProvider": None,
                    "wrappedNativeGateway": None,
                },
                "operations": {
                    "deposit": {
                        "contractRef": "pool",
                        "method": "supply(address,uint256,address,uint16)",
                        "approvalTargetRef": "pool",
                        "notes": None,
                    },
                    "borrow": {
                        "contractRef": "pool",
                        "method": "borrow(address,uint256,uint256,uint16,address)",
                        "approvalTargetRef": None,
                        "notes": None,
                    },
                    "repay": {
                        "contractRef": "pool",
                        "method": "repay(address,uint256,uint256,address)",
                        "approvalTargetRef": "pool",
                        "notes": None,
                    },
                    "withdraw": {
                        "contractRef": "pool",
                        "method": "withdraw(address,uint256,address)",
                        "approvalTargetRef": None,
                        "notes": None,
                    },
                },
                "tokens": {
                    "USDC": {
                        "address": "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",
                        "decimals": 6,
                        "isNative": False,
                        "operations": ["deposit", "borrow", "repay", "withdraw"],
                        "notes": None,
                    },
                    "WMATIC": {
                        "address": "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270",
                        "decimals": 18,
                        "isNative": False,
                        "operations": ["deposit", "borrow", "repay", "withdraw"],
                        "notes": None,
                    },
                },
            }
        }
    },
    "optimism-mainnet": {
        "protocols": {
            "aave-v3": {
                "displayName": "Aave V3",
                "category": "lending",
                "docsUrl": "https://docs.aave.com/",
                "contracts": {
                    "pool": "0x794a61358D6845594F94dc1DB02A252b5b4814aD",
                    "poolDataProvider": None,
                    "wrappedNativeGateway": None,
                },
                "operations": {
                    "deposit": {
                        "contractRef": "pool",
                        "method": "supply(address,uint256,address,uint16)",
                        "approvalTargetRef": "pool",
                        "notes": None,
                    },
                    "borrow": {
                        "contractRef": "pool",
                        "method": "borrow(address,uint256,uint256,uint16,address)",
                        "approvalTargetRef": None,
                        "notes": None,
                    },
                    "repay": {
                        "contractRef": "pool",
                        "method": "repay(address,uint256,uint256,address)",
                        "approvalTargetRef": "pool",
                        "notes": None,
                    },
                    "withdraw": {
                        "contractRef": "pool",
                        "method": "withdraw(address,uint256,address)",
                        "approvalTargetRef": None,
                        "notes": None,
                    },
                },
                "tokens": {
                    "USDC": {
                        "address": None,
                        "decimals": 6,
                        "isNative": False,
                        "operations": ["deposit", "borrow", "repay", "withdraw"],
                        "notes": "Set canonical OP USDC address before enabling.",
                    },
                },
            }
        }
    },
    "base-mainnet": {
        "protocols": {
            "aave-v3": {
                "displayName": "Aave V3",
                "category": "lending",
                "docsUrl": "https://docs.aave.com/",
                "contracts": {
                    "pool": None,
                    "poolDataProvider": None,
                    "wrappedNativeGateway": None,
                },
                "operations": {
                    "deposit": {
                        "contractRef": "pool",
                        "method": "supply(address,uint256,address,uint16)",
                        "approvalTargetRef": "pool",
                        "notes": "Fill addresses before enabling.",
                    },
                    "borrow": {
                        "contractRef": "pool",
                        "method": "borrow(address,uint256,uint256,uint16,address)",
                        "approvalTargetRef": None,
                        "notes": "Fill addresses before enabling.",
                    },
                    "repay": {
                        "contractRef": "pool",
                        "method": "repay(address,uint256,uint256,address)",
                        "approvalTargetRef": "pool",
                        "notes": "Fill addresses before enabling.",
                    },
                    "withdraw": {
                        "contractRef": "pool",
                        "method": "withdraw(address,uint256,address)",
                        "approvalTargetRef": None,
                        "notes": "Fill addresses before enabling.",
                    },
                },
                "tokens": {
                    "USDC": {
                        "address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
                        "decimals": 6,
                        "isNative": False,
                        "operations": ["deposit", "borrow", "repay", "withdraw"],
                        "notes": None,
                    },
                    "WETH": {
                        "address": "0x4200000000000000000000000000000000000006",
                        "decimals": 18,
                        "isNative": False,
                        "operations": ["deposit", "borrow", "repay", "withdraw"],
                        "notes": None,
                    },
                },
            }
        }
    },
    "avalanche-c-chain": {
        "protocols": {
            "aave-v3": {
                "displayName": "Aave V3",
                "category": "lending",
                "docsUrl": "https://docs.aave.com/",
                "contracts": {
                    "pool": None,
                    "poolDataProvider": None,
                    "wrappedNativeGateway": None,
                },
                "operations": {
                    "deposit": {
                        "contractRef": "pool",
                        "method": "supply(address,uint256,address,uint16)",
                        "approvalTargetRef": "pool",
                        "notes": "Fill addresses before enabling.",
                    },
                    "borrow": {
                        "contractRef": "pool",
                        "method": "borrow(address,uint256,uint256,uint16,address)",
                        "approvalTargetRef": None,
                        "notes": "Fill addresses before enabling.",
                    },
                    "repay": {
                        "contractRef": "pool",
                        "method": "repay(address,uint256,uint256,address)",
                        "approvalTargetRef": "pool",
                        "notes": "Fill addresses before enabling.",
                    },
                    "withdraw": {
                        "contractRef": "pool",
                        "method": "withdraw(address,uint256,address)",
                        "approvalTargetRef": None,
                        "notes": "Fill addresses before enabling.",
                    },
                },
                "tokens": {
                    "WAVAX": {
                        "address": "0xB31f66AA3C1e785363F0875A1B74E27b85FD66c7",
                        "decimals": 18,
                        "isNative": False,
                        "operations": ["deposit", "borrow", "repay", "withdraw"],
                        "notes": None,
                    },
                    "USDC": {
                        "address": None,
                        "decimals": 6,
                        "isNative": False,
                        "operations": ["deposit", "borrow", "repay", "withdraw"],
                        "notes": "Set preferred AVAX USDC address variant.",
                    },
                },
            }
        }
    },
    "bsc-mainnet": {
        "protocols": {
            "venus": {
                "displayName": "Venus",
                "category": "lending",
                "docsUrl": "https://docs.venus.io/",
                "contracts": {
                    "comptroller": None,
                    "vbnb": None,
                    "vusdc": None,
                },
                "operations": {
                    "deposit": {
                        "contractRef": "vusdc",
                        "method": "mint(uint256)",
                        "approvalTargetRef": "vusdc",
                        "notes": "For ERC20 markets; native BNB uses payable mint().",
                    },
                    "borrow": {
                        "contractRef": "vusdc",
                        "method": "borrow(uint256)",
                        "approvalTargetRef": None,
                        "notes": "Requires collateral and market entry.",
                    },
                    "repay": {
                        "contractRef": "vusdc",
                        "method": "repayBorrow(uint256)",
                        "approvalTargetRef": "vusdc",
                        "notes": None,
                    },
                    "withdraw": {
                        "contractRef": "vusdc",
                        "method": "redeemUnderlying(uint256)",
                        "approvalTargetRef": None,
                        "notes": None,
                    },
                },
                "tokens": {
                    "USDC": {
                        "address": "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d",
                        "decimals": 18,
                        "isNative": False,
                        "operations": ["deposit", "borrow", "repay", "withdraw"],
                        "notes": "Verify decimal precision in your chosen Venus market.",
                    },
                    "BNB": {
                        "address": None,
                        "decimals": 18,
                        "isNative": True,
                        "operations": ["deposit", "repay"],
                        "notes": "Handled through vBNB payable methods.",
                    },
                },
            }
        }
    },
    "ganache": {
        "protocols": {
            "local-defi": {
                "displayName": "Local DeFi Test Suite",
                "category": "sandbox",
                "docsUrl": None,
                "contracts": {
                    "defiRouter": "0xBEFAcba04d2edA4917D81B174673BD5f805C0a59",
                    "stakingVault": "0x614bdEc6A6a81ed61C9f7bBa56944f111cFa8379",
                    "lendingPool": "0xDB9496Bb3c76a5BC80bA76D43dCEa5842F25BB8D",
                    "priceOracle": "0x879bd3D1fe57D8fE2Ff924ca7CBdcAA23DE5882B",
                },
                "operations": {
                    "stake": {
                        "contractRef": "defiRouter",
                        "method": "stake(address,uint256)",
                        "approvalTargetRef": "defiRouter",
                        "notes": "Routes to LocalStakingVault (ERC20 or native if token=address(0)).",
                    },
                    "deposit": {
                        "contractRef": "defiRouter",
                        "method": "deposit(address,uint256)",
                        "approvalTargetRef": "defiRouter",
                        "notes": "Routes collateral deposit to LocalLendingPool.",
                    },
                    "lend": {
                        "contractRef": "defiRouter",
                        "method": "lend(address,uint256)",
                        "approvalTargetRef": "defiRouter",
                        "notes": "Routes liquidity provision to LocalLendingPool borrow side.",
                    },
                    "borrow": {
                        "contractRef": "defiRouter",
                        "method": "borrow(address,uint256)",
                        "approvalTargetRef": None,
                        "notes": "Borrows borrowToken from LocalLendingPool against deposited collateral.",
                    },
                    "claim-rewards": {
                        "contractRef": "stakingVault",
                        "method": "harvestTokenRewards(address)",
                        "approvalTargetRef": None,
                        "notes": "Harvest staking rewards accrued for the selected ERC20 token.",
                    },
                },
                "tokens": {
                    "TKA": {
                        "address": "0x581Ea417b37248f5FEaef81C229585E6722FDb04",
                        "decimals": 18,
                        "isNative": False,
                        "operations": ["stake", "deposit", "claim-rewards"],
                        "notes": "Local collateral/staking token (MockERC20).",
                    },
                    "TKB": {
                        "address": "0x2d147486513F8fe4197cf84D37d9e8e803381a31",
                        "decimals": 18,
                        "isNative": False,
                        "operations": ["lend", "borrow"],
                        "notes": "Local borrow-side liquidity token (MockERC20).",
                    },
                },
            }
        }
    },
}


PROTOCOL_ALIASES: dict[str, str] = {
    "aave": "aave-v3",
    "aavev3": "aave-v3",
    "compound": "compound-v3",
    "compoundv3": "compound-v3",
    "local": "local-defi",
}


def _normalize_key(value: str) -> str:
    return str(value or "").strip().lower().replace("_", "-").replace(" ", "-")


def resolve_defi_chain(network_name: str) -> str | None:
    chain_key, _ = resolve_chain(network_name)
    if chain_key and chain_key in SUPPORTED_DEFI_ASSETS:
        return chain_key
    return None


def resolve_protocol_id(protocol_name: str) -> str:
    normalized = _normalize_key(protocol_name)
    return PROTOCOL_ALIASES.get(normalized, normalized)


def get_chain_protocols(network_name: str) -> dict[str, dict[str, Any]]:
    chain_key = resolve_defi_chain(network_name)
    if not chain_key:
        return {}
    return SUPPORTED_DEFI_ASSETS.get(chain_key, {}).get("protocols", {})


def list_supported_protocols(network_name: str) -> list[str]:
    return sorted(get_chain_protocols(network_name).keys())


def list_supported_tokens(network_name: str, protocol_name: str | None = None) -> dict[str, Any]:
    protocols = get_chain_protocols(network_name)
    if not protocols:
        return {}

    if protocol_name:
        pid = resolve_protocol_id(protocol_name)
        protocol = protocols.get(pid)
        if not protocol:
            return {}
        return protocol.get("tokens", {})

    merged: dict[str, Any] = {}
    for protocol in protocols.values():
        for symbol, token_data in (protocol.get("tokens") or {}).items():
            merged.setdefault(symbol, token_data)
    return merged


def list_supported_operations(network_name: str, protocol_name: str | None = None) -> list[str]:
    protocols = get_chain_protocols(network_name)
    if not protocols:
        return []

    if protocol_name:
        pid = resolve_protocol_id(protocol_name)
        protocol = protocols.get(pid)
        if not protocol:
            return []
        return sorted((protocol.get("operations") or {}).keys())

    ops: set[str] = set()
    for protocol in protocols.values():
        ops.update((protocol.get("operations") or {}).keys())
    return sorted(ops)


def get_operation_route(
    network_name: str,
    protocol_name: str,
    operation: str,
    token_symbol: str | None = None,
) -> dict[str, Any] | None:
    chain_key = resolve_defi_chain(network_name)
    if not chain_key:
        return None

    protocol_id = resolve_protocol_id(protocol_name)
    protocols = get_chain_protocols(chain_key)
    protocol = protocols.get(protocol_id)
    if not protocol:
        return None

    operation_key = _normalize_key(operation)
    operation_cfg = (protocol.get("operations") or {}).get(operation_key)
    if not operation_cfg:
        return None

    contract_ref = operation_cfg.get("contractRef")
    contracts = protocol.get("contracts") or {}
    contract_address = contracts.get(contract_ref)

    token_cfg = None
    if token_symbol:
        token_cfg = (protocol.get("tokens") or {}).get(token_symbol.upper())
        if token_cfg and operation_key not in (token_cfg.get("operations") or []):
            return None

    return {
        "chain": chain_key,
        "protocolId": protocol_id,
        "protocolName": protocol.get("displayName") or protocol_id,
        "operation": operation_key,
        "operationMeta": DEFI_OPERATION_CATALOG.get(operation_key, {}),
        "contractRef": contract_ref,
        "contractAddress": contract_address,
        "method": operation_cfg.get("method"),
        "approvalTarget": contracts.get(operation_cfg.get("approvalTargetRef")),
        "token": token_cfg,
        "notes": operation_cfg.get("notes"),
    }


def is_operation_supported(
    network_name: str,
    protocol_name: str,
    operation: str,
    token_symbol: str | None = None,
) -> bool:
    return get_operation_route(network_name, protocol_name, operation, token_symbol) is not None
