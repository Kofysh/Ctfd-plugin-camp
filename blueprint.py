"""
Blueprint Flask du plugin CTFd Camps.
Routes admin et utilisateur.
"""

import logging
from datetime import datetime, timezone

from flask import Blueprint, jsonify, render_template, request

from CTFd.models import Challenges, Teams, db
from CTFd.utils.config import get_config
from CTFd.utils.decorators import admins_only, authed_only
from CTFd.utils.user import get_current_team

from .constants import (
    CFG_ALLOW_CHANGE,
    CFG_CHANGE_DEADLINE,
    CFG_ENABLE_TEAM_LIMITS,
    CFG_MAX_BLUE_TEAMS,
    CFG_MAX_RED_TEAMS,
    CFG_SHOW_CHALLENGE_BADGES,
    CFG_SHOW_PUBLIC_STATS,
    MAX_LOGS_DISPLAYED,
    VALID_CAMPS,
    VALID_CAMPS_WITH_NONE,
)
from .helpers import can_change_camp, can_join_camp, set_config
from .models import CampAccessLog, ChallengeCamp, TeamCamp

logger = logging.getLogger("CTFdCamps")


def create_blueprint() -> Blueprint:
    """Crée et retourne le blueprint du plugin Camps."""

    bp = Blueprint(
        "camps",
        __name__,
        template_folder="templates",
        static_folder="assets",
    )

    # ======================================================================
    #  ROUTES ADMIN
    # ======================================================================

    @bp.route("/admin/camps")
    @admins_only
    def camps_admin():
        """Page principale d'administration des camps."""
        teams = Teams.query.all()
        teams_data = []
        for team in teams:
            tc = TeamCamp.query.filter_by(team_id=team.id).first()
            teams_data.append({
                "id": team.id,
                "name": team.name,
                "camp": tc.camp if tc else None,
            })

        blue_count = TeamCamp.query.filter_by(camp="blue").count()
        red_count = TeamCamp.query.filter_by(camp="red").count()

        stats = {
            "blue": blue_count,
            "red": red_count,
            "unassigned": len(teams) - blue_count - red_count,
            "total": len(teams),
        }

        config = _load_admin_config()

        return render_template("camps_admin.html", teams=teams_data, stats=stats, config=config)

    @bp.route("/admin/camps/config", methods=["POST"])
    @admins_only
    def update_config():
        """Met à jour la configuration du système de camps."""
        try:
            data = request.json or {}

            deadline = data.get("deadline", "")
            if deadline:
                # Valider le format ISO
                try:
                    datetime.fromisoformat(deadline.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    return jsonify({"success": False, "error": "Format de date invalide"}), 400

            set_config(CFG_ALLOW_CHANGE, data.get("allow_change", True))
            set_config(CFG_SHOW_PUBLIC_STATS, data.get("show_public_stats", False))
            set_config(CFG_SHOW_CHALLENGE_BADGES, data.get("show_challenge_badges", False))
            set_config(CFG_ENABLE_TEAM_LIMITS, data.get("enable_team_limits", False))
            set_config(CFG_MAX_BLUE_TEAMS, int(data.get("max_blue_teams", 0)))
            set_config(CFG_MAX_RED_TEAMS, int(data.get("max_red_teams", 0)))
            set_config(CFG_CHANGE_DEADLINE, deadline)

            logger.info("[CTFd Camps] Configuration sauvegardée")
            return jsonify({"success": True, "message": "Configuration mise à jour"})

        except Exception as exc:
            logger.exception("[CTFd Camps] Erreur sauvegarde config")
            return jsonify({"success": False, "error": str(exc)}), 500

    @bp.route("/admin/camps/team/<int:team_id>", methods=["POST"])
    @admins_only
    def update_team_camp(team_id):
        """Met à jour le camp d'une équipe (admin)."""
        camp = (request.json or {}).get("camp")
        if camp not in VALID_CAMPS_WITH_NONE and camp is not None:
            return jsonify({"success": False, "error": "Camp invalide"}), 400

        team = Teams.query.filter_by(id=team_id).first()
        if not team:
            return jsonify({"success": False, "error": "Équipe introuvable"}), 404

        try:
            if camp in ("none", None):
                TeamCamp.query.filter_by(team_id=team_id).delete()
                db.session.commit()
                return jsonify({"success": True, "message": "Camp retiré"})

            tc = TeamCamp.query.filter_by(team_id=team_id).first()
            if tc:
                tc.camp = camp
            else:
                db.session.add(TeamCamp(team_id=team_id, camp=camp))

            db.session.commit()
            return jsonify({"success": True, "message": f"Camp {camp} assigné"})

        except Exception as exc:
            db.session.rollback()
            return jsonify({"success": False, "error": str(exc)}), 500

    @bp.route("/admin/camps/logs")
    @admins_only
    def camps_logs():
        """Page des logs des tentatives d'accès illégitimes."""
        logs = (
            CampAccessLog.query
            .order_by(CampAccessLog.timestamp.desc())
            .limit(MAX_LOGS_DISPLAYED)
            .all()
        )

        logs_data = []
        for log in logs:
            team = Teams.query.filter_by(id=log.team_id).first()
            challenge = Challenges.query.filter_by(id=log.challenge_id).first()
            logs_data.append({
                "id": log.id,
                "team_name": team.name if team else f"Team #{log.team_id}",
                "team_id": log.team_id,
                "team_camp": log.team_camp,
                "challenge_name": challenge.name if challenge else f"Challenge #{log.challenge_id}",
                "challenge_id": log.challenge_id,
                "challenge_camp": log.challenge_camp,
                "request_info": log.request_info or "",
                "timestamp": log.timestamp.strftime("%d/%m/%Y %H:%M:%S"),
            })

        stats = {
            "total": CampAccessLog.query.count(),
            "unique_teams": db.session.query(CampAccessLog.team_id).distinct().count(),
            "shown": len(logs_data),
        }

        return render_template("camps_logs.html", logs=logs_data, stats=stats)

    @bp.route("/admin/camps/logs/clear", methods=["POST"])
    @admins_only
    def clear_logs():
        """Supprime tous les logs."""
        try:
            CampAccessLog.query.delete()
            db.session.commit()
            return jsonify({"success": True, "message": "Logs supprimés"})
        except Exception as exc:
            db.session.rollback()
            return jsonify({"success": False, "error": str(exc)}), 500

    # ======================================================================
    #  ROUTES UTILISATEUR
    # ======================================================================

    @bp.route("/camps/select")
    @authed_only
    def select_camp_page():
        """Page de sélection de camp."""
        team = get_current_team()
        if not team:
            return "Vous devez être dans une équipe pour accéder à cette page", 403

        tc = TeamCamp.query.filter_by(team_id=team.id).first()
        current_camp = tc.camp if tc else None

        can_change, error_msg = can_change_camp(team.id)
        allow_change = get_config(CFG_ALLOW_CHANGE, default=True)
        show_public_stats = get_config(CFG_SHOW_PUBLIC_STATS, default=False)
        enable_team_limits = get_config(CFG_ENABLE_TEAM_LIMITS, default=False)

        # Statistiques
        stats = None
        if show_public_stats or enable_team_limits:
            blue_count = TeamCamp.query.filter_by(camp="blue").count()
            red_count = TeamCamp.query.filter_by(camp="red").count()
            stats = {
                "blue": blue_count,
                "red": red_count,
                "show_counts": show_public_stats,
                "show_limits": enable_team_limits,
            }
            if enable_team_limits:
                stats["blue_max"] = get_config(CFG_MAX_BLUE_TEAMS, default=0)
                stats["red_max"] = get_config(CFG_MAX_RED_TEAMS, default=0)

        can_join_blue, blue_error = can_join_camp("blue", team.id)
        can_join_red, red_error = can_join_camp("red", team.id)

        # Deadline formatée
        deadline_formatted = _format_deadline()

        return render_template(
            "camps_select.html",
            current_camp=current_camp,
            can_change=can_change,
            allow_change=allow_change,
            can_join_blue=can_join_blue,
            can_join_red=can_join_red,
            blue_error=blue_error,
            red_error=red_error,
            change_error=error_msg if not can_change else None,
            deadline=deadline_formatted,
            stats=stats,
        )

    @bp.route("/api/v1/camps/select", methods=["POST"])
    @authed_only
    def select_camp_api():
        """API pour sélectionner le camp de son équipe."""
        team = get_current_team()
        if not team:
            return jsonify({"success": False, "error": "Vous devez être dans une équipe"}), 403

        camp = (request.json or {}).get("camp")
        if camp not in VALID_CAMPS:
            return jsonify({"success": False, "error": "Camp invalide"}), 400

        can_change, error_msg = can_change_camp(team.id)
        if not can_change:
            return jsonify({"success": False, "error": error_msg}), 403

        can_join, join_error = can_join_camp(camp, team.id)
        if not can_join:
            return jsonify({"success": False, "error": join_error}), 403

        try:
            tc = TeamCamp.query.filter_by(team_id=team.id).first()
            if tc:
                old_camp = tc.camp
                tc.camp = camp
                message = f"Camp changé de {old_camp} vers {camp}"
            else:
                db.session.add(TeamCamp(team_id=team.id, camp=camp))
                message = f"Vous avez rejoint le camp {camp}"

            db.session.commit()
            logger.info("[CTFd Camps] Équipe %s → camp %s", team.name, camp)
            return jsonify({"success": True, "message": message})

        except Exception:
            db.session.rollback()
            logger.exception("[CTFd Camps] Erreur sélection camp")
            return jsonify({"success": False, "error": "Erreur lors de la sauvegarde"}), 500

    @bp.route("/api/v1/camps/challenges")
    @authed_only
    def get_challenges_with_camps():
        """API pour récupérer les challenges filtrés par camp."""
        team = get_current_team()
        if not team:
            return jsonify({"success": False, "error": "Vous devez être dans une équipe"}), 403

        tc = TeamCamp.query.filter_by(team_id=team.id).first()
        if not tc:
            return jsonify({"success": False, "error": "Vous devez choisir un camp"}), 403

        team_camp = tc.camp

        # Charger les camps en une requête
        camps_map = {cc.challenge_id: cc.camp for cc in ChallengeCamp.query.all()}

        challenges = Challenges.query.filter_by(state="visible").all()
        result = [
            {
                "id": ch.id,
                "name": ch.name,
                "category": ch.category,
                "value": ch.value,
                "camp": camps_map.get(ch.id),
                "type": ch.type,
                "state": ch.state,
            }
            for ch in challenges
            if camps_map.get(ch.id) is None or camps_map.get(ch.id) == team_camp
        ]

        return jsonify({"success": True, "data": result, "team_camp": team_camp})

    return bp


# ======================================================================
#  Fonctions utilitaires internes au blueprint
# ======================================================================

def _load_admin_config() -> dict:
    """Charge la configuration complète pour la page admin."""
    deadline_str = get_config(CFG_CHANGE_DEADLINE, default="")

    deadline_formatted = ""
    deadline_passed = False
    if deadline_str:
        try:
            deadline = datetime.fromisoformat(str(deadline_str))
            deadline_formatted = deadline.strftime("%Y-%m-%dT%H:%M")
            deadline_passed = datetime.now(timezone.utc) > deadline
        except (ValueError, TypeError):
            pass

    return {
        "allow_change": get_config(CFG_ALLOW_CHANGE, default=True),
        "show_public_stats": get_config(CFG_SHOW_PUBLIC_STATS, default=False),
        "show_challenge_badges": get_config(CFG_SHOW_CHALLENGE_BADGES, default=False),
        "enable_team_limits": get_config(CFG_ENABLE_TEAM_LIMITS, default=False),
        "max_blue_teams": get_config(CFG_MAX_BLUE_TEAMS, default=0),
        "max_red_teams": get_config(CFG_MAX_RED_TEAMS, default=0),
        "deadline": deadline_formatted,
        "deadline_passed": deadline_passed,
    }


def _format_deadline() -> str | None:
    """Formate la deadline pour affichage utilisateur."""
    deadline_str = get_config(CFG_CHANGE_DEADLINE, default="")
    if not deadline_str:
        return None
    try:
        deadline = datetime.fromisoformat(str(deadline_str))
        return deadline.strftime("%d/%m/%Y à %H:%M")
    except (ValueError, TypeError):
        return None
