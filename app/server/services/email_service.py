import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List

class EmailService:
    @staticmethod
    def _send_email(to_email: str, subject: str, html_body: str):
        smtp_host = os.getenv("SMTP_HOST")
        smtp_port = int(os.getenv("SMTP_PORT", 587))
        smtp_user = os.getenv("SMTP_USER")
        smtp_pass = os.getenv("SMTP_PASSWORD")
        smtp_from = os.getenv("SMTP_FROM", "IT Asset System")

        if not all([smtp_host, smtp_user, smtp_pass]):
            print(f"⚠️ Email Not Sent: SMTP credentials missing in .env (Subject: {subject})")
            return

        msg = MIMEMultipart()
        msg["From"] = smtp_from
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(html_body, "html"))

        try:
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)
                print(f"📧 Email Sent to {to_email}: {subject}")
        except Exception as e:
            print(f"❌ Failed to send email to {to_email}: {str(e)}")

    @classmethod
    def notify_request_created(cls, employee_name: str, asset_name: str, manager_email: str):
        helpdesk_email = os.getenv("HELP_DESK_EMAIL")
        subject = f"New Asset Request: {asset_name} from {employee_name}"
        body = f"""
        <html>
            <body>
                <h2 style='color: #6366f1;'>New Asset Request</h2>
                <p><strong>Employee:</strong> {employee_name}</p>
                <p><strong>Asset Requested:</strong> {asset_name}</p>
                <p>Status: Awaiting Support Triage.</p>
                <hr>
                <p>Shared with Manager and IT Help Desk.</p>
            </body>
        </html>
        """
        if helpdesk_email:
            cls._send_email(helpdesk_email, subject, body)
        if manager_email:
            cls._send_email(manager_email, subject, body)

    @classmethod
    def notify_manager_approved(cls, employee_name: str, asset_name: str):
        helpdesk_email = os.getenv("HELP_DESK_EMAIL")
        subject = f"Work Start: {asset_name} for {employee_name} Approved"
        body = f"""
        <html>
            <body>
                <h2 style='color: #10b981;'>Request Approved by Manager</h2>
                <p><strong>Employee:</strong> {employee_name}</p>
                <p><strong>Asset:</strong> {asset_name}</p>
                <p>Please commence inventory check and fulfillment.</p>
            </body>
        </html>
        """
        if helpdesk_email:
            cls._send_email(helpdesk_email, subject, body)

    @classmethod
    def notify_asset_assigned(cls, employee_name: str, asset_name: str, manager_email: str):
        subject = f"Asset Assigned: {asset_name} to {employee_name}"
        body = f"""
        <html>
            <body>
                <h2 style='color: #6366f1;'>Asset Hand-over Complete</h2>
                <p>The requested <strong>{asset_name}</strong> has been successfully assigned to <strong>{employee_name}</strong>.</p>
                <p>Inventory records have been updated.</p>
            </body>
        </html>
        """
        if manager_email:
            cls._send_email(manager_email, subject, body)
