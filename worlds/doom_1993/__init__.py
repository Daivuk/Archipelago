import functools
import logging
from typing import Any, Dict, List

from BaseClasses import CollectionState, Item, ItemClassification, Location, MultiWorld, Region, Tutorial
from worlds.AutoWorld import WebWorld, World
from . import Events, Items, Locations, Options, Regions, Rules

logger = logging.getLogger("DOOM 1993")


class DOOM1993Location(Location):
    game: str = "DOOM 1993"


class DOOM1993Item(Item):
    game: str = "DOOM 1993"


class DOOM1993Web(WebWorld):
    tutorials = [Tutorial(
        "Multiworld Setup Guide",
        "A guide to setting up the DOOM 1993 randomizer connected to an Archipelago Multiworld",
        "English",
        "setup_en.md",
        "setup/en",
        ["Daivuk"]
    )]
    theme = "dirt"


class DOOM1993World(World):
    """
    Developed by id Software, and originally released in 1993, DOOM pioneered and popularized the first-person shooter,
    setting a standard for all FPS games.
    """
    option_definitions = Options.options
    game = "DOOM 1993"
    web = DOOM1993Web()
    data_version = 1
    required_client_version = (0, 3, 9)

    item_name_to_id = {data["name"]: item_id for item_id, data in Items.item_table.items()}
    item_name_groups = Items.item_name_groups

    location_name_to_id = {data["name"]: loc_id for loc_id, data in Locations.location_table.items()}
    location_name_groups = Locations.location_name_groups

    starting_level_for_episode: List[str] = [
        "Hangar (E1M1)",
        "Deimos Anomaly (E2M1)",
        "Hell Keep (E3M1)"
    ]

    # Item ratio that scales depending on episode count. These are the ratio for 3 episode.
    items_ratio: Dict[str, float] = {
        "Armor": 41,
        "Mega Armor": 25,
        "Berserk": 12,
        "Invulnerability": 10,
        "Partial invisibility": 18,
        "Supercharge": 28,
        "Medikit": 15,
        "Box of bullets": 13,
        "Box of rockets": 13,
        "Box of shotgun shells": 13,
        "Energy cell pack": 10
    }

    def __init__(self, world: MultiWorld, player: int):
        self.included_episodes = [1, 1, 1]
        self.location_count = 0

        super().__init__(world, player)

    def get_episode_count(self):
        return functools.reduce(lambda count, episode: count + episode, self.included_episodes)

    def generate_early(self):
        # Cache which episodes are included
        for i in range(3):
            self.included_episodes[i] = getattr(self.multiworld, f"episode{i + 1}")[self.player].value

        # If no episodes selected, select Episode 1
        if self.get_episode_count() == 0:
            self.included_episodes[0] = 1

    def create_regions(self):
        # Main regions
        menu_region = Region("Menu", self.player, self.multiworld)
        mars_region = Region("Mars", self.player, self.multiworld)
        self.multiworld.regions += [menu_region, mars_region]
        menu_region.add_exits({"Mars": None})

        # Create regions and locations
        for region_name in Regions.regions:
            region = Region(region_name, self.player, self.multiworld)
            locaitons = {
                loc["name"]: (loc_id if loc["index"] != -1 else None)
                for loc_id, loc in Locations.location_table.items()
                if loc["region"] == region_name and self.included_episodes[loc["episode"] - 1]
            }
            region.add_locations(locaitons, DOOM1993Location)

            self.multiworld.regions.append(region)
            mars_region.add_exits({region_name: None})

        # Sum locations for items creation
        self.location_count = len(self.multiworld.get_locations(self.player))

    def completion_rule(self, state: CollectionState):
        for event in Events.events:
            if event not in self.location_name_to_id:
                continue
            loc = Locations.location_table[self.location_name_to_id[event]]
            if not self.included_episodes[loc["episode"] - 1]:
                continue
            if not state.has(event, self.player, 1):
                return False
        return True

    def set_rules(self):
        Rules.set_rules(self)
        self.multiworld.completion_condition[self.player] = lambda state: self.completion_rule(state)

        # Forbid progression items to locations that can be missed and can't be picked up. (e.g. One-time timed
        # platform) Unless the user allows for it.
        if getattr(self.multiworld, "allow_death_logic")[self.player]:
            self.multiworld.exclude_locations[self.player] += set(Locations.death_logic_locations)
    
    def create_item(self, name: str) -> DOOM1993Item:
        item_id: int = self.item_name_to_id[name]
        return DOOM1993Item(name, Items.item_table[item_id]["classification"], item_id, self.player)

    def create_event(self, name: str) -> DOOM1993Item:
        return DOOM1993Item(name, ItemClassification.progression, None, self.player)

    def place_locked_item_in_locations(self, item_name, locations):
        location = self.multiworld.random.choice(locations)
        self.multiworld.get_location(location, self.player).place_locked_item(self.create_item(item_name))
        self.location_count -= 1

    def create_items(self):
        is_only_first_episode: bool = self.get_episode_count() == 1 and self.included_episodes[0]
        itempool: List[DOOM1993Item] = []

        # Items
        for item_id, item in Items.item_table.items():
            if item["episode"] != -1 and not self.included_episodes[item["episode"] - 1]:
                continue

            if item["name"] in {"BFG9000", "Plasma Gun"} and is_only_first_episode:
                continue  # Don't include those guns in first episode

            if item["name"] in {"Warrens (E3M9) - Blue skull key", "Halls of the Damned (E2M6) - Yellow skull key"}:
                continue

            count = item["count"] if item["name"] not in self.starting_level_for_episode else item["count"] - 1
            itempool += [self.create_item(item["name"]) for _ in range(count)]

        # Place end level items in locked locations
        for event in Events.events:
            if event not in self.location_name_to_id:
                continue

            loc = Locations.location_table[self.location_name_to_id[event]]
            if not self.included_episodes[loc["episode"] - 1]:
                continue

            self.multiworld.get_location(event, self.player).place_locked_item(self.create_event(event))
            self.location_count -= 1
    
        # Special case for E2M6 and E3M8, where you enter a normal door then get stuck behind with a key door.
        # We need to put the key in the locations available behind this door.
        if self.included_episodes[1]:
            self.place_locked_item_in_locations("Halls of the Damned (E2M6) - Yellow skull key", [
                "Halls of the Damned (E2M6) - Yellow skull key",
                "Halls of the Damned (E2M6) - Partial invisibility 2"
            ])
        if self.included_episodes[2]:
            self.place_locked_item_in_locations("Warrens (E3M9) - Blue skull key", [
                "Warrens (E3M9) - Rocket launcher",
                "Warrens (E3M9) - Rocket launcher 2",
                "Warrens (E3M9) - Partial invisibility",
                "Warrens (E3M9) - Invulnerability",
                "Warrens (E3M9) - Supercharge",
                "Warrens (E3M9) - Berserk",
                "Warrens (E3M9) - Chaingun"
            ])

        # Give starting levels right away
        for i in range(len(self.included_episodes)):
            if self.included_episodes[i]:
                self.multiworld.push_precollected(self.create_item(self.starting_level_for_episode[i]))

        # Fill the rest starting with weapons, powerups then fillers
        self.create_ratioed_items("Armor", itempool)
        self.create_ratioed_items("Mega Armor", itempool)
        self.create_ratioed_items("Berserk", itempool)
        self.create_ratioed_items("Invulnerability", itempool)
        self.create_ratioed_items("Partial invisibility", itempool)
        self.create_ratioed_items("Supercharge", itempool)

        while len(itempool) < self.location_count:
            itempool.append(self.create_item(self.get_filler_item_name()))

        # add itempool to multiworld
        self.multiworld.itempool += itempool

    def get_filler_item_name(self):
        return self.multiworld.random.choice([
            "Medikit",
            "Box of bullets",
            "Box of rockets",
            "Box of shotgun shells",
            "Energy cell pack"
        ])

    def create_ratioed_items(self, item_name: str, itempool: List[DOOM1993Item]):
        remaining_loc = self.location_count - len(itempool)
        ep_count = self.get_episode_count()

        # Was balanced for 3 episodes
        count = min(remaining_loc, max(1, int(round(self.items_ratio[item_name] * ep_count / 3))))
        if count == 0:
            logger.warning("Warning, no ", item_name, " will be placed.")
            return

        for i in range(count):
            itempool.append(self.create_item(item_name))

    def fill_slot_data(self) -> Dict[str, Any]:
        return {name: getattr(self.multiworld, name)[self.player].value for name in self.option_definitions}
