from CTFd.plugins import register_plugin_assets_directory, register_admin_plugin_menu_bar
from CTFd.models import db, Challenges
from flask import request, g, redirect, url_for, session
from CTFd.utils.config import get_config
from .blueprint import load_bp, can_change_camp
from .models import ChallengeCamp, TeamCamp, CampAccessLog
from .patches.admin import (
    patch_admin_challenges_listing,
    patch_admin_teams_listing,
    patch_user_challenges_page,
    patch_create_challenge,
    patch_update_challenge
)
from CTFd.utils.user import get_current_team, is_admin, get_ip
import os
import sqlalchemy as sa


def load(app):
    """
    Fonction principale de chargement du plugin CTFd Camps
    """
    
    # Créer les tables si elles n'existent pas
    with app.app_context():
        inspector = sa.inspect(db.engine)
        tables = inspector.get_table_names()
        
        # Table challenge_camps
        if 'challenge_camps' not in tables:
            print("[CTFd Camps] 🔨 Création de la table challenge_camps...")
            ChallengeCamp.__table__.create(db.engine)
            print("[CTFd Camps] ✅ Table challenge_camps créée !")
        else:
            print("[CTFd Camps] ℹ️ Table challenge_camps existe déjà")
        
        # Table team_camps
        if 'team_camps' not in tables:
            print("[CTFd Camps] 🔨 Création de la table team_camps...")
            TeamCamp.__table__.create(db.engine)
            print("[CTFd Camps] ✅ Table team_camps créée !")
        else:
            print("[CTFd Camps] ℹ️ Table team_camps existe déjà")
        
        # Table camp_access_logs
        if 'camp_access_logs' not in tables:
            print("[CTFd Camps] 🔨 Création de la table camp_access_logs...")
            CampAccessLog.__table__.create(db.engine)
            print("[CTFd Camps] ✅ Table camp_access_logs créée !")
        else:
            print("[CTFd Camps] ℹ️ Table camp_access_logs existe déjà")
            # DROP et recréer pour avoir la bonne taille de colonne (à utiliser seulement en cas de modification du modèle)
            # print("[CTFd Camps] 🔨 DROP de la table camp_access_logs...")
            # CampAccessLog.__table__.drop(db.engine)
            # CampAccessLog.__table__.create(db.engine)
            # print("[CTFd Camps] ✅ Table camp_access_logs recréée !")
    
    # Appliquer les patches admin
    patch_admin_challenges_listing(app)
    patch_admin_teams_listing(app)
    patch_user_challenges_page(app)
    patch_create_challenge(app)
    patch_update_challenge(app)
    
    # Hook pour vérifier que l'équipe a un camp avant d'accéder aux challenges
    @app.before_request
    def check_team_has_camp():
        """
        Vérifie que l'équipe a choisi un camp avant d'accéder aux challenges
        Redirige vers /camps/select si pas de camp
        """
        # Ignorer si admin
        if is_admin():
            return
        
        # Ignorer si c'est une route API, statique, ou admin
        if request.endpoint and (
            request.endpoint.startswith('api.') or
            request.endpoint.startswith('views.static') or
            request.endpoint.startswith('admin.')
        ):
            return
        
        # Ignorer si c'est déjà la page de sélection de camp
        if request.path.startswith('/camps/'):
            return
        
        # Vérifier uniquement pour la page /challenges
        if request.path == '/challenges' or request.path.startswith('/challenges/'):
            team = get_current_team()
            if team:
                # Vérifier si l'équipe a un camp
                team_camp = TeamCamp.query.filter_by(team_id=team.id).first()
                if not team_camp:
                    # Pas de camp assigné, rediriger
                    return redirect('/camps/select')
    
    # Hook pour filtrer les challenges selon le camp de l'équipe
    @app.after_request
    def filter_challenges_by_camp(response):
        """
        Filtre les challenges dans les réponses API selon le camp de l'équipe
        """
        # Debug : afficher l'endpoint
        if request.path.startswith('/api/v1/challenges'):
            print(f"[CTFd Camps DEBUG] API challenges détectée - path: {request.path}, endpoint: {request.endpoint}, status: {response.status_code}")
        
        # Ignorer si admin
        if is_admin():
            if request.path.startswith('/api/v1/challenges'):
                print(f"[CTFd Camps DEBUG] User is admin, pas de filtrage")
            return response
        
        # FILTRAGE 1 : Liste des challenges (/api/v1/challenges)
        if request.path == '/api/v1/challenges' and response.status_code == 200:
            print(f"[CTFd Camps DEBUG] Tentative de filtrage de la liste...")
            try:
                # Récupérer l'équipe et son camp
                team = get_current_team()
                if not team:
                    print(f"[CTFd Camps DEBUG] Pas d'équipe trouvée")
                    return response
                
                print(f"[CTFd Camps DEBUG] Équipe trouvée: {team.name} (ID: {team.id})")
                
                team_camp_entry = TeamCamp.query.filter_by(team_id=team.id).first()
                if not team_camp_entry:
                    print(f"[CTFd Camps DEBUG] Pas de camp assigné à l'équipe")
                    return response
                
                team_camp = team_camp_entry.camp
                print(f"[CTFd Camps DEBUG] Camp de l'équipe: {team_camp}")
                
                # Parser la réponse JSON
                import json
                data = json.loads(response.get_data(as_text=True))
                
                print(f"[CTFd Camps DEBUG] Données parsées, success: {data.get('success')}")
                
                if data.get('success') and 'data' in data:
                    original_count = len(data['data'])
                    print(f"[CTFd Camps DEBUG] Nombre de challenges avant filtrage: {original_count}")
                    
                    # Filtrer les challenges
                    filtered_challenges = []
                    for challenge in data['data']:
                        # Récupérer le camp du challenge
                        camp_entry = ChallengeCamp.query.filter_by(challenge_id=challenge['id']).first()
                        challenge_camp = camp_entry.camp if camp_entry else None
                        
                        print(f"[CTFd Camps DEBUG] Challenge {challenge['id']} ({challenge['name']}): camp={challenge_camp}")
                        
                        # Règles de visibilité :
                        # 1. Challenge sans camp (null) → Visible pour tous
                        # 2. Challenge avec le même camp que l'équipe → Visible
                        # 3. Challenge d'un autre camp → Masqué
                        if challenge_camp is None or challenge_camp == team_camp:
                            filtered_challenges.append(challenge)
                            print(f"[CTFd Camps DEBUG]   → VISIBLE")
                        else:
                            print(f"[CTFd Camps DEBUG]   → MASQUÉ")
                    
                    # Remplacer les données
                    data['data'] = filtered_challenges
                    
                    # Reconstruire la réponse
                    response.set_data(json.dumps(data))
                    
                    print(f"[CTFd Camps] ✅ Filtrage liste appliqué : {len(filtered_challenges)}/{original_count} challenges visibles pour le camp {team_camp}")
            
            except Exception as e:
                print(f"[CTFd Camps] ❌ Erreur lors du filtrage de la liste: {e}")
                import traceback
                traceback.print_exc()
        
        # FILTRAGE 2 : Challenge individuel (/api/v1/challenges/<id>)
        import re
        match = re.match(r'^/api/v1/challenges/(\d+)$', request.path)
        if match and response.status_code == 200:
            challenge_id = int(match.group(1))
            print(f"[CTFd Camps DEBUG] 🔒 Tentative d'accès au challenge {challenge_id}...")
            
            try:
                # Récupérer l'équipe et son camp
                team = get_current_team()
                if not team:
                    print(f"[CTFd Camps DEBUG] Pas d'équipe, accès refusé")
                    return response
                
                team_camp_entry = TeamCamp.query.filter_by(team_id=team.id).first()
                if not team_camp_entry:
                    print(f"[CTFd Camps DEBUG] Pas de camp assigné, accès refusé")
                    return response
                
                team_camp = team_camp_entry.camp
                
                # Vérifier le camp du challenge
                camp_entry = ChallengeCamp.query.filter_by(challenge_id=challenge_id).first()
                challenge_camp = camp_entry.camp if camp_entry else None
                
                print(f"[CTFd Camps DEBUG] Challenge {challenge_id}: camp={challenge_camp}, équipe: camp={team_camp}")
                
                # Si le challenge a un camp différent → BLOQUER
                if challenge_camp is not None and challenge_camp != team_camp:
                    print(f"[CTFd Camps] 🚨 ACCÈS REFUSÉ au challenge {challenge_id} (camp {challenge_camp}) pour l'équipe {team.name} (camp {team_camp})")
                    
                    # Logger la tentative
                    try:
                        request_info = f"{request.method} {request.url} (IP: {get_ip(req=request)})"
                        log_entry = CampAccessLog(
                            team_id=team.id,
                            challenge_id=challenge_id,
                            team_camp=team_camp,
                            challenge_camp=challenge_camp,
                            ip_address=request_info[:500]
                        )
                        db.session.add(log_entry)
                        db.session.commit()
                    except Exception as log_error:
                        print(f"[CTFd Camps] ⚠️ Erreur logging: {log_error}")
                        db.session.rollback()
                    
                    import json
                    response.set_data(json.dumps({
                        'success': False,
                        'error': 'Ce challenge n\'est pas accessible par votre camp'
                    }))
                    response.status_code = 403
                else:
                    print(f"[CTFd Camps] ✅ Accès autorisé au challenge {challenge_id}")
            
            except Exception as e:
                print(f"[CTFd Camps] ❌ Erreur lors du filtrage individuel: {e}")
                import traceback
                traceback.print_exc()
        
        return response
    
    # Context processor pour enrichir les challenges avec leur camp
    @app.context_processor
    def inject_camp_data():
        """
        Injecte les données de camp dans les templates
        Enrichit automatiquement les objets challenges avec leur camp
        """
        def get_challenge_camp(challenge_id):
            """Récupère le camp d'un challenge"""
            camp_entry = ChallengeCamp.query.filter_by(challenge_id=challenge_id).first()
            return camp_entry.camp if camp_entry else None
        
        def get_team_camp(team_id):
            """Récupère le camp d'une équipe"""
            camp_entry = TeamCamp.query.filter_by(team_id=team_id).first()
            return camp_entry.camp if camp_entry else None
        
        def can_change_camp_for_display():
            """Vérifie si on peut afficher le bouton changer de camp"""
            team = get_current_team()
            if not team:
                return False
            
            can_change, _ = can_change_camp(team.id)
            return can_change
        
        # Enrichir tous les challenges avec leur camp pour les templates
        def enrich_challenge(challenge):
            """Enrichit un challenge avec son camp"""
            if not hasattr(challenge, 'camp') or challenge.camp is None:
                camp_entry = ChallengeCamp.query.filter_by(challenge_id=challenge_id).first()
                challenge.camp = camp_entry.camp if camp_entry else None
            return challenge
        
        return dict(
            get_challenge_camp=get_challenge_camp,
            get_team_camp=get_team_camp,
            get_current_team=get_current_team,
            can_change_camp_for_display=can_change_camp_for_display,
            enrich_challenge=enrich_challenge
        )
    
    # Hook pour injecter le CSS/JS des pastilles de camp sur les challenges
    @app.after_request
    def inject_challenge_badges(response):
        """Injecte le JavaScript pour afficher les pastilles de camp sur les challenges"""
        
        # Vérifier si on est sur la page challenges et si l'option est activée
        if request.path == '/challenges' and response.status_code == 200:
            show_badges = get_config('camps_show_challenge_badges', default=False)
            
            if show_badges:
                # Récupérer les camps de tous les challenges
                from CTFd.models import Challenges as ChallengesModel
                challenges = ChallengesModel.query.filter_by(state='visible').all()
                
                camps_map = {}
                for challenge in challenges:
                    camp_entry = ChallengeCamp.query.filter_by(challenge_id=challenge.id).first()
                    if camp_entry:
                        camps_map[challenge.id] = camp_entry.camp
                
                # Injecter le script
                inject_script = f"""
<script>
(function() {{
    const campsMap = {camps_map};
    
    // Attendre que les challenges soient chargés
    function addCampBadges() {{
        document.querySelectorAll('.challenge-button[value]').forEach(button => {{
            const challengeId = parseInt(button.getAttribute('value'));
            const camp = campsMap[challengeId];
            
            if (camp && !button.querySelector('.camp-badge')) {{
                const badge = document.createElement('div');
                badge.className = 'camp-badge';
                badge.style.cssText = `
                    position: absolute;
                    bottom: 8px;
                    left: 8px;
                    width: 14px;
                    height: 14px;
                    border-radius: 50%;
                    background-color: ${{camp === 'blue' ? '#007bff' : '#dc3545'}};
                    border: 2px solid white;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.3);
                    z-index: 10;
                    pointer-events: none;
                `;
                badge.title = camp === 'blue' ? 'Camp Bleu' : 'Camp Rouge';
                
                // S'assurer que le bouton a position relative
                button.style.position = 'relative';
                button.appendChild(badge);
            }}
        }});
    }}
    
    // Ajouter les badges au chargement
    if (document.readyState === 'loading') {{
        document.addEventListener('DOMContentLoaded', addCampBadges);
    }} else {{
        addCampBadges();
    }}
    
    // Observer les changements (si challenges chargés dynamiquement)
    const observer = new MutationObserver(addCampBadges);
    observer.observe(document.body, {{ childList: true, subtree: true }});
    
    console.log('[CTFd Camps] Pastilles de camp injectées:', Object.keys(campsMap).length, 'challenges');
}})();
</script>
"""
                
                # Injecter avant </body>
                html = response.get_data(as_text=True)
                if '</body>' in html:
                    html = html.replace('</body>', inject_script + '</body>')
                    response.set_data(html)
        
        return response
    
    # Hook pour enrichir automatiquement tous les challenges avec leur camp
    @app.before_request
    def enrich_challenges_with_camp():
        """
        Enrichit les objets Challenge avec leur camp avant le rendu des templates
        """
        # Uniquement pour les pages admin challenges
        if request.endpoint and 'challenges' in str(request.endpoint):
            try:
                # Récupérer la correspondance challenge_id -> camp
                camps_map = {c.challenge_id: c.camp for c in ChallengeCamp.query.all()}
                
                # Injecter dans g pour utilisation ultérieure
                g.camps_map = camps_map
                
            except Exception as e:
                print(f"[CTFd Camps] ⚠️ Erreur lors de l'enrichissement: {e}")
                g.camps_map = {}
        
        # Enrichir les équipes avec leur camp pour la page admin teams
        if request.endpoint and 'teams' in str(request.endpoint):
            try:
                # Récupérer la correspondance team_id -> camp
                teams_camps_map = {tc.team_id: tc.camp for tc in TeamCamp.query.all()}
                
                # Injecter dans g pour utilisation ultérieure
                g.teams_camps_map = teams_camps_map
                
            except Exception as e:
                print(f"[CTFd Camps] ⚠️ Erreur lors de l'enrichissement teams: {e}")
                g.teams_camps_map = {}

    
    # Hook AVANT la requête API : extraire le camp et le stocker temporairement
    @app.before_request
    def extract_camp_from_request():
        """
        Extrait le champ 'camp' de la requête et le stocke dans g.camp_value
        pour éviter que CTFd n'essaie de le passer au modèle Challenges
        """
        if request.endpoint and 'api.challenges' in request.endpoint:
            if request.method in ['POST', 'PATCH']:
                # Extraire le camp depuis form ou JSON
                camp_value = None
                if request.form.get('camp'):
                    camp_value = request.form.get('camp')
                    # Créer une copie modifiable du form sans le champ camp
                    request.form = request.form.copy()
                    if 'camp' in request.form:
                        del request.form['camp']
                elif request.is_json and request.json and request.json.get('camp'):
                    camp_value = request.json.get('camp')
                    # Retirer le camp du JSON
                    if 'camp' in request.json:
                        del request.json['camp']
                
                # VALIDATION STRICTE : Seulement 'blue' ou 'red' acceptés
                if camp_value and camp_value in ['blue', 'red']:
                    g.camp_value = camp_value
                elif camp_value:
                    print(f"[CTFd Camps] ⚠️ Valeur de camp invalide rejetée : {camp_value}")
                    g.camp_value = None
                else:
                    g.camp_value = None
    
    # Hook APRÈS la requête : sauvegarder le camp dans notre table
    @app.after_request
    def save_challenge_camp(response):
        """
        Sauvegarde le camp dans la table challenge_camps après la création/modification
        """
        
        # Vérifier si on a un camp à sauvegarder
        if hasattr(g, 'camp_value') and g.camp_value:
            
            # Création de challenge (POST)
            if request.method == 'POST' and response.status_code in [200, 201]:
                try:
                    import json
                    response_data = json.loads(response.get_data(as_text=True))
                    challenge_id = response_data.get('data', {}).get('id')
                    
                    if challenge_id:
                        # Créer l'entrée dans challenge_camps
                        camp_entry = ChallengeCamp(
                            challenge_id=challenge_id,
                            camp=g.camp_value
                        )
                        db.session.add(camp_entry)
                        db.session.commit()
                        print(f"[CTFd Camps] ✅ Camp '{g.camp_value}' assigné au challenge {challenge_id}")
                except Exception as e:
                    print(f"[CTFd Camps] ⚠️ Erreur lors de la sauvegarde du camp: {e}")
                    db.session.rollback()
            
            # Modification de challenge (PATCH)
            elif request.method == 'PATCH' and response.status_code == 200:
                try:
                    challenge_id = request.view_args.get('challenge_id')
                    
                    if challenge_id:
                        # Vérifier si une entrée existe déjà
                        camp_entry = ChallengeCamp.query.filter_by(challenge_id=challenge_id).first()
                        
                        if camp_entry:
                            camp_entry.camp = g.camp_value
                        else:
                            camp_entry = ChallengeCamp(
                                challenge_id=challenge_id,
                                camp=g.camp_value
                            )
                            db.session.add(camp_entry)
                        
                        db.session.commit()
                        print(f"[CTFd Camps] ✅ Camp '{g.camp_value}' mis à jour pour le challenge {challenge_id}")
                except Exception as e:
                    print(f"[CTFd Camps] ⚠️ Erreur lors de la mise à jour du camp: {e}")
                    db.session.rollback()
        
        return response
    
    # Enregistrer le répertoire des assets
    dir_path = os.path.dirname(os.path.realpath(__file__))
    dir_name = os.path.basename(dir_path)
    register_plugin_assets_directory(
        app,
        base_path="/plugins/" + dir_name + "/assets/",
        endpoint="camps_assets"
    )
    
    # Charger et enregistrer le blueprint
    camps_bp = load_bp()
    app.register_blueprint(camps_bp)
    
    
    print("[CTFd Camps] Plugin chargé avec succès ! 🔥")