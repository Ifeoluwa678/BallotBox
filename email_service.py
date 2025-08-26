import os
import base64
from email.mime.text import MIMEText
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Gmail API scope: only sending emails
SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

def get_gmail_service():
    """Authenticate and return Gmail API service."""
    creds = None

    # token.json stores user access/refresh tokens
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    # If no valid credentials, login flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        # Save credentials for next runs
        with open("token.json", "w") as token:
            token.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)

def send_voting_email(recipient_email, voting_link, election_title, passcode, start_time, end_time):
    """
    Send a voting invitation email using Gmail API.
    """
    try:
        service = get_gmail_service()

        subject = f"Voting Invitation: {election_title}"
        body = f"""
        Hello,

        You have been invited to vote in the election: {election_title}.

        Election Passcode: {passcode}

        Voting starts: {start_time.strftime('%Y-%m-%d %H:%M')}
        Voting ends:   {end_time.strftime('%Y-%m-%d %H:%M')}

        Click the link below to cast your vote:
        {voting_link}

        Please note: this link is unique and can only be used once.

        Regards,  
        BallotBox Team
        """

        message = MIMEText(body)
        message["to"] = recipient_email
        message["subject"] = subject

        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

        service.users().messages().send(
            userId="me", body={"raw": raw_message}
        ).execute()

        print(f"✅ Email sent to {recipient_email}")
        return True

    except Exception as e:
        print(f"❌ Email sending error: {str(e)}")
        return False
