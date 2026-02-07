"""
Modèles SQLAlchemy du plugin CTFd Camps.
"""

from datetime import datetime, timezone

from CTFd.models import db


class ChallengeCamp(db.Model):
    """Association entre un challenge et un camp (Bleu ou Rouge)."""

    __tablename__ = "challenge_camps"

    id = db.Column(db.Integer, primary_key=True)
    challenge_id = db.Column(
        db.Integer,
        db.ForeignKey("challenges.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    camp = db.Column(db.String(10), nullable=False)  # "blue" | "red"

    challenge = db.relationship("Challenges", foreign_keys=[challenge_id], lazy="select")

    def __repr__(self):
        return f"<ChallengeCamp challenge_id={self.challenge_id} camp={self.camp}>"


class TeamCamp(db.Model):
    """Association entre une équipe et un camp (Bleu ou Rouge)."""

    __tablename__ = "team_camps"

    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(
        db.Integer,
        db.ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    camp = db.Column(db.String(10), nullable=False)  # "blue" | "red"

    team = db.relationship("Teams", foreign_keys=[team_id], lazy="select")

    def __repr__(self):
        return f"<TeamCamp team_id={self.team_id} camp={self.camp}>"


class CampAccessLog(db.Model):
    """Log des tentatives d'accès aux challenges d'un autre camp."""

    __tablename__ = "camp_access_logs"

    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(
        db.Integer,
        db.ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
    )
    challenge_id = db.Column(
        db.Integer,
        db.ForeignKey("challenges.id", ondelete="CASCADE"),
        nullable=False,
    )
    team_camp = db.Column(db.String(10), nullable=False)
    challenge_camp = db.Column(db.String(10), nullable=False)
    request_info = db.Column(db.String(500))  # "METHOD URL (IP: x.x.x.x)"
    timestamp = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
    )

    team = db.relationship("Teams", foreign_keys=[team_id], lazy="select")
    challenge = db.relationship("Challenges", foreign_keys=[challenge_id], lazy="select")

    def __repr__(self):
        return f"<CampAccessLog team={self.team_id} challenge={self.challenge_id}>"
