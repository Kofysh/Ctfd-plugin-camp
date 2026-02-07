"""
Constantes du plugin CTFd Camps.
"""

# --- Valeurs de camp ---
CAMP_BLUE = "blue"
CAMP_RED = "red"
VALID_CAMPS = {CAMP_BLUE, CAMP_RED}
VALID_CAMPS_WITH_NONE = {CAMP_BLUE, CAMP_RED, "none"}

CAMP_LABELS = {
    CAMP_BLUE: "Camp Bleu",
    CAMP_RED: "Camp Rouge",
}

# --- Clés de configuration CTFd ---
CFG_ALLOW_CHANGE = "camps_allow_change"
CFG_SHOW_PUBLIC_STATS = "camps_show_public_stats"
CFG_SHOW_CHALLENGE_BADGES = "camps_show_challenge_badges"
CFG_ENABLE_TEAM_LIMITS = "camps_enable_team_limits"
CFG_MAX_BLUE_TEAMS = "camps_max_blue_teams"
CFG_MAX_RED_TEAMS = "camps_max_red_teams"
CFG_CHANGE_DEADLINE = "camps_change_deadline"

# --- Limites ---
MAX_LOGS_DISPLAYED = 100
REQUEST_INFO_MAX_LENGTH = 500

# --- Logging ---
LOG_PREFIX = "[CTFd Camps]"
