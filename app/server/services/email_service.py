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
        hr_email = os.getenv("HR_EMAIL")
        subject = f"New Asset Request: {asset_name} from {employee_name}"
        body = f"""
        <html>
            <body>
                <h2 style='color: #6366f1;'>New Asset Request</h2>
                <p><strong>Employee:</strong> {employee_name}</p>
                <p><strong>Asset Requested:</strong> {asset_name}</p>
                <p><strong>Status:</strong> Pending HR Verification.</p>
                <hr>
                <p>This request has been shared with IT Help Desk, HR, and the Department Manager.</p>
            </body>
        </html>
        """
        if helpdesk_email:
            cls._send_email(helpdesk_email, subject, body)
        if hr_email:
            cls._send_email(hr_email, subject, body)
        if manager_email:
            cls._send_email(manager_email, subject, body)

    @classmethod
    def notify_hr_verified(cls, employee_name: str, asset_name: str, is_needed: bool):
        helpdesk_email = os.getenv("HELP_DESK_EMAIL")
        manager_email = os.getenv("MANAGER_EMAIL") # Fallback or specific
        
        status_text = "Verified as NEEDED" if is_needed else "Verified as NOT NEEDED"
        color = "#10b981" if is_needed else "#ef4444"
        
        subject = f"HR Verification: {asset_name} for {employee_name} ({'Needed' if is_needed else 'Not Needed'})"
        body = f"""
        <html>
            <body>
                <h2 style='color: {color};'>HR Request Verification</h2>
                <p><strong>Employee:</strong> {employee_name}</p>
                <p><strong>Asset:</strong> {asset_name}</p>
                <p><strong>HR Decision:</strong> {status_text}</p>
                <p>Help Desk can now proceed with inventory check.</p>
            </body>
        </html>
        """
        if helpdesk_email:
            cls._send_email(helpdesk_email, subject, body)

    @classmethod
    def notify_stock_info_to_manager(cls, employee_name: str, asset_name: str, manager_email: str, stock_msg: str):
        subject = f"Inventory Check Result: {asset_name} for {employee_name}"
        body = f"""
        <html>
            <body>
                <h2 style='color: #6366f1;'>Inventory Triage Report</h2>
                <p><strong>Employee:</strong> {employee_name}</p>
                <p><strong>Asset:</strong> {asset_name}</p>
                <p><strong>Stock Availability:</strong> {stock_msg}</p>
                <p>Please review and provide final approval/denial.</p>
            </body>
        </html>
        """
        if manager_email:
            cls._send_email(manager_email, subject, body)

    @classmethod
    def notify_manager_decision(cls, employee_name: str, asset_name: str, is_approved: bool):
        subject = f"Final Decision: {asset_name} for {employee_name} ({'Approved' if is_approved else 'Denied'})"
        color = "#10b981" if is_approved else "#ef4444"
        body = f"""
        <html>
            <body>
                <h2 style='color: {color};'>Manager's Final Decision</h2>
                <p>The request for <strong>{asset_name}</strong> for <strong>{employee_name}</strong> has been <strong>{'Approved' if is_approved else 'Denied'}</strong>.</p>
                <p>{'Fulfillment will begin shortly.' if is_approved else 'No further action will be taken.'}</p>
            </body>
        </html>
        """
        # Notify employee and helpdesk?
        helpdesk_email = os.getenv("HELP_DESK_EMAIL")
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
