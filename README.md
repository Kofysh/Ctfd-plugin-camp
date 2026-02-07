# 🎯 CTFd Camps Plugin

Plugin CTFd pour créer un système de **camps adversaires** (Bleu vs Rouge) avec filtrage automatique des challenges, gestion des quotas et logs de sécurité.

---

## 📋 Fonctionnalités

### 🏕️ Système de Camps
- **2 camps adversaires** : Camp Bleu (Défenseurs) 🔵 et Camp Rouge (Attaquants) 🔴
- Assignation des challenges par camp (interface admin)
- **Challenges neutres** : visibles par tous les camps (aucun camp assigné)
- Page de sélection de camp pour les équipes (`/camps/select`)
- Badge visuel du camp actuel sur la page `/challenges`

### 🔒 Gestion des Restrictions
- **Deadline de changement** : bloquer les changements après une date limite
- **Verrouillage des camps** : empêcher tout changement une fois le camp choisi
- **Quotas par camp** : limiter le nombre d'équipes par camp (ex: max 10 équipes bleues)

### 🎨 Interface
- **Design adaptatif** : fonctionne en mode dark et light
- **Pastilles colorées** : affichage visuel des camps sur les challenges (optionnel)
- **Statistiques publiques** : affichage du nombre d'équipes par camp (optionnel)
- Interface admin complète dans `/admin/camps`

### 🔐 Sécurité
- **Filtrage automatique** : les équipes ne voient QUE les challenges de leur camp + challenges neutres
- **Protection API** : accès refusé (403 Forbidden) aux challenges des autres camps
- Vérification backend : impossible de contourner les restrictions via requêtes forgées
- **Logs de sécurité** : enregistrement des tentatives d'accès illégitimes avec IP, requête et timestamp
- **Validation stricte** : seulement 'blue' ou 'red' acceptés

---

## 📦 Installation

### 1. Télécharger le plugin

```bash
cd /opt/CTFd/CTFd/plugins
git clone https://github.com/votre-repo/ctfd-camps.git
```

### 2. Vérifier la structure

```
CTFd/plugins/ctfd-camps/
├── __init__.py
├── blueprint.py
├── models.py
├── patches/
│   └── admin.py
└── templates/
    ├── camps_admin.html
    ├── camps_logs.html
    └── camps_select.html
```

### 3. Redémarrer CTFd

```bash
docker-compose restart ctfd
# OU
sudo systemctl restart ctfd
```

### 4. Vérifier l'installation

Au démarrage, vous devriez voir dans les logs :
```
[CTFd Camps] ✅ Table challenge_camps créée !
[CTFd Camps] ✅ Table team_camps créée !
[CTFd Camps] ✅ Table camp_access_logs créée !
[CTFd Camps] Plugin chargé avec succès ! 🔥
```

---

## 🚀 Utilisation

### Configuration Admin

1. **Accéder à la page de configuration** : `/admin/camps`

2. **Options disponibles** :
   - ✅ **Autoriser le changement de camp** : permet aux équipes de changer de camp
   - ✅ **Afficher publiquement le nombre d'équipes par camp** : affiche les statistiques sur `/camps/select`
   - ✅ **Afficher les pastilles de camp sur les challenges** : ajoute des bulles 🔵/🔴 sur les cartes de challenges
   - ✅ **Limiter le nombre d'équipes par camp** : définir un quota max par camp
   - 📅 **Date limite de changement** : bloquer les changements après cette date

3. **Assigner les camps aux challenges** :
   - Lors de la création/modification d'un challenge
   - Colonne "Camp" visible dans `/admin/challenges`
   - Laisser vide = challenge neutre (visible pour les deux camps)

4. **Assigner les camps aux équipes** (optionnel) :
   - Colonne "Camp" visible dans `/admin/teams`
   - Les équipes peuvent choisir leur camp sur `/camps/select`

### Côté Équipes

1. **Choisir un camp** : `/camps/select`
   - Affiche les camps disponibles avec descriptions
   - Boutons grisés si camp complet ou changement bloqué
   - Confirmation avant validation

2. **Accéder aux challenges** : `/challenges`
   - Badge coloré indiquant le camp actuel
   - Bouton "Changer de camp" si autorisé
   - **Filtrage automatique** : seuls les challenges du camp + neutres sont visibles

3. **Restrictions** :
   - Redirection automatique vers `/camps/select` si aucun camp choisi
   - Impossible d'accéder aux challenges des autres camps (403 Forbidden)

### Logs de Sécurité

1. **Accéder aux logs** : `/admin/camps/logs`

2. **Informations enregistrées** :
   - Équipe ayant tenté l'accès
   - Challenge visé
   - Camps (équipe vs challenge)
   - Requête complète (méthode + URL)
   - Adresse IP
   - Date et heure

3. **Actions disponibles** :
   - Voir les détails d'une tentative (bouton "👁️ Voir requête")
   - Supprimer tous les logs
   - Les 100 dernières tentatives sont affichées

---

## 📁 Structure des Fichiers

### Fichiers Principaux

| Fichier | Description |
|---------|-------------|
| `__init__.py` | Point d'entrée du plugin, création des tables, hooks de filtrage |
| `blueprint.py` | Routes Flask (admin + user), API, logique métier |
| `models.py` | Modèles SQLAlchemy (ChallengeCamp, TeamCamp, CampAccessLog) |
| `patches/admin.py` | Modifications de l'interface admin (colonnes, templates) |

### Templates

| Template | Description |
|----------|-------------|
| `templates/camps_admin.html` | Interface admin de configuration des camps |
| `templates/camps_select.html` | Page de sélection de camp pour les équipes |
| `templates/camps_logs.html` | Page d'affichage des logs de sécurité |

### Base de Données

| Table | Description |
|-------|-------------|
| `challenge_camps` | Association challenge ↔ camp (blue/red/null) |
| `team_camps` | Association équipe ↔ camp (blue/red) |
| `camp_access_logs` | Logs des tentatives d'accès illégitimes |

---

## ⚙️ Configuration Avancée

### Désactiver le DROP de la table des logs

Par défaut, lors du développement, la table `camp_access_logs` est recréée à chaque redémarrage.

Pour **conserver les logs en production**, commentez ces lignes dans `__init__.py` :

```python
# DROP et recréer pour avoir la bonne taille de colonne (à utiliser seulement en cas de modification du modèle)
# print("[CTFd Camps] 🔨 DROP de la table camp_access_logs...")
# CampAccessLog.__table__.drop(db.engine)
# CampAccessLog.__table__.create(db.engine)
# print("[CTFd Camps] ✅ Table camp_access_logs recréée !")
```

### Personnaliser les Camps

Pour ajouter plus de camps ou changer les noms, modifiez :
- `blueprint.py` : logique de validation (`['blue', 'red']`)
- `templates/*.html` : labels et descriptions
- `models.py` : si vous changez les valeurs stockées en BDD

---

## Support

Pour toute question ou problème, ouvrez une [issue](https://github.com/HACK-OLYTE/Ctfd-plugin-camp/issues). <br>
Ou contactez nous sur le site de l'association Hack'olyte : [contact](https://hackolyte.fr/contact/).


## Contribuer

Les contributions sont les bienvenues !  
Vous pouvez :

- Signaler des bugs
- Proposer de nouvelles fonctionnalités
- Soumettre des pull requests


## Licences 

Ce plugin est sous licence [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/deed.fr).  
Merci de ne pas retirer le footer de chaque fichier HTML sans l'autorisation préalable de l'association Hack'olyte.
