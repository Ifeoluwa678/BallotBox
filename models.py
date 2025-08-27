from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db
from flask_login import UserMixin
import uuid

# -------------------
# User Model
# -------------------
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(50), nullable=False)

    # Relationship: one user (coordinator) can create many elections
    elections = db.relationship("Election", backref="creator", lazy=True)

    def set_password(self, password):
        self.password = generate_password_hash(password, method='pbkdf2:sha256')

    def check_password(self, password):
        return check_password_hash(self.password, password)


# Election Model
class Election(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    start_time = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    end_time = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    # Rename this to match your DB column
    coordinator_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    passcode = db.Column(db.String(50), nullable=False)

    # Relationships
    candidates = db.relationship("Candidate", backref="election", cascade="all, delete-orphan", lazy=True)
    voters = db.relationship("Voter", backref="election", cascade="all, delete-orphan", lazy=True)
    tokens = db.relationship("Token", backref="election", cascade="all, delete-orphan", lazy=True)
    votes = db.relationship("Vote", backref="election", cascade="all, delete-orphan", lazy=True)

# -------------------
# Candidate Model
# -------------------
class Candidate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    position = db.Column(db.String(100), nullable=False)
    bio = db.Column(db.Text, nullable=True)
    election_id = db.Column(db.Integer, db.ForeignKey('election.id'), nullable=False)

    votes = db.relationship("Vote", backref="candidate", cascade="all, delete-orphan", lazy=True)


# -------------------
# Vote Model
# -------------------
class Vote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    voter_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)   # if registered user
    candidate_id = db.Column(db.Integer, db.ForeignKey('candidate.id'), nullable=False)
    election_id = db.Column(db.Integer, db.ForeignKey('election.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('voter_id', 'election_id', name='_user_vote_once'),
    )


# -------------------
# Voter Model
# -------------------
class Voter(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    election_id = db.Column(db.Integer, db.ForeignKey('election.id'), nullable=False)

    # one voter → one token
    token = db.relationship("Token", backref="voter", uselist=False, lazy="joined")


# -------------------
# Token Model
# -------------------
class Token(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    election_id = db.Column(db.Integer, db.ForeignKey('election.id'), nullable=False)
    voter_id = db.Column(db.Integer, db.ForeignKey('voter.id'), nullable=False)
    is_used = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
