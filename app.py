from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_migrate import Migrate
from datetime import datetime, timedelta
import uuid
import os
from dotenv import load_dotenv
from sqlalchemy.orm import joinedload
from flask_login import (
    LoginManager, login_user, current_user,
    login_required, logout_user
)

from extensions import db
from models import User, Election, Candidate, Vote, Voter, Token
from email_service import send_voting_email
from sqlalchemy import func
from flask_sqlalchemy import SQLAlchemy


# -------------------
# App Setup
# -------------------
load_dotenv()  # Must be first

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv("SECRET_KEY")
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("SQLALCHEMY_DATABASE_URI")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy()
# Init extensions
db.init_app(app)
migrate = Migrate(app, db)

# Initialize LoginManager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# -------------------
# Routes
# -------------------
@app.route('/')
def index():
    return render_template('index.html')


# Register
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email'].lower()
        password = request.form['password']
        role = request.form['role']

        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash("Email already registered.", "danger")
            return render_template('register.html', email=email, role=role)

        new_user = User(email=email, role=role)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()

        flash("Registration successful! Please login.", "success")
        return redirect(url_for('login'))

    return render_template('register.html')


# Login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].lower()
        password = request.form['password']
        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            login_user(user)
            flash("Login successful!", "success")
            return redirect(url_for('dashboard'))
        else:
            flash("Invalid credentials", "danger")

    return render_template('login.html')


# Dashboard (Coordinator only)
@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', user=current_user)


# Create Election
@app.route('/create_election', methods=['GET', 'POST'])
@login_required
def create_election():
    if current_user.role != 'coordinator':
        flash("Access denied. Coordinator role required.", "danger")
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        passcode = request.form['passcode']
        start_time = datetime.strptime(request.form['start_time'], '%Y-%m-%dT%H:%M')
        end_time = datetime.strptime(request.form['end_time'], '%Y-%m-%dT%H:%M')

        new_election = Election(
            title=title,
            description=description,
            start_time=start_time,
            end_time=end_time,
            created_by=current_user.id,
            is_active=True,
            passcode=passcode
        )
        db.session.add(new_election)
        db.session.commit()

        # Contestants
        contestant_names = request.form.getlist('contestant_names[]')
        contestant_positions = request.form.getlist('contestant_positions[]')

        for i in range(len(contestant_names)):
            if contestant_names[i].strip():
                new_contestant = Candidate(
                    name=contestant_names[i],
                    position=contestant_positions[i],
                    election_id=new_election.id
                )
                db.session.add(new_contestant)
        db.session.commit()

        # Voters + email sending
        voter_emails = request.form.getlist('voter_emails[]')
        voter_phones = request.form.getlist('voter_phones[]')

        for i in range(len(voter_emails)):
            if voter_emails[i].strip():
                new_voter = Voter(
                    email=voter_emails[i].lower(),
                    phone=voter_phones[i],
                    election_id=new_election.id
                )
                db.session.add(new_voter)
                db.session.commit()

                unique_token = str(uuid.uuid4())
                new_token = Token(
                    token=unique_token,
                    voter_id=new_voter.id,
                    election_id=new_election.id
                )
                db.session.add(new_token)
                db.session.commit()

                voting_link = f"{request.url_root}vote_with_token/{unique_token}"

                try:
                    success = send_voting_email(
                        recipient_email=new_voter.email,
                        voting_link=voting_link,
                        election_title=new_election.title,
                        passcode=passcode,
                        start_time=start_time,
                        end_time=end_time
                    )
                    if success:
                        flash(f"✓ Voting email sent to {new_voter.email}", "success")
                    else:
                        flash(f"✗ Failed to send email to {new_voter.email}", "warning")
                except Exception as e:
                    flash(f"Error sending email to {new_voter.email}: {str(e)}", "danger")

        flash("Election created successfully and voting links sent!", "success")
        return redirect(url_for('manage_elections'))

    return render_template('create_election.html', coordinator=current_user)


# Manage Elections
@app.route('/elections')
@login_required
def manage_elections():
    if current_user.role != 'coordinator':
        flash("Coordinator only.", "danger")
        return redirect(url_for('dashboard'))

    elections = Election.query.filter_by(created_by=current_user.id).all()
    return render_template('manage_elections.html', elections=elections)


# Delete Election
@app.route("/delete_election/<int:election_id>", methods=["POST"])
@login_required
def delete_election(election_id):
    election = Election.query.get_or_404(election_id)

    if election.created_by != current_user.id:
        flash("You are not authorized to delete this election.", "danger")
        return redirect(url_for("manage_elections"))

    Candidate.query.filter_by(election_id=election.id).delete()
    Voter.query.filter_by(election_id=election.id).delete()
    Token.query.filter_by(election_id=election.id).delete()

    db.session.delete(election)
    db.session.commit()

    flash("Election deleted successfully.", "success")
    return redirect(url_for("manage_elections"))


# Manage Candidates
@app.route('/election/<int:election_id>/candidates')
@login_required
def manage_candidates(election_id):
    election = Election.query.get_or_404(election_id)

    # Candidate list with vote counts
    candidates_with_votes = (
        db.session.query(
            Candidate.id,
            Candidate.name,
            Candidate.position,
            func.count(Vote.id).label("votes")
        )
        .outerjoin(Vote, Candidate.id == Vote.candidate_id)
        .filter(Candidate.election_id == election_id)
        .group_by(Candidate.id)
        .all()
    )

    # Total votes cast in this election
    total_votes = (
        db.session.query(func.count(Vote.id))
        .filter(Vote.election_id == election_id)
        .scalar()
    )

    # Total registered voters
    total_voters = (
        db.session.query(func.count(Voter.id))
        .filter(Voter.election_id == election_id)
        .scalar()
    )

    turnout_percentage = (
        (total_votes / total_voters * 100) if total_voters > 0 else 0
    )

    return render_template(
        "manage_candidates.html",
        election=election,
        candidates=candidates_with_votes,
        total_votes=total_votes,
        total_voters=total_voters,
        turnout_percentage=turnout_percentage
    )

# Add Voters
@app.route('/election/<int:election_id>/add_voters', methods=['GET', 'POST'])
@login_required
def add_voters(election_id):
    if current_user.role != "coordinator":
        flash("Access denied. Coordinator role required.", "danger")
        return redirect(url_for('dashboard'))

    election = Election.query.get_or_404(election_id)

    if request.method == 'POST':
        email = request.form['email'].lower()
        phone = request.form.get('phone', '')

        # Prevent duplicates
        existing_voter = Voter.query.filter_by(email=email, election_id=election.id).first()
        if existing_voter:
            flash("This voter is already registered for this election.", "warning")
            return redirect(url_for('add_voters', election_id=election.id))

        # Create new voter
        new_voter = Voter(email=email, phone=phone, election_id=election.id)
        db.session.add(new_voter)
        db.session.commit()

        # Generate unique token
        token_value = str(uuid.uuid4())
        new_token = Token(token=token_value, election_id=election.id, voter_id=new_voter.id)
        db.session.add(new_token)
        db.session.commit()

        # ✅ Send email when voter is added
        voting_link = f"{request.url_root}vote_with_token/{new_token.token}"
        try:
            success = send_voting_email(
                recipient_email=new_voter.email,
                voting_link=voting_link,
                election_title=election.title,
                passcode=election.passcode,
                start_time=election.start_time,
                end_time=election.end_time
            )
            if success:
                flash(f"✓ Voting email sent to {new_voter.email}", "success")
            else:
                flash(f"✗ Failed to send email to {new_voter.email}", "warning")
        except Exception as e:
            flash(f"Error sending email to {new_voter.email}: {str(e)}", "danger")

        return redirect(url_for('add_voters', election_id=election.id))

    voters = Voter.query.filter_by(election_id=election.id).options(db.joinedload(Voter.token)).all()
    return render_template('add_voters.html', election=election, voters=voters)

# Vote With Token
@app.route('/vote_with_token/<token>', methods=['GET', 'POST'])
def vote_with_token(token):
    # Find the token record
    token_record = Token.query.filter_by(token=token, is_used=False).first()
    if not token_record:
        flash("❌ Invalid or expired voting link.", "danger")
        return redirect(url_for('index'))

    election = Election.query.get_or_404(token_record.election_id)
    candidates = Candidate.query.filter_by(election_id=election.id).all()

    if request.method == 'POST':
        email = request.form['email'].lower()
        passcode = request.form['passcode']

        # ✅ Check passcode
        if passcode != election.passcode:
            flash("❌ Invalid election passcode.", "danger")
            return render_template("vote_with_token.html", election=election, token=token, candidates=candidates)

        # ✅ Check if email matches the assigned voter
        voter = Voter.query.filter_by(email=email, election_id=election.id).first()
        if not voter:
            flash("❌ This email is not registered for this election.", "danger")
            return render_template("vote_with_token.html", election=election, token=token, candidates=candidates)

        # ✅ Check if token already used
        if token_record.is_used:
            flash("⚠️ This voting link has already been used.", "warning")
            return render_template("vote_with_token.html", election=election, token=token, candidates=candidates)

        # ✅ Check if this voter has already voted (duplicate protection)
        existing_vote = Vote.query.filter_by(voter_id=voter.id, election_id=election.id).first()
        if existing_vote:
            flash("⚠️ You have already voted in this election.", "warning")
            return render_template("vote_with_token.html", election=election, token=token, candidates=candidates)

        # ✅ Save vote
        candidate_id = request.form['candidate']
        new_vote = Vote(
            voter_id=voter.id,
            candidate_id=candidate_id,
            election_id=election.id
        )

        db.session.add(new_vote)
        token_record.is_used = True  # Mark token as used
        db.session.commit()

        flash("✅ Your vote has been recorded successfully!", "success")
        return redirect(url_for("index"))

    return render_template("vote_with_token.html", election=election, token=token, candidates=candidates)


# Test Email
@app.route('/test_email/<email>')
def test_email(email):
    try:
        test_link = f"{request.url_root}vote_with_token/test123"
        test_title = "Test Election"
        test_passcode = "TEST123"
        start = datetime.now()
        end = start + timedelta(hours=24)

        success = send_voting_email(
            recipient_email=email,
            voting_link=test_link,
            election_title=test_title,
            passcode=test_passcode,
            start_time=start,
            end_time=end
        )
        if success:
            return f"✓ Test email sent to {email} successfully!"
        else:
            return f"✗ Failed to send test email to {email}"

    except Exception as e:
        return f"Error: {str(e)}"


# Logout
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash("Logged out.", "info")
    return redirect(url_for('index'))


# Privacy + Terms
@app.route("/privacy")
def privacy():
    return render_template("privacy.html")

@app.route("/terms")
def terms():
    return render_template("terms.html")


# -------------------
# Run
# -------------------
if __name__ == '__main__':
    app.run(debug=True)
