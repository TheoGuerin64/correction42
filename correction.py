"""This script will notify you when a new slot is available for correction on the 42 intra."""

import json
import os
import platform
from datetime import date, datetime, timedelta
from string import Template
from time import sleep
from typing import Dict, List, Optional

import requests
from notifypy import Notify
from rich.console import Console
from rich.prompt import IntPrompt, Prompt

SLEEP_TIME = 10
URL = Template("https://projects.intra.42.fr/projects/$project_name/slots.json?team_id=$team_id&start=$start&end=$end")
DIR = os.path.dirname(os.path.realpath(__file__))


class SlotException(Exception):
    """Exception raised when a slot could not be retrieved."""


class Slot:
    """A slot is a time interval where a project can be corrected."""

    def __init__(self, data: Dict[str, str]) -> None:
        self.id = data["id"]
        self.start = datetime.strptime(data["start"][:19], "%Y-%m-%dT%H:%M:%S")
        self.end = datetime.strptime(data["end"][:19], "%Y-%m-%dT%H:%M:%S")

    def __eq__(self, __value: object) -> bool:
        if not isinstance(__value, Slot):
            raise NotImplementedError()
        return self.id == __value.id

    def __str__(self) -> str:
        if self.start.date() == self.end.date() and self.start.date() == date.today():
            return f"{self.start.time():%H:%M} - {self.end.time():%H:%M}"
        return f"{self.start:%d/%m/%Y %H:%M} - {self.end:%d/%m/%Y %H:%M}"


def get_config_path(console: Console) -> Optional[str]:
    """Get the path to the config file."""
    if platform.system() == "Windows":
        config_folder = os.getenv("APPDATA")
        if config_folder is None:
            console.print("Could not find APPDATA environment variable. No config will be saved.", style="bold red")
    else:
        config_folder = os.getenv("HOME")
        if config_folder is None:
            console.print("Could not find HOME environment variable. No config will be saved.", style="bold red")

    if config_folder is None:
        return None
    return os.path.join(config_folder, "42-correction-tracker.json")


def load_config(console: Console, config_path: Optional[str]) -> dict:
    """Load the config file."""
    if config_path is None or not os.path.exists(config_path):
        return {}

    try:
        with open(config_path, "r", encoding="utf-8") as file:
            config = json.load(file)
    except (OSError, json.JSONDecodeError) as error:
        console.print(f"Could not load config file at {config_path} ({error})", style="bold red")
        config = {}

    return config


def ask_config(config: dict) -> None:
    """Ask the user for the config values."""
    project_name_raw = Prompt.ask("Project name", default=config.get("project_name"))
    config["project_name"] = project_name_raw.replace(" ", "-").lower()
    config["team_id"] = Prompt.ask("Team ID", default=config.get("team_id"))
    config["session_token"] = Prompt.ask("Session token", default=config.get("session_token"))
    config["nb_days"] = IntPrompt.ask("Number of days", default=config.get("nb_days"))


def save_config(console: Console, config: dict, config_path: Optional[str]) -> None:
    """Save the config file."""
    if config_path is None:
        return

    try:
        with open(config_path, "w", encoding="utf-8") as file:
            json.dump(config, file)
    except OSError:
        console.print(f"Could not save config file at {config_path}", style="bold red")


def get_slots(config: dict) -> List[Slot]:
    """Get the slots for the given config."""
    response = requests.get(
        URL.substitute(config, start=date.today(), end=date.today() + timedelta(days=config["nb_days"])),
        headers={
            "host": "projects.intra.42.fr",
            "Cookie": f"_intra_42_session_production={config['session_token']}"
        },
        timeout=10
    )
    content = response.json()

    if response.status_code == 200:
        return [Slot(slot) for slot in content]
    if response.status_code == 404:
        raise SlotException("Could not get slots (Project not found)")
    if response.status_code == 401:
        raise SlotException("Could not get slots (Invalid session token)")
    raise SlotException("Could not get slots (Unknown error)")


def send_new_slot_notification(slot: Slot) -> None:
    """Send a notification for a new slot."""
    notification = Notify()
    notification.title = "New slot"
    notification.message = str(slot)
    notification.icon = DIR + "/icon.png"
    notification.send()


def main() -> None:
    console = Console()
    console.print("Welcome to the 42 correction tracker!", style="bold green", highlight=False)

    config_path = get_config_path(console)
    config = load_config(console, config_path)
    ask_config(config)
    save_config(console, config, config_path)

    print()
    with console.status("Searching for slots..."):
        slots = []
        while True:
            try:
                new_slots = get_slots(config)
            except SlotException as error:
                console.print(error, style="bold red", highlight=False)
                sleep(SLEEP_TIME)
                continue

            for new_slot in new_slots:
                if new_slot not in slots:
                    console.print(f"{datetime.now()} - New slot: {new_slot}", style="bold green")
                    send_new_slot_notification(new_slot)
                    slots.append(new_slot)
            for old_slot in slots.copy():
                if old_slot not in new_slots:
                    console.print(f"{datetime.now()} - Slot removed: {old_slot}", style="bold red")
                    slots.remove(old_slot)

            sleep(SLEEP_TIME)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
