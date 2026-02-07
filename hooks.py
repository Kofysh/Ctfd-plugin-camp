"""
Hooks Flask (before_request / after_request / context_processor)
pour le filtrage des challenges par camp.
"""

import json
import logging
import re

from flask import Flask, g, redirect, request

from CTFd.models import Challenges, db
from CTFd.utils.config import get_config
from CTFd.utils.user import get_current_team, get_ip, is_admin

from .constants import (
    CFG_SHOW_CHALLENGE_BADGES,
    LOG_PREFIX,
    REQUEST_INFO_MAX_LENGTH,
    VALID_CAMPS,
)
from .helpers import can_change_camp
from .models import CampAccessLog, ChallengeCamp, TeamCamp

logger = logging.getLogger("CTFdCamps")

# Regex compilée une seule fois pour le matching des challenges individuels
_CHALLENGE_ID_RE = re.compile(r"^/api/v1/challenges/(\d+)$")


def register_hooks(app: Flask) -> None:
    """Enregistre tous les hooks sur l'application Flask."""

    _register_camp_redirect(app)
    _register_challenge_list_filter(app)
    _register_challenge_detail_filter(app)
    _register_camp_extraction(app)
    _register_camp_save(app)
    _register_context_processors(app)
    _register_badge_injection(app)
    _register_template_enrichment(app)


# ---------------------------------------------------------------------------
# 1. Redirection vers /camps/select si pas de camp
# ---------------------------------------------------------------------------

def _register_camp_redirect(app: Flask) -> None:

    @app.before_request
    def check_team_has_camp():
        if is_admin():
            return

        # Ignorer les routes API, statiques, admin et la page de sélection elle-même
        ep = request.endpoint or ""
        if ep.startswith(("api.", "views.static", "admin.")):
            return
        if request.path.startswith("/camps/"):
            return

        # Vérifier uniquement pour /challenges
        if request.path == "/challenges" or request.path.startswith("/challenges/"):
            team = get_current_team()
            if team and not TeamCamp.query.filter_by(team_id=team.id).first():
                return redirect("/camps/select")


# ---------------------------------------------------------------------------
# 2. Filtrage de la liste des challenges (GET /api/v1/challenges)
# ---------------------------------------------------------------------------

def _register_challenge_list_filter(app: Flask) -> None:

    @app.after_request
    def filter_challenges_list(response):
        if request.path != "/api/v1/challenges" or response.status_code != 200:
            return response
        if is_admin():
            return response

        try:
            team = get_current_team()
            if not team:
                return response

            team_camp_entry = TeamCamp.query.filter_by(team_id=team.id).first()
            if not team_camp_entry:
                return response

            team_camp = team_camp_entry.camp
            data = json.loads(response.get_data(as_text=True))

            if not data.get("success") or "data" not in data:
                return response

            original_count = len(data["data"])

            # Charger tous les camps en un seul query (évite N+1)
            camps_map = {
                cc.challenge_id: cc.camp for cc in ChallengeCamp.query.all()
            }

            data["data"] = [
                ch for ch in data["data"]
                if camps_map.get(ch["id"]) is None or camps_map.get(ch["id"]) == team_camp
            ]

            response.set_data(json.dumps(data))
            logger.info(
                "%s Filtrage liste: %d/%d challenges visibles (camp %s)",
                LOG_PREFIX, len(data["data"]), original_count, team_camp,
            )

        except Exception:
            logger.exception("%s Erreur filtrage liste challenges", LOG_PREFIX)

        return response


# ---------------------------------------------------------------------------
# 3. Filtrage d'un challenge individuel (GET /api/v1/challenges/<id>)
# ---------------------------------------------------------------------------

def _register_challenge_detail_filter(app: Flask) -> None:

    @app.after_request
    def filter_challenge_detail(response):
        match = _CHALLENGE_ID_RE.match(request.path)
        if not match or response.status_code != 200:
            return response
        if is_admin():
            return response

        challenge_id = int(match.group(1))

        try:
            team = get_current_team()
            if not team:
                return response

            team_camp_entry = TeamCamp.query.filter_by(team_id=team.id).first()
            if not team_camp_entry:
                return response

            team_camp = team_camp_entry.camp
            camp_entry = ChallengeCamp.query.filter_by(challenge_id=challenge_id).first()
            challenge_camp = camp_entry.camp if camp_entry else None

            # Challenge d'un autre camp → bloquer
            if challenge_camp is not None and challenge_camp != team_camp:
                _log_unauthorized_access(team, challenge_id, team_camp, challenge_camp)

                response.set_data(json.dumps({
                    "success": False,
                    "error": "Ce challenge n'est pas accessible par votre camp",
                }))
                response.status_code = 403

        except Exception:
            logger.exception("%s Erreur filtrage challenge %d", LOG_PREFIX, challenge_id)

        return response


def _log_unauthorized_access(team, challenge_id: int, team_camp: str, challenge_camp: str) -> None:
    """Enregistre une tentative d'accès non autorisée."""
    logger.warning(
        "%s Accès refusé: challenge %d (camp %s) → équipe %s (camp %s)",
        LOG_PREFIX, challenge_id, challenge_camp, team.name, team_camp,
    )
    try:
        info = f"{request.method} {request.url} (IP: {get_ip(req=request)})"
        db.session.add(CampAccessLog(
            team_id=team.id,
            challenge_id=challenge_id,
            team_camp=team_camp,
            challenge_camp=challenge_camp,
            request_info=info[:REQUEST_INFO_MAX_LENGTH],
        ))
        db.session.commit()
    except Exception:
        logger.exception("%s Erreur logging accès", LOG_PREFIX)
        db.session.rollback()


# ---------------------------------------------------------------------------
# 4. Extraction du champ "camp" des requêtes API challenges (POST/PATCH)
# ---------------------------------------------------------------------------

def _register_camp_extraction(app: Flask) -> None:

    @app.before_request
    def extract_camp_from_request():
        ep = request.endpoint or ""
        if "api.challenges" not in ep or request.method not in ("POST", "PATCH"):
            return

        camp_value = None

        # Extraire depuis le formulaire
        if request.form.get("camp"):
            camp_value = request.form.get("camp")
            mutable_form = request.form.copy()
            del mutable_form["camp"]
            request.form = mutable_form

        # Extraire depuis le JSON
        elif request.is_json and request.json and request.json.get("camp"):
            camp_value = request.json.get("camp")
            del request.json["camp"]

        # Validation stricte
        g.camp_value = camp_value if camp_value in VALID_CAMPS else None

        if camp_value and camp_value not in VALID_CAMPS:
            logger.warning("%s Valeur de camp invalide rejetée: %s", LOG_PREFIX, camp_value)


# ---------------------------------------------------------------------------
# 5. Sauvegarde du camp après création/modification d'un challenge
# ---------------------------------------------------------------------------

def _register_camp_save(app: Flask) -> None:

    @app.after_request
    def save_challenge_camp(response):
        camp_value = getattr(g, "camp_value", None)
        if not camp_value:
            return response

        try:
            if request.method == "POST" and response.status_code in (200, 201):
                _save_camp_on_create(response, camp_value)
            elif request.method == "PATCH" and response.status_code == 200:
                _save_camp_on_update(camp_value)
        except Exception:
            logger.exception("%s Erreur sauvegarde camp", LOG_PREFIX)
            db.session.rollback()

        return response


def _save_camp_on_create(response, camp_value: str) -> None:
    """Sauvegarde le camp lors de la création d'un challenge."""
    data = json.loads(response.get_data(as_text=True))
    challenge_id = data.get("data", {}).get("id")
    if not challenge_id:
        return

    db.session.add(ChallengeCamp(challenge_id=challenge_id, camp=camp_value))
    db.session.commit()
    logger.info("%s Camp '%s' assigné au challenge %d", LOG_PREFIX, camp_value, challenge_id)


def _save_camp_on_update(camp_value: str) -> None:
    """Met à jour le camp lors de la modification d'un challenge."""
    challenge_id = request.view_args.get("challenge_id")
    if not challenge_id:
        return

    entry = ChallengeCamp.query.filter_by(challenge_id=challenge_id).first()
    if entry:
        entry.camp = camp_value
    else:
        db.session.add(ChallengeCamp(challenge_id=challenge_id, camp=camp_value))

    db.session.commit()
    logger.info("%s Camp '%s' mis à jour pour challenge %d", LOG_PREFIX, camp_value, challenge_id)


# ---------------------------------------------------------------------------
# 6. Context processors pour les templates Jinja
# ---------------------------------------------------------------------------

def _register_context_processors(app: Flask) -> None:

    @app.context_processor
    def inject_camp_helpers():
        def get_challenge_camp(challenge_id: int) -> str | None:
            entry = ChallengeCamp.query.filter_by(challenge_id=challenge_id).first()
            return entry.camp if entry else None

        def get_team_camp(team_id: int) -> str | None:
            entry = TeamCamp.query.filter_by(team_id=team_id).first()
            return entry.camp if entry else None

        def can_change_camp_for_display() -> bool:
            team = get_current_team()
            if not team:
                return False
            allowed, _ = can_change_camp(team.id)
            return allowed

        return dict(
            get_challenge_camp=get_challenge_camp,
            get_team_camp=get_team_camp,
            get_current_team=get_current_team,
            can_change_camp_for_display=can_change_camp_for_display,
        )


# ---------------------------------------------------------------------------
# 7. Injection des pastilles de camp (badges JS) sur /challenges
# ---------------------------------------------------------------------------

def _register_badge_injection(app: Flask) -> None:

    @app.after_request
    def inject_challenge_badges(response):
        if request.path != "/challenges" or response.status_code != 200:
            return response

        if not get_config(CFG_SHOW_CHALLENGE_BADGES, default=False):
            return response

        try:
            challenges = Challenges.query.filter_by(state="visible").all()
            camps_map = {}
            for ch in challenges:
                entry = ChallengeCamp.query.filter_by(challenge_id=ch.id).first()
                if entry:
                    camps_map[ch.id] = entry.camp

            if not camps_map:
                return response

            script = _build_badge_script(camps_map)
            html = response.get_data(as_text=True)
            if "</body>" in html:
                response.set_data(html.replace("</body>", script + "</body>"))

        except Exception:
            logger.exception("%s Erreur injection badges", LOG_PREFIX)

        return response


def _build_badge_script(camps_map: dict) -> str:
    """Génère le script JS pour les pastilles de camp."""
    return f"""
<script>
(function() {{
    var campsMap = {json.dumps(camps_map)};

    function addCampBadges() {{
        document.querySelectorAll('.challenge-button[value]').forEach(function(btn) {{
            var id = parseInt(btn.getAttribute('value'));
            var camp = campsMap[id];
            if (!camp || btn.querySelector('.camp-badge')) return;

            var badge = document.createElement('div');
            badge.className = 'camp-badge';
            badge.style.cssText = 'position:absolute;bottom:8px;left:8px;width:14px;height:14px;'
                + 'border-radius:50%;border:2px solid white;box-shadow:0 2px 4px rgba(0,0,0,.3);'
                + 'z-index:10;pointer-events:none;background-color:'
                + (camp === 'blue' ? '#007bff' : '#dc3545');
            badge.title = camp === 'blue' ? 'Camp Bleu' : 'Camp Rouge';

            btn.style.position = 'relative';
            btn.appendChild(badge);
        }});
    }}

    if (document.readyState === 'loading') {{
        document.addEventListener('DOMContentLoaded', addCampBadges);
    }} else {{
        addCampBadges();
    }}

    new MutationObserver(addCampBadges).observe(document.body, {{childList: true, subtree: true}});
}})();
</script>
"""


# ---------------------------------------------------------------------------
# 8. Enrichissement des données de camp dans g (pour les templates admin)
# ---------------------------------------------------------------------------

def _register_template_enrichment(app: Flask) -> None:

    @app.before_request
    def enrich_with_camp_data():
        ep = str(request.endpoint or "")

        if "challenges" in ep:
            try:
                g.camps_map = {c.challenge_id: c.camp for c in ChallengeCamp.query.all()}
            except Exception:
                g.camps_map = {}

        if "teams" in ep:
            try:
                g.teams_camps_map = {tc.team_id: tc.camp for tc in TeamCamp.query.all()}
            except Exception:
                g.teams_camps_map = {}
