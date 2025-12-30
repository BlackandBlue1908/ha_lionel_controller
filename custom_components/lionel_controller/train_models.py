"""Train model definitions with announcement name mappings.

This file contains announcement name mappings for different Lionel train models.
Each train model has different voice announcements, so this allows users to see
the correct names for their specific train.

To contribute a new train model:
1. Add a new entry to TRAIN_MODELS with your train's name as the key
2. Map each announcement code (1-6) to the actual phrase your train says
3. Submit a pull request!

The announcement codes are:
- 1: "Ready to Roll" equivalent
- 2: "Hey There" equivalent  
- 3: "Squeaky" equivalent
- 4: "Water and Fire" equivalent
- 5: "Fastest Freight" equivalent
- 6: "Penna Flyer" equivalent
"""

# Default/Generic announcement names (used when train model is unknown)
DEFAULT_ANNOUNCEMENTS = {
    "random": "Random",
    "ready_to_roll": "Ready to Roll",
    "hey_there": "Hey There",
    "squeaky": "Squeaky",
    "water_and_fire": "Water & Fire",
    "fastest_freight": "Fastest Freight",
    "penna_flyer": "Penna Flyer",
}

# Train model specific announcement mappings
# Key: Train model name (shown in config flow)
# Value: Dict mapping announcement keys to display names
TRAIN_MODELS = {
    "Generic": DEFAULT_ANNOUNCEMENTS,
    
    "Polar Express": {
        "random": "Random",
        "ready_to_roll": "Polar Express",
        "hey_there": "All Aboard",
        "squeaky": "You Coming?",
        "water_and_fire": "Tickets",
        "fastest_freight": "First Gift",
        "penna_flyer": "The King",
    },
    "Thomas The Tank Engine": {
        "random": "Random",
        "all_aboard": "All Aboard",
        "full_steam_ahead": "Full Steam Ahead!",
        "number_1_engine": "Number 1 Engine",
        "rocking_the_rails": "Rocking the Rails",
        "oh_yeah": "Oh Yeah!",
        "on_track_and_on_time": "On Track and On Time!",
    },
    
    # Add more train models below!
    # Example:
    # "Hogwarts Express": {
    #     "random": "Random",
    #     "ready_to_roll": "Platform 9¾",
    #     "hey_there": "Welcome Aboard",
    #     "squeaky": "Anything from the trolley?",
    #     "water_and_fire": "Hogwarts",
    #     "fastest_freight": "Expelliarmus",
    #     "penna_flyer": "Expecto Patronum",
    # },
}

# List of available train models for config flow
TRAIN_MODEL_OPTIONS = list(TRAIN_MODELS.keys())


def get_announcement_names(train_model: str) -> dict:
    """Get announcement name mappings for a specific train model.
    
    Args:
        train_model: The train model name (e.g., "Polar Express")
        
    Returns:
        Dict mapping announcement keys to display names
    """
    return TRAIN_MODELS.get(train_model, DEFAULT_ANNOUNCEMENTS)


def get_announcement_name(train_model: str, announcement_key: str) -> str:
    """Get a specific announcement name for a train model.
    
    Args:
        train_model: The train model name
        announcement_key: The announcement key (e.g., "ready_to_roll")
        
    Returns:
        The display name for that announcement
    """
    names = get_announcement_names(train_model)
    return names.get(announcement_key, announcement_key.replace("_", " ").title())
