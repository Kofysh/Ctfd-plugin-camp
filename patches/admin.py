from CTFd.plugins import override_template
import re


def patch_admin_challenges_listing(app):
    """
    Ajoute la colonne "Camp" dans la liste des challenges de l'admin
    Patch: admin/challenges/challenges.html
    """
    
    # Récupérer le template original ou déjà overridé
    if 'admin/challenges/challenges.html' in app.overridden_templates:
        original = app.overridden_templates['admin/challenges/challenges.html']
    else:
        with open('/opt/CTFd/CTFd/themes/admin/templates/challenges/challenges.html', 'r') as f:
            original = f.read()
    
    # Ajouter la colonne "Camp" dans le header du tableau (avant "Category")
    match_header = re.search(r'<th class="sort-col"><b>Category</b></th>', original)
    if match_header:
        pos = match_header.start()
        original = original[:pos] + '<th class="sort-col"><b>Camp</b></th>' + original[pos:]
    
    # Ajouter la colonne "Camp" dans les lignes du tableau (avant "Category")
    match_column = re.search(r'<td>{{ challenge.category }}</td>', original)
    if match_column:
        pos = match_column.start()
        original = original[:pos] + '<td>{{ g.camps_map.get(challenge.id, "Non assigné") }}</td>' + original[pos:]
    
    # Override le template si les deux patchs ont réussi
    if match_header and match_column:
        override_template('admin/challenges/challenges.html', original)
        print("[CTFd Camps] ✅ Patch admin challenges listing appliqué")
    else:
        print("[CTFd Camps] ⚠️ Échec du patch admin challenges listing")


def patch_user_challenges_page(app):
    """
    Ajoute le badge de camp et le bouton "Changer de camp" sur la page /challenges
    Patch: challenges.html
    """
    
    try:
        # Récupérer le template original
        if 'challenges.html' in app.overridden_templates:
            original = app.overridden_templates['challenges.html']
        else:
            # Le template challenges.html est dans le thème actif
            theme = app.config.get('THEME_NAME', 'core')
            template_path = f'/opt/CTFd/CTFd/themes/{theme}/templates/challenges.html'
            with open(template_path, 'r') as f:
                original = f.read()
        
        # Chercher juste après le titre "Challenges" dans le jumbotron
        # Pattern : chercher </h1> dans le jumbotron
        match = re.search(r'(<h1[^>]*>.*?Challenges.*?</h1>)', original, re.DOTALL)
        
        if match:
            pos = match.end()
            # Insérer le badge de camp après le titre
            camp_badge = '''
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
'''
            original = original[:pos] + camp_badge + original[pos:]
            
            override_template('challenges.html', original)
            print("[CTFd Camps] ✅ Patch user challenges page appliqué")
        else:
            print("[CTFd Camps] ⚠️ Échec du patch user challenges page (titre non trouvé)")
    
    except Exception as e:
        print(f"[CTFd Camps] ⚠️ Erreur lors du patch user challenges: {e}")


def patch_admin_teams_listing(app):
    """
    Ajoute la colonne "Camp" dans la liste des équipes de l'admin
    Patch: admin/teams/teams.html
    """
    
    try:
        # Récupérer le template original ou déjà overridé
        if 'admin/teams/teams.html' in app.overridden_templates:
            original = app.overridden_templates['admin/teams/teams.html']
            print("[CTFd Camps DEBUG] Template déjà overridé trouvé")
        else:
            with open('/opt/CTFd/CTFd/themes/admin/templates/teams/teams.html', 'r') as f:
                original = f.read()
            print("[CTFd Camps DEBUG] Template lu depuis le filesystem")
        
        # Vérifier si le patch a déjà été appliqué
        camp_count = original.count('<b>Camp</b>')
        print(f"[CTFd Camps DEBUG] Nombre de '<b>Camp</b>' trouvés: {camp_count}")
        
        if '<b>Camp</b>' in original:
            print("[CTFd Camps] ℹ️ Patch admin teams déjà appliqué, ignoré")
            return
        
        # Ajouter la colonne "Camp" dans le header du tableau (avant "Hidden")
        match_header = re.search(r'<th class="sort-col text-center px-0"><b>Hidden</b></th>', original)
        if match_header:
            pos = match_header.start()
            print(f"[CTFd Camps DEBUG] Header trouvé à position {pos}")
            original = original[:pos] + '<th class="sort-col text-center"><b>Camp</b></th>\n\t\t\t\t\t\t' + original[pos:]
        else:
            print("[CTFd Camps DEBUG] Header NOT trouvé!")
        
        # Ajouter la colonne "Camp" dans les lignes du tableau (avant "Hidden")
        match_column = re.search(r'<td class="team-hidden d-md-table-cell d-lg-table-cell text-center"', original)
        if match_column:
            pos = match_column.start()
            print(f"[CTFd Camps DEBUG] Column trouvée à position {pos}")
            original = original[:pos] + '<td class="team-camp text-center">{{ g.teams_camps_map.get(team.id, "Non assigné") }}</td>\n\n\t\t\t\t\t\t' + original[pos:]
        else:
            print("[CTFd Camps DEBUG] Column NOT trouvée!")
        
        # Override le template si les deux patchs ont réussi
        if match_header and match_column:
            override_template('admin/teams/teams.html', original)
            print("[CTFd Camps] ✅ Patch admin teams listing appliqué")
        else:
            print("[CTFd Camps] ⚠️ Échec du patch admin teams listing")
    
    except Exception as e:
        print(f"[CTFd Camps] ⚠️ Erreur lors du patch admin teams: {e}")


def patch_create_challenge(app):
    """
    Ajoute le champ "Camp" dans le formulaire de création de challenge
    Patch: admin/challenges/create.html
    """
    
    # Récupérer le template original ou déjà overridé
    if 'admin/challenges/create.html' in app.overridden_templates:
        original = app.overridden_templates['admin/challenges/create.html']
    else:
        with open('/opt/CTFd/CTFd/themes/admin/templates/challenges/create.html', 'r') as f:
            original = f.read()
    
    # Insérer le champ "Camp" avant le bloc "category"
    match = re.search(r'{% block category %}', original)
    if match:
        pos = match.start()
        original = original[:pos] + """
    {% block camp %}
    <div class="form-group">
        <label>
            Camp:<br>
            <small class="form-text text-muted">
                Choisir le camp pour ce challenge
            </small>
        </label>
        <select class="form-control" name="camp" required>
            <option value="">-- Sélectionner un camp --</option>
            <option value="blue">🔵 Camp Bleu (Défenseurs)</option>
            <option value="red">🔴 Camp Rouge (Attaquants)</option>
        </select>
    </div>
    {% endblock %}
    """ + original[pos:]
        
        override_template('admin/challenges/create.html', original)
        print("[CTFd Camps] ✅ Patch create challenge appliqué")
    else:
        print("[CTFd Camps] ⚠️ Échec du patch create challenge")


def patch_update_challenge(app):
    """
    Ajoute le champ "Camp" dans le formulaire de modification de challenge
    Patch: admin/challenges/update.html
    """
    
    # Récupérer le template original ou déjà overridé
    if 'admin/challenges/update.html' in app.overridden_templates:
        original = app.overridden_templates['admin/challenges/update.html']
    else:
        with open('/opt/CTFd/CTFd/themes/admin/templates/challenges/update.html', 'r') as f:
            original = f.read()
    
    # Insérer le champ "Camp" avant le bloc "category"
    match = re.search(r'{% block category %}', original)
    if match:
        pos = match.start()
        original = original[:pos] + """
    {% block camp %}
    {% set challenge_camp = get_challenge_camp(challenge.id) %}
    <div class="form-group">
        <label>
            Camp<br>
            <small class="form-text text-muted">Camp du challenge</small>
        </label>
        <select class="form-control chal-camp" name="camp" required>
            <option value="">-- Sélectionner un camp --</option>
            <option value="blue" {% if challenge_camp == 'blue' %}selected{% endif %}>🔵 Camp Bleu (Défenseurs)</option>
            <option value="red" {% if challenge_camp == 'red' %}selected{% endif %}>🔴 Camp Rouge (Attaquants)</option>
        </select>
    </div>
    {% endblock %}
    """ + original[pos:]
        
        override_template('admin/challenges/update.html', original)
        print("[CTFd Camps] ✅ Patch update challenge appliqué")
    else:
        print("[CTFd Camps] ⚠️ Échec du patch update challenge")