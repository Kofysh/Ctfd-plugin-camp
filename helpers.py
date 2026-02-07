"""
Fonctions utilitaires partagées du plugin CTFd Camps.
"""

import logging
from datetime import datetime, timezone

from CTFd.cache import clear_config
from CTFd.models import Configs, db
from CTFd.utils.config import get_config

from .constants import (
    CFG_ALLOW_CHANGE,
    CFG_CHANGE_DEADLINE,
    CFG_ENABLE_TEAM_LIMITS,
    CFG_MAX_BLUE_TEAMS,
    CFG_MAX_RED_TEAMS,
    CAMP_BLUE,
    CAMP_LABELS,
    LOG_PREFIX,
)
from .models import TeamCamp

logger = logging.getLogger("CTFdCamps")


# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

def set_config(key: str, value) -> None:
    """Crée ou met à jour une entrée de configuration CTFd."""
    config = Configs.query.filter_by(key=key).first()
    if config:
        config.value = value
    else:
        config = Configs(key=key, value=value)
        db.session.add(config)
    db.session.commit()
    clear_config()


# ---------------------------------------------------------------------------
# Camp validation helpers
# ---------------------------------------------------------------------------

def can_change_camp(team_id: int) -> tuple[bool, str]:
    """
    Vérifie si une équipe peut changer de camp.

    Returns:
        (peut_changer, raison_si_non)
    """
    # 1. Vérifier la deadline
    deadline_str = get_config(CFG_CHANGE_DEADLINE, default="")
    if deadline_str:
        try:
            deadline = datetime.fromisoformat(str(deadline_str))
            if datetime.now(timezone.utc) > deadline:
                return False, "La date limite de changement de camp est dépassée"
        except (ValueError, TypeError) as exc:
            logger.warning("%s Erreur parsing deadline: %s", LOG_PREFIX, exc)

    # 2. Vérifier si le changement est autorisé
    allow_change = get_config(CFG_ALLOW_CHANGE, default=True)
    if not allow_change:
        team_camp = TeamCamp.query.filter_by(team_id=team_id).first()
        if team_camp:
            return False, "Le changement de camp est désactivé. Votre choix est définitif."

    return True, "OK"


def can_join_camp(camp: str, current_team_id: int | None = None) -> tuple[bool, str]:
    """
    Vérifie si une équipe peut rejoindre un camp (quotas).

    Returns:
        (peut_rejoindre, raison_si_non)
    """
    enable_limits = get_config(CFG_ENABLE_TEAM_LIMITS, default=False)
    if not enable_limits:
        return True, ""

    # Récupérer la limite pour ce camp
    if camp == CAMP_BLUE:
        max_teams = get_config(CFG_MAX_BLUE_TEAMS, default=0)
    else:
        max_teams = get_config(CFG_MAX_RED_TEAMS, default=0)

    # 0 = illimité
    if not max_teams:
        return True, ""

    max_teams = int(max_teams)
    current_count = TeamCamp.query.filter_by(camp=camp).count()

    # Ne pas compter l'équipe si elle est déjà dans ce camp
    if current_team_id:
        team_camp = TeamCamp.query.filter_by(team_id=current_team_id).first()
        if team_camp and team_camp.camp == camp:
            return True, ""

    if current_count >= max_teams:
        label = CAMP_LABELS.get(camp, camp)
        return False, f"Le {label} est complet ({current_count}/{max_teams} équipes)"

    return True, ""
