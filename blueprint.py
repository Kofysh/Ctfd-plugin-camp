from flask import Blueprint, render_template, request, jsonify, redirect, url_for, session
from CTFd.models import db, Teams, Challenges
from CTFd.utils.decorators import admins_only, authed_only
from CTFd.utils.config import get_config
from CTFd.utils.user import get_current_team
from CTFd.cache import clear_config
from datetime import datetime, timezone
from .models import TeamCamp, ChallengeCamp, CampAccessLog


def set_config(key, value):
    """Helper pour sauvegarder une config"""
    from CTFd.models import Configs
    
    config = Configs.query.filter_by(key=key).first()
    if config:
        config.value = value
    else:
        config = Configs(key=key, value=value)
        db.session.add(config)
    
    db.session.commit()
    clear_config()  # Vider le cache


def can_change_camp(team_id):
    """
    Vérifie si une équipe peut changer de camp
    Retourne (bool, str) : (peut_changer, raison_si_non)
    """
    # 1. Vérifier la deadline
    deadline_str = get_config('camps_change_deadline', default='')
    print(f"[CTFd Camps DEBUG] deadline_str from config: '{deadline_str}' (type: {type(deadline_str)})")
    
    if deadline_str:
        try:
            deadline = datetime.fromisoformat(deadline_str)
            now = datetime.now(timezone.utc)  # Utiliser UTC pour la comparaison
            print(f"[CTFd Camps DEBUG] Deadline: {deadline}, Now: {now}, Passed: {now > deadline}")
            
            if now > deadline:
                return False, "La date limite de changement de camp est dépassée"
        except Exception as e:
            print(f"[CTFd Camps DEBUG] Erreur parsing deadline: {e}")
            pass
    else:
        print(f"[CTFd Camps DEBUG] Pas de deadline configurée")
    
    # 2. Vérifier si le changement est autorisé
    allow_change = get_config('camps_allow_change', default=True)
    print(f"[CTFd Camps DEBUG] allow_change: {allow_change} (type: {type(allow_change)})")
    
    if not allow_change:
        # Si désactivé, on ne peut changer que si on n'a pas encore de camp
        team_camp = TeamCamp.query.filter_by(team_id=team_id).first()
        if team_camp:
            return False, "Le changement de camp est désactivé. Votre choix est définitif."
    
    return True, "OK"


def can_join_camp(camp, current_team_id=None):
    """
    Vérifie si une équipe peut rejoindre un camp spécifique
    Prend en compte les limites de places
    current_team_id : ID de l'équipe actuelle (pour ne pas se compter elle-même si elle change)
    Retourne (bool, str) : (peut_rejoindre, raison_si_non)
    """
    # Vérifier si les limites sont activées
    enable_limits = get_config('camps_enable_team_limits', default=False)
    if not enable_limits:
        return True, ""
    
    # Récupérer la limite pour ce camp
    if camp == 'blue':
        max_teams = get_config('camps_max_blue_teams', default=0)
    elif camp == 'red':
        max_teams = get_config('camps_max_red_teams', default=0)
    else:
        return False, "Camp invalide"
    
    # 0 = illimité
    if max_teams == 0:
        return True, ""
    
    # Compter le nombre d'équipes actuelles dans ce camp
    current_count = TeamCamp.query.filter_by(camp=camp).count()
    
    # Si l'équipe change de camp (elle est déjà dans un camp), ne pas se compter
    if current_team_id:
        team_camp = TeamCamp.query.filter_by(team_id=current_team_id).first()
        if team_camp and team_camp.camp == camp:
            # L'équipe est déjà dans ce camp, pas de problème
            return True, ""
    
    # Vérifier si le camp est plein
    if current_count >= max_teams:
        camp_name = "Bleu" if camp == 'blue' else "Rouge"
        return False, f"Le camp {camp_name} est complet ({current_count}/{max_teams} équipes)"
    
    return True, ""


def load_bp():
    """
    Créer et retourner le blueprint pour le plugin Camps
    """
    camps_bp = Blueprint(
        'camps',
        __name__,
        template_folder='templates',
        static_folder='assets'
    )
    
    # ========== ROUTES ADMIN ==========
    
    @camps_bp.route('/admin/camps')
    @admins_only
    def camps_admin():
        """Page principale d'administration des camps"""
        
        # Récupérer toutes les équipes avec leur camp
        teams = Teams.query.all()
        teams_data = []
        
        for team in teams:
            team_camp = TeamCamp.query.filter_by(team_id=team.id).first()
            teams_data.append({
                'id': team.id,
                'name': team.name,
                'camp': team_camp.camp if team_camp else None
            })
        
        # Calculer les statistiques
        blue_count = TeamCamp.query.filter_by(camp='blue').count()
        red_count = TeamCamp.query.filter_by(camp='red').count()
        unassigned_count = len(teams) - blue_count - red_count
        
        stats = {
            'blue': blue_count,
            'red': red_count,
            'unassigned': unassigned_count,
            'total': len(teams)
        }
        
        # Récupérer la configuration
        allow_change = get_config('camps_allow_change', default=True)
        show_public_stats = get_config('camps_show_public_stats', default=False)
        show_challenge_badges = get_config('camps_show_challenge_badges', default=False)
        enable_team_limits = get_config('camps_enable_team_limits', default=False)
        max_blue_teams = get_config('camps_max_blue_teams', default=0)
        max_red_teams = get_config('camps_max_red_teams', default=0)
        deadline_str = get_config('camps_change_deadline', default='')
        
        # Formatter la deadline pour l'input datetime-local
        deadline_formatted = ''
        if deadline_str:
            try:
                deadline = datetime.fromisoformat(deadline_str)
                deadline_formatted = deadline.strftime('%Y-%m-%dT%H:%M')
            except:
                pass
        
        # Vérifier si la deadline est dépassée
        deadline_passed = False
        if deadline_str:
            try:
                deadline = datetime.fromisoformat(deadline_str)
                deadline_passed = datetime.now() > deadline
            except:
                pass
        
        config = {
            'allow_change': allow_change,
            'show_public_stats': show_public_stats,
            'show_challenge_badges': show_challenge_badges,
            'enable_team_limits': enable_team_limits,
            'max_blue_teams': max_blue_teams,
            'max_red_teams': max_red_teams,
            'deadline': deadline_formatted,
            'deadline_passed': deadline_passed
        }
        
        return render_template('camps_admin.html', teams=teams_data, stats=stats, config=config)
    
    @camps_bp.route('/admin/camps/config', methods=['POST'])
    @admins_only
    def update_config():
        """Mettre à jour la configuration du système de camps"""
        
        try:
            allow_change = request.json.get('allow_change', True)
            show_public_stats = request.json.get('show_public_stats', False)
            show_challenge_badges = request.json.get('show_challenge_badges', False)
            enable_team_limits = request.json.get('enable_team_limits', False)
            max_blue_teams = request.json.get('max_blue_teams', 0)
            max_red_teams = request.json.get('max_red_teams', 0)
            deadline = request.json.get('deadline', '')  
            
            # La deadline arrive au format ISO depuis le frontend
            # On la stocke telle quelle
            if deadline:
                try:
                    # Vérifier que c'est un format valide
                    datetime.fromisoformat(deadline.replace('Z', '+00:00'))
                except Exception as e:
                    print(f"[CTFd Camps] Erreur validation deadline: {e}")
                    return jsonify({'success': False, 'error': 'Format de date invalide'}), 400
            
            # Sauvegarder la configuration
            set_config('camps_allow_change', allow_change)
            set_config('camps_show_public_stats', show_public_stats)
            set_config('camps_show_challenge_badges', show_challenge_badges)
            set_config('camps_enable_team_limits', enable_team_limits)
            set_config('camps_max_blue_teams', int(max_blue_teams))
            set_config('camps_max_red_teams', int(max_red_teams))
            set_config('camps_change_deadline', deadline)
            
            print(f"[CTFd Camps] Configuration sauvegardée")
            
            return jsonify({'success': True, 'message': 'Configuration mise à jour'})
            
        except Exception as e:
            print(f"[CTFd Camps] Erreur lors de la sauvegarde: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @camps_bp.route('/admin/camps/team/<int:team_id>', methods=['POST'])
    @admins_only
    def update_team_camp(team_id):
        """Mettre à jour le camp d'une équipe (admin)"""
        
        # Validation de sécurité : seulement 'blue', 'red', ou 'none'
        camp = request.json.get('camp')
        if camp not in ['blue', 'red', 'none', None]:
            return jsonify({'success': False, 'error': 'Camp invalide'}), 400
        
        # Vérifier que l'équipe existe
        team = Teams.query.filter_by(id=team_id).first()
        if not team:
            return jsonify({'success': False, 'error': 'Équipe introuvable'}), 404
        
        try:
            # Si camp = 'none', supprimer l'entrée
            if camp == 'none' or camp is None:
                TeamCamp.query.filter_by(team_id=team_id).delete()
                db.session.commit()
                return jsonify({'success': True, 'message': 'Camp retiré'})
            
            # Sinon, créer ou mettre à jour
            team_camp = TeamCamp.query.filter_by(team_id=team_id).first()
            if team_camp:
                team_camp.camp = camp
            else:
                team_camp = TeamCamp(team_id=team_id, camp=camp)
                db.session.add(team_camp)
            
            db.session.commit()
            return jsonify({'success': True, 'message': f'Camp {camp} assigné'})
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @camps_bp.route('/admin/camps/logs')
    @admins_only
    def camps_logs():
        """Page des logs des tentatives d'accès illégitimes"""
        
        # Récupérer tous les logs, triés par date décroissante
        logs = CampAccessLog.query.order_by(CampAccessLog.timestamp.desc()).limit(100).all()
        
        # Enrichir avec les noms
        logs_data = []
        for log in logs:
            team = Teams.query.filter_by(id=log.team_id).first()
            challenge = Challenges.query.filter_by(id=log.challenge_id).first()
            
            logs_data.append({
                'id': log.id,
                'team_name': team.name if team else f'Team #{log.team_id}',
                'team_id': log.team_id,
                'team_camp': log.team_camp,
                'challenge_name': challenge.name if challenge else f'Challenge #{log.challenge_id}',
                'challenge_id': log.challenge_id,
                'challenge_camp': log.challenge_camp,
                'request_info': log.ip_address or '',  # Contient METHOD URL (IP: xxx)
                'timestamp': log.timestamp.strftime('%d/%m/%Y %H:%M:%S')
            })
        
        # Statistiques
        total_attempts = CampAccessLog.query.count()
        unique_teams = db.session.query(CampAccessLog.team_id).distinct().count()
        
        stats = {
            'total': total_attempts,
            'unique_teams': unique_teams,
            'shown': len(logs_data)
        }
        
        return render_template('camps_logs.html', logs=logs_data, stats=stats)
    
    @camps_bp.route('/admin/camps/logs/clear', methods=['POST'])
    @admins_only
    def clear_logs():
        """Supprimer tous les logs"""
        try:
            CampAccessLog.query.delete()
            db.session.commit()
            return jsonify({'success': True, 'message': 'Logs supprimés'})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': str(e)}), 500
    
    # ========== ROUTES USER ==========
    
    @camps_bp.route('/camps/select')
    @authed_only
    def select_camp_page():
        """Page de sélection de camp pour les équipes"""
        
        # Récupérer l'équipe actuelle
        team = get_current_team()
        if not team:
            return "Vous devez être dans une équipe pour accéder à cette page", 403
        
        # Récupérer le camp actuel
        team_camp = TeamCamp.query.filter_by(team_id=team.id).first()
        current_camp = team_camp.camp if team_camp else None
        
        # Vérifier si le changement est possible
        can_change, error_msg = can_change_camp(team.id)
        
        # Récupérer la configuration
        allow_change = get_config('camps_allow_change', default=True)
        show_public_stats = get_config('camps_show_public_stats', default=False)
        enable_team_limits = get_config('camps_enable_team_limits', default=False)
        
        # Récupérer les statistiques si l'une des options est activée
        stats = None
        if show_public_stats or enable_team_limits:
            blue_count = TeamCamp.query.filter_by(camp='blue').count()
            red_count = TeamCamp.query.filter_by(camp='red').count()
            
            stats = {
                'blue': blue_count,
                'red': red_count,
                'show_counts': show_public_stats,  # Afficher les compteurs seulement si activé
                'show_limits': enable_team_limits   # Afficher les limites seulement si activé
            }
            
            # Ajouter les limites si activées
            if enable_team_limits:
                stats['blue_max'] = get_config('camps_max_blue_teams', default=0)
                stats['red_max'] = get_config('camps_max_red_teams', default=0)
        
        # Vérifier si les camps sont disponibles
        can_join_blue, blue_error = can_join_camp('blue', team.id)
        can_join_red, red_error = can_join_camp('red', team.id)
        
        # Récupérer la deadline
        deadline_str = get_config('camps_change_deadline', default='')
        deadline_formatted = None
        if deadline_str:
            try:
                deadline = datetime.fromisoformat(deadline_str)
                deadline_formatted = deadline.strftime('%d/%m/%Y à %H:%M')
            except:
                pass
        
        return render_template(
            'camps_select.html',
            current_camp=current_camp,
            can_change=can_change,
            allow_change=allow_change,
            can_join_blue=can_join_blue,
            can_join_red=can_join_red,
            blue_error=blue_error,
            red_error=red_error,
            change_error=error_msg if not can_change else None,
            deadline=deadline_formatted,
            stats=stats
        )
    
    @camps_bp.route('/api/v1/camps/select', methods=['POST'])
    @authed_only
    def select_camp_api():
        """API pour sélectionner le camp de son équipe"""
        
        # Récupérer l'équipe actuelle
        team = get_current_team()
        if not team:
            return jsonify({'success': False, 'error': 'Vous devez être dans une équipe'}), 403
        
        # Validation de sécurité : seulement 'blue' ou 'red'
        camp = request.json.get('camp')
        if camp not in ['blue', 'red']:
            return jsonify({'success': False, 'error': 'Camp invalide'}), 400
        
        # Vérifier si le changement est possible
        can_change, error_msg = can_change_camp(team.id)
        if not can_change:
            return jsonify({'success': False, 'error': error_msg}), 403
        
        # Vérifier si le camp n'est pas plein
        can_join, join_error = can_join_camp(camp, team.id)
        if not can_join:
            return jsonify({'success': False, 'error': join_error}), 403
        
        try:
            # Créer ou mettre à jour le camp
            team_camp = TeamCamp.query.filter_by(team_id=team.id).first()
            if team_camp:
                old_camp = team_camp.camp
                team_camp.camp = camp
                message = f'Camp changé de {old_camp} vers {camp}'
            else:
                team_camp = TeamCamp(team_id=team.id, camp=camp)
                db.session.add(team_camp)
                message = f'Vous avez rejoint le camp {camp}'
            
            db.session.commit()
            
            print(f"[CTFd Camps] Équipe {team.name} (ID: {team.id}) a choisi le camp {camp}")
            
            return jsonify({'success': True, 'message': message})
            
        except Exception as e:
            db.session.rollback()
            print(f"[CTFd Camps] Erreur lors de la sélection de camp: {e}")
            return jsonify({'success': False, 'error': 'Erreur lors de la sauvegarde'}), 500
    
    @camps_bp.route('/api/v1/camps/challenges')
    @authed_only
    def get_challenges_with_camps():
        """
        API pour récupérer les challenges filtrés selon le camp de l'équipe
        - Challenges avec camp = camp de l'équipe → Visibles
        - Challenges sans camp (null) → Visibles pour tous (challenges neutres)
        - Challenges d'un autre camp → Masqués
        """
        from CTFd.models import Challenges
        from .models import ChallengeCamp
        
        # Récupérer l'équipe et son camp
        team = get_current_team()
        if not team:
            return jsonify({'success': False, 'error': 'Vous devez être dans une équipe'}), 403
        
        team_camp_entry = TeamCamp.query.filter_by(team_id=team.id).first()
        team_camp = team_camp_entry.camp if team_camp_entry else None
        
        if not team_camp:
            return jsonify({'success': False, 'error': 'Vous devez choisir un camp'}), 403
        
        # Récupérer tous les challenges visibles
        challenges = Challenges.query.filter_by(state='visible').all()
        
        # Filtrer et enrichir avec les camps
        result = []
        for challenge in challenges:
            camp_entry = ChallengeCamp.query.filter_by(challenge_id=challenge.id).first()
            challenge_camp = camp_entry.camp if camp_entry else None
            
            # Règles de visibilité :
            # 1. Challenge sans camp (null) → Visible pour tous
            # 2. Challenge avec le même camp que l'équipe → Visible
            # 3. Challenge d'un autre camp → Masqué
            if challenge_camp is None or challenge_camp == team_camp:
                result.append({
                    'id': challenge.id,
                    'name': challenge.name,
                    'category': challenge.category,
                    'value': challenge.value,
                    'camp': challenge_camp,
                    'type': challenge.type,
                    'state': challenge.state
                })
        
        return jsonify({
            'success': True,
            'data': result,
            'team_camp': team_camp
        })
    
    return camps_bp