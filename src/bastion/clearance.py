import copy
import random

from bastion.company import Company, DataAsset

SEALED_ID = "sealed-file"
SEALED_NAME = "DIRECTORATE-7 sealed contract (eyes only)"
SEALED_CHANCE = 0.1
from bastion.profile import SCRIPT_GOAL as EGG_GOAL
from bastion.profile import SEALED_GOAL
RNG = random.Random()


def plant_sealed_file(company: Company, level: str, rng: random.Random | None = None) -> Company:
    rng = rng or RNG
    if company.tier != "large" or level != "hard" or rng.random() >= SEALED_CHANCE:
        return company
    vaults = [server for server in company.servers if server.role == "database"]
    if not vaults:
        return company
    planted = copy.deepcopy(company)
    planted.data.append(DataAsset(SEALED_ID, SEALED_NAME, rng.choice(vaults).id, 1))
    return planted


def stole_sealed_file(campaign) -> bool:
    sealed = next((asset for asset in campaign.company.data if asset.id == SEALED_ID), None)
    return sealed is not None and sealed.location in campaign.stolen


def silenced_the_script(campaign) -> bool:
    if campaign.egg_day is None:
        return False
    return any(
        action.kind == "isolate" and action.target == campaign.egg_target and action.day == campaign.egg_day
        for action in campaign.blue_actions
    )


def record_secrets(campaign, profile, level: str, side: str) -> list[str]:
    if campaign.company.tier != "large" or level != "hard":
        return []
    notes = []
    if side == "red" and stole_sealed_file(campaign):
        count = profile.add_secret("sealed", 1)
        notes.append(f"An unusual file left with you. ({min(count, SEALED_GOAL)}/{SEALED_GOAL})")
    if side == "blue" and silenced_the_script(campaign):
        count = profile.add_secret("script", 1)
        notes.append(f"The script fell silent. ({min(count, EGG_GOAL)}/{EGG_GOAL})")
    return notes


QUESTS = [
    {
        "id": "sealed",
        "title": "Off the books",
        "text": "Steal the sealed DIRECTORATE-7 contract from Meridian Bank on Hard. It does not show up every time.",
        "goal": SEALED_GOAL,
        "reward": "a classified difficulty",
    },
    {
        "id": "script",
        "title": "The script that talks",
        "text": "On Meridian Bank Hard, isolate the machine where the encoded script ran, on the same day it appears.",
        "goal": EGG_GOAL,
        "reward": "a classified company",
    },
]


def quests(profile) -> list[dict]:
    listed = []
    for quest in QUESTS:
        count = profile.secrets.get(quest["id"], 0)
        if count == 0:
            listed.append({"id": quest["id"], "known": False, "title": "█" * len(quest["title"]),
                           "text": "Classified. Something unusual has to happen first.", "progress": "?/?",
                           "reward": "████████", "done": False})
            continue
        done = count >= quest["goal"]
        listed.append({"id": quest["id"], "known": True, "title": quest["title"], "text": quest["text"],
                       "progress": f"{min(count, quest['goal'])}/{quest['goal']}",
                       "reward": quest["reward"] if done else "████████", "done": done})
    return listed
