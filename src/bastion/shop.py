"""The shop: a small starter kit is free, everything else is bought once with coins and kept.

Coins are earned from points (10 points = 1 coin), separately for Red and Blue, and the
server counts them from refereed games. The computer opponent always has everything, so
buying more never makes the game easier than it is designed to be; it lets you catch up.
"""
POINTS_PER_COIN = 10
STARTER = {
    "red": ("port-scan", "phishing", "brute-force", "exfiltration"),
    "blue": ("firewall", "mfa", "email-filter", "siem"),
}
TIER_PRICE = {"small": 20, "medium": 50, "large": 90, "huge": 120}


def side_of(catalog, item_id: str) -> str | None:
    if item_id in catalog.attacks:
        return "red"
    if item_id in catalog.defenses:
        return "blue"
    return None


def price(catalog, item_id: str) -> int:
    item = catalog.attacks.get(item_id) or catalog.defenses[item_id]
    return TIER_PRICE.get(item.tier, 50) + item.cost


def is_free(item_id: str) -> bool:
    return any(item_id in ids for ids in STARTER.values())


def owns(owned, item_id: str) -> bool:
    return is_free(item_id) or item_id in set(owned or [])


def items(catalog, owned) -> list[dict]:
    rows = []
    for side, pool in (("red", catalog.attacks.values()), ("blue", catalog.defenses.values())):
        for item in pool:
            rows.append({
                "id": item.id, "side": side, "name": item.name, "tier": item.tier, "cost": item.cost,
                "price": 0 if is_free(item.id) else price(catalog, item.id),
                "free": is_free(item.id), "owned": owns(owned, item.id),
                "mitre": getattr(item, "mitre_id", ""), "description": item.description,
            })
    return rows


def coins(points_by_side: dict[str, int], spent: dict[str, int]) -> dict[str, int]:
    return {side: points_by_side.get(side, 0) // POINTS_PER_COIN - spent.get(side, 0) for side in ("red", "blue")}
