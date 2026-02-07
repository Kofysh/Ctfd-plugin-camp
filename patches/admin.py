"""
Patches des templates admin pour ajouter les colonnes et champs "Camp".
"""

import logging
import re

from flask import Flask

from CTFd.plugins import override_template

logger = logging.getLogger("CTFdCamps")

# Chemin de base des templates CTFd
_THEMES_BASE = "/opt/CTFd/CTFd/themes"


def apply_all_patches(app: Flask) -> None:
    """Applique tous les patches de templates."""
    _patch_challenges_listing(app)
    _patch_teams_listing(app)
    _patch_challenges_page(app)
    _patch_create_challenge(app)
    _patch_update_challenge(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_template(app: Flask, name: str, fallback_path: str) -> str | None:
    """Récupère le contenu d'un template (overridé ou depuis le filesystem)."""
    if name in app.overridden_templates:
        return app.overridden_templates[name]
    try:
        with open(fallback_path, "r") as f:
            return f.read()
    except FileNotFoundError:
        logger.warning("[CTFd Camps] Template introuvable: %s", fallback_path)
        return None


def _apply_patch(template_name: str, content: str, success: bool) -> None:
    """Applique un override de template si le patch a réussi."""
    if success:
        override_template(template_name, content)
        logger.info("[CTFd Camps] Patch appliqué: %s", template_name)
    else:
        logger.warning("[CTFd Camps] Échec du patch: %s", template_name)


# ---------------------------------------------------------------------------
# Patches
# ---------------------------------------------------------------------------

def _patch_challenges_listing(app: Flask) -> None:
    """Ajoute la colonne 'Camp' dans la liste admin des challenges."""
    tpl_name = "admin/challenges/challenges.html"
    content = _get_template(
        app, tpl_name,
        f"{_THEMES_BASE}/admin/templates/challenges/challenges.html",
    )
    if not content:
        return

    header = re.search(r'<th class="sort-col"><b>Category</b></th>', content)
    column = re.search(r"<td>{{ challenge.category }}</td>", content)

    if header:
        pos = header.start()
        content = content[:pos] + '<th class="sort-col"><b>Camp</b></th>' + content[pos:]

    # Recalculer après insertion
    column = re.search(r"<td>{{ challenge.category }}</td>", content)
    if column:
        pos = column.start()
        camp_cell = '<td>{{ g.camps_map.get(challenge.id, "Non assigné") }}</td>'
        content = content[:pos] + camp_cell + content[pos:]

    _apply_patch(tpl_name, content, bool(header and column))


def _patch_teams_listing(app: Flask) -> None:
    """Ajoute la colonne 'Camp' dans la liste admin des équipes."""
    tpl_name = "admin/teams/teams.html"
    content = _get_template(
        app, tpl_name,
        f"{_THEMES_BASE}/admin/templates/teams/teams.html",
    )
    if not content:
        return

    # Éviter de patcher deux fois
    if "<b>Camp</b>" in content:
        logger.info("[CTFd Camps] Patch teams déjà appliqué, ignoré")
        return

    header = re.search(
        r'<th class="sort-col text-center px-0"><b>Hidden</b></th>',
        content,
    )
    column = re.search(
        r'<td class="team-hidden d-md-table-cell d-lg-table-cell text-center"',
        content,
    )

    if header:
        pos = header.start()
        content = (
            content[:pos]
            + '<th class="sort-col text-center"><b>Camp</b></th>\n\t\t\t\t\t\t'
            + content[pos:]
        )

    # Recalculer après insertion
    column = re.search(
        r'<td class="team-hidden d-md-table-cell d-lg-table-cell text-center"',
        content,
    )
    if column:
        pos = column.start()
        camp_cell = (
            '<td class="team-camp text-center">'
            '{{ g.teams_camps_map.get(team.id, "Non assigné") }}</td>\n\n\t\t\t\t\t\t'
        )
        content = content[:pos] + camp_cell + content[pos:]

    _apply_patch(tpl_name, content, bool(header and column))


def _patch_challenges_page(app: Flask) -> None:
    """Ajoute le badge de camp et le bouton 'Changer de camp' sur /challenges."""
    tpl_name = "challenges.html"
    theme = app.config.get("THEME_NAME", "core")
    content = _get_template(
        app, tpl_name,
        f"{_THEMES_BASE}/{theme}/templates/challenges.html",
    )
    if not content:
        return

    match = re.search(r"(<h1[^>]*>.*?Challenges.*?</h1>)", content, re.DOTALL)
    if not match:
        logger.warning("[CTFd Camps] Titre Challenges non trouvé dans le template")
        return

    badge_html = """
            {% if session.get('id') %}
                {% set team = get_current_team() %}
                {% if team %}
                    {% set team_camp = get_team_camp(team.id) %}
                    {% if team_camp %}
                        <div class="mt-3">
                            <span class="badge badge-pill {% if team_camp == 'blue' %}badge-primary{% else %}badge-danger{% endif %} p-3" style="font-size: 1.1em;">
                                {% if team_camp == 'blue' %}
                                    🔵 Vous êtes dans le <strong>Camp Bleu</strong> (Défenseurs)
                                {% else %}
                                    🔴 Vous êtes dans le <strong>Camp Rouge</strong> (Attaquants)
                                {% endif %}
                            </span>
                            {% set can_change_camp_display = can_change_camp_for_display() %}
                            {% if can_change_camp_display %}
                                <a href="/camps/select" class="btn btn-sm btn-outline-light ml-2">🔄 Changer de camp</a>
                            {% endif %}
                        </div>
                    {% endif %}
                {% endif %}
            {% endif %}
"""
    pos = match.end()
    content = content[:pos] + badge_html + content[pos:]
    _apply_patch(tpl_name, content, True)


def _patch_create_challenge(app: Flask) -> None:
    """Ajoute le champ 'Camp' dans le formulaire de création de challenge."""
    tpl_name = "admin/challenges/create.html"
    content = _get_template(
        app, tpl_name,
        f"{_THEMES_BASE}/admin/templates/challenges/create.html",
    )
    if not content:
        return

    match = re.search(r"{% block category %}", content)
    if not match:
        _apply_patch(tpl_name, content, False)
        return

    camp_field = """
    {% block camp %}
    <div class="form-group">
        <label>
            Camp:<br>
            <small class="form-text text-muted">Choisir le camp pour ce challenge</small>
        </label>
        <select class="form-control" name="camp" required>
            <option value="">-- Sélectionner un camp --</option>
            <option value="blue">🔵 Camp Bleu (Défenseurs)</option>
            <option value="red">🔴 Camp Rouge (Attaquants)</option>
        </select>
    </div>
    {% endblock %}
    """
    pos = match.start()
    content = content[:pos] + camp_field + content[pos:]
    _apply_patch(tpl_name, content, True)


def _patch_update_challenge(app: Flask) -> None:
    """Ajoute le champ 'Camp' dans le formulaire de modification de challenge."""
    tpl_name = "admin/challenges/update.html"
    content = _get_template(
        app, tpl_name,
        f"{_THEMES_BASE}/admin/templates/challenges/update.html",
    )
    if not content:
        return

    match = re.search(r"{% block category %}", content)
    if not match:
        _apply_patch(tpl_name, content, False)
        return

    camp_field = """
    {% block camp %}
    {% set challenge_camp = get_challenge_camp(challenge.id) %}
    <div class="form-group">
        <label>
            Camp:<br>
            <small class="form-text text-muted">Camp du challenge</small>
        </label>
        <select class="form-control chal-camp" name="camp" required>
            <option value="">-- Sélectionner un camp --</option>
            <option value="blue" {% if challenge_camp == 'blue' %}selected{% endif %}>🔵 Camp Bleu (Défenseurs)</option>
            <option value="red" {% if challenge_camp == 'red' %}selected{% endif %}>🔴 Camp Rouge (Attaquants)</option>
        </select>
    </div>
    {% endblock %}
    """
    pos = match.start()
    content = content[:pos] + camp_field + content[pos:]
    _apply_patch(tpl_name, content, True)
