from CTFd.models import db
from datetime import datetime


class ChallengeCamp(db.Model):
    """
    Modèle pour associer un challenge à un camp (Bleu ou Rouge)
    """
    __tablename__ = 'challenge_camps'
    
    id = db.Column(db.Integer, primary_key=True)
    challenge_id = db.Column(
        db.Integer, 
        db.ForeignKey('challenges.id', ondelete='CASCADE'),
        nullable=False,
        unique=True  # Un challenge ne peut être que dans un seul camp
    )
    camp = db.Column(db.String(80), nullable=False)  # "blue" ou "red"
    
    # Relation vers le challenge
    challenge = db.relationship('Challenges', foreign_keys=[challenge_id], lazy='select')
    
    def __repr__(self):
        return f'<ChallengeCamp challenge_id={self.challenge_id} camp={self.camp}>'


class TeamCamp(db.Model):
    """
    Modèle pour associer une équipe à un camp (Bleu ou Rouge)
    """
    __tablename__ = 'team_camps'
    
    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(
        db.Integer,
        db.ForeignKey('teams.id', ondelete='CASCADE'),
        nullable=False,
        unique=True  # Une équipe ne peut être que dans un seul camp
    )
    camp = db.Column(db.String(80), nullable=False)  # "blue" ou "red"
    
    # Relation vers l'équipe
    team = db.relationship('Teams', foreign_keys=[team_id], lazy='select')
    
    def __repr__(self):
        return f'<TeamCamp team_id={self.team_id} camp={self.camp}>'


class CampAccessLog(db.Model):
    """
    Log des tentatives d'accès aux challenges d'autres camps
    Permet de détecter les équipes qui tentent de contourner le système
    """
    __tablename__ = 'camp_access_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey('teams.id', ondelete='CASCADE'), nullable=False)
    challenge_id = db.Column(db.Integer, db.ForeignKey('challenges.id', ondelete='CASCADE'), nullable=False)
    team_camp = db.Column(db.String(10), nullable=False)  # Camp de l'équipe
    challenge_camp = db.Column(db.String(10), nullable=False)  # Camp du challenge
    ip_address = db.Column(db.String(50))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relations
    team = db.relationship('Teams', foreign_keys=[team_id], lazy='select')
    challenge = db.relationship('Challenges', foreign_keys=[challenge_id], lazy='select')
    
    def __repr__(self):
        return f'<CampAccessLog team={self.team_id} challenge={self.challenge_id} at {self.timestamp}>'