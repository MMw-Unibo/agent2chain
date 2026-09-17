"""Helpers for chat message construction and ADK event text extraction."""

from __future__ import annotations

from typing import Any

from google.genai import types


def extract_text_from_event(event: Any) -> str:
    """Extract plain text from an ADK event if present."""
    content = getattr(event, "content", None)
    if not content:
        return ""

    parts = getattr(content, "parts", None) or []
    chunks: list[str] = []
    for part in parts:
        text = getattr(part, "text", None)
        if text:
            chunks.append(text)
    return "\n".join(chunks).strip()


def build_wallet_context(wallet: dict[str, Any] | None) -> str:
    """Return wallet context block appended to the user prompt when connected."""
    if not wallet or not wallet.get("connected"):
        return ""

    return (
        "\n\nLive Wallet Context:\n"
        f"- Account: {wallet.get('account', 'unknown')}\n"
        f"- Chain ID: {wallet.get('chainId', 'unknown')}\n"
        f"- Network: {wallet.get('networkName', 'unknown')}\n"
        f"- Balance (ETH): {wallet.get('balanceEth', 'unknown')}"
    )


def build_user_content(user_message: str, wallet: dict[str, Any] | None) -> types.UserContent:
    """Build ADK user content enriched with optional wallet context."""
    wallet_block = build_wallet_context(wallet)
    enriched_message = f"{user_message.strip()}{wallet_block}".strip()
    return types.UserContent(parts=[types.Part(text=enriched_message)])


def format_agent_reply(reply: str) -> str:
    """Normalize output text while preserving markdown semantics."""
    return reply.replace("\r\n", "\n").strip()
