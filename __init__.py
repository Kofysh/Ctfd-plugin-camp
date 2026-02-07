"""
CTFd Camps Plugin — Système de camps adversaires (Bleu vs Rouge).

Fonctionnalités :
  - Assignation des challenges et équipes à des camps
  - Filtrage automatique des challenges selon le camp
  - Gestion des quotas et deadlines
  - Logs des tentatives d'accès non autorisées

Auteur : Hack'olyte (https://hackolyte.fr)
"""

import logging
import os

import sqlalchemy as sa

from CTFd.models import db
from CTFd.plugins import register_plugin_assets_directory

from .blueprint import create_blueprint
from .hooks import register_hooks
from .models import CampAccessLog, ChallengeCamp, TeamCamp
from .patches.admin import apply_all_patches

logger = logging.getLogger("CTFdCamps")

_TABLES = [
    ("challenge_camps", ChallengeCamp),
    ("team_camps", TeamCamp),
    ("camp_access_logs", CampAccessLog),
]


def load(app):
    """Point d'entrée du plugin, appelé par CTFd au démarrage."""

    # 1. Création des tables
    _ensure_tables(app)

    # 2. Patches des templates admin
    apply_all_patches(app)

    # 3. Hooks (filtrage, redirection, injection JS, etc.)
    register_hooks(app)

    # 4. Enregistrement des assets
    plugin_dir = os.path.basename(os.path.dirname(os.path.realpath(__file__)))
    register_plugin_assets_directory(
        app,
        base_path=f"/plugins/{plugin_dir}/assets/",
        endpoint="camps_assets",
    )

    # 5. Blueprint (routes admin + user)
    app.register_blueprint(create_blueprint())

    logger.info("[CTFd Camps] Plugin chargé avec succès !")


def _ensure_tables(app):
    """Crée les tables manquantes dans la base de données."""
    with app.app_context():
        existing = set(sa.inspect(db.engine).get_table_names())

        for table_name, model in _TABLES:
            if table_name not in existing:
                logger.info("[CTFd Camps] Création de la table %s…", table_name)
                model.__table__.create(db.engine)
                logger.info("[CTFd Camps] Table %s créée.", table_name)
            else:
                logger.info("[CTFd Camps] Table %s déjà existante.", table_name)
