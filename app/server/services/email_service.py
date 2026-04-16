import smtplib
import os
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from app.server.schema.employee import Employee

logger = logging.getLogger(__name__)


def _app_display_name() -> str:
    """Product name in email copy and default SMTP From (override with APP_DISPLAY_NAME in .env)."""
    return (os.getenv("APP_DISPLAY_NAME", "Asset Control System") or "Asset Control System").strip()


def _default_smtp_from() -> str:
    return f"{_app_display_name()} <no-reply@localhost>"


class EmailService:
    @staticmethod
    def _format_role_label(role_value) -> str:
        if role_value is None:
            return "User"
        raw = getattr(role_value, "value", role_value)
        text = str(raw).replace("_", " ").strip()
        return text.title() if text else "User"

    @staticmethod
    def _wrap_email(title: str, subtitle: str, body_html: str, accent_color: str = "#6366f1", footer_note: Optional[str] = None) -> str:
        if footer_note is None:
            footer_note = f"Automated message from {_app_display_name()} — do not reply."
        return f"""
        <html>
            <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #1e293b; line-height: 1.6; background-color: #f8fafc; padding: 20px;">
                <div style="max-width: 600px; margin: auto; background: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);">
                    <div style="background-color: {accent_color}; padding: 30px; text-align: center;">
                        <h1 style="color: #ffffff; margin: 0; font-size: 24px; font-weight: 600;">{title}</h1>
                        <p style="color: #ffffff; opacity: 0.85; margin: 10px 0 0 0; font-size: 14px;">{subtitle}</p>
                    </div>
                    <div style="padding: 40px;">
                        {body_html}
                    </div>
                    <div style="background-color: #f8fafc; padding: 20px; text-align: center; border-top: 1px solid #e2e8f0;">
                        <p style="font-size: 12px; color: #94a3b8; margin: 0;">{footer_note}</p>
                    </div>
                </div>
            </body>
        </html>
        """

    @staticmethod
    def _send_email(to_email: str, subject: str, html_body: str, reply_to: str = None):
        # Force reload .env to bypass Uvicorn's hot-reload cache
        from dotenv import load_dotenv
        load_dotenv(override=True)
        
        smtp_host = os.getenv("SMTP_HOST", "").strip()
        smtp_port_raw = os.getenv("SMTP_PORT", "587").strip()
        smtp_port = int(smtp_port_raw) if smtp_port_raw.isdigit() else 587
        smtp_user = os.getenv("SMTP_USER", "").strip()
        smtp_pass = os.getenv("SMTP_PASSWORD", "").strip()
        smtp_from = os.getenv("SMTP_FROM", "").strip() or _default_smtp_from()

        if not all([smtp_host, smtp_user, smtp_pass]):
            logger.warning(
                "Email not sent: SMTP credentials missing",
                extra={
                    "userId": "system",
                    "endpoint": "/notifications/email",
                    "method": "SMTP",
                    "statusCode": 503,
                    "responseTime": 0,
                },
            )
            return False

        msg = MIMEMultipart()
        msg["From"] = smtp_from
        msg["To"] = to_email
        msg["Subject"] = subject
        if reply_to:
            msg.add_header('reply-to', reply_to)
        
        msg.attach(MIMEText(html_body, "html"))

        try:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)
                logger.info(
                    "Email sent",
                    extra={
                        "userId": "system",
                        "endpoint": "/notifications/email",
                        "method": "SMTP",
                        "statusCode": 200,
                        "responseTime": 0,
                    },
                )
                return True
        except Exception as e:
            logger.error(
                f"Email send failed: {str(e)}",
                extra={
                    "userId": "system",
                    "endpoint": "/notifications/email",
                    "method": "SMTP",
                    "statusCode": 500,
                    "responseTime": 0,
                },
            )
            return False

    @classmethod
    def notify_low_stock(cls, asset_name: str, asset_id: str, branch: str, unused: int, threshold: int, recipients: list):
        if not recipients:
            return
        urgency_color = "#ef4444" if unused == 0 else "#f59e0b"
        urgency_label = "OUT OF STOCK" if unused == 0 else "LOW STOCK"
        urgency_bg = "#fef2f2" if unused == 0 else "#fffbeb"
        urgency_border = "#fca5a5" if unused == 0 else "#fde68a"
        action_note = "This asset is completely out of stock. New requests cannot be fulfilled. Please initiate a procurement order immediately." if unused == 0 else "Stock is running low. Consider initiating a procurement or cross-branch transfer before inventory runs out."
        subject = f"[{urgency_label}] {asset_name} - {unused} unit(s) remaining in {branch or 'Unassigned Branch'}"
        body = f"""
        <html>
            <body style="font-family: Segoe UI, Tahoma, sans-serif; color: #1e293b; background-color: #f8fafc; padding: 20px;">
                <div style="max-width: 600px; margin: auto; background: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);">
                    <div style="background-color: {urgency_color}; padding: 30px; text-align: center;">
                        <h1 style="color: #ffffff; margin: 0; font-size: 24px; font-weight: 700;">{urgency_label}</h1>
                        <p style="color: #fff; opacity: 0.85; margin: 10px 0 0 0; font-size: 14px;">Inventory action required for {branch or 'your branch'}</p>
                    </div>
                    <div style="padding: 40px;">
                        <p>This is an automated alert. The following catalog asset has dropped to or below its configured restock threshold.</p>
                        <div style="background-color: {urgency_bg}; border: 1px solid {urgency_border}; border-radius: 8px; padding: 20px; margin: 25px 0;">
                            <table style="width: 100%; border-collapse: collapse;">
                                <tr><td style="padding: 6px 0; color: #64748b; width: 40%;">Asset Name</td><td style="font-weight: 600;">{asset_name}</td></tr>
                                <tr><td style="padding: 6px 0; color: #64748b;">Asset ID</td><td style="font-family: monospace; font-size: 13px;">{asset_id}</td></tr>
                                <tr><td style="padding: 6px 0; color: #64748b;">Branch</td><td style="font-weight: 600;">{branch or '-'}</td></tr>
                                <tr><td style="padding: 6px 0; color: #64748b;">Units Remaining</td><td style="font-weight: 700; font-size: 18px; color: {urgency_color};">{unused}</td></tr>
                                <tr><td style="padding: 6px 0; color: #64748b;">Restock Threshold</td><td>{threshold} units</td></tr>
                            </table>
                        </div>
                        <div style="border-left: 4px solid {urgency_color}; background-color: #f8fafc; padding: 15px; margin: 25px 0; font-size: 14px;">
                            <strong>Recommended Action:</strong><br>{action_note}
                        </div>
                        <p style="font-size: 14px; color: #64748b;">Manage stock levels from the Inventory section of the {_app_display_name()} portal.</p>
                    </div>
                    <div style="background-color: #f8fafc; padding: 20px; text-align: center; border-top: 1px solid #e2e8f0;">
                        <p style="font-size: 12px; color: #94a3b8; margin: 0;">Automated alert from {_app_display_name()}.</p>
                    </div>
                </div>
            </body>
        </html>
        """
        for email in set(recipients):
            if email:
                cls._send_email(email, subject, body)

    @classmethod
    def notify_request_created(cls, employee_name: str, asset_name: str, manager_email: str):
        helpdesk_email = os.getenv("HELP_DESK_EMAIL")
        hr_email = os.getenv("HR_EMAIL")
        subject = f"New Asset Request: {asset_name} from {employee_name}"
        body = cls._wrap_email(
            "New Asset Request",
            "Pending HR verification",
            f"""
            <p>A new request has been raised and shared with the relevant reviewers.</p>
            <div style="background-color: #f1f5f9; border-radius: 8px; padding: 20px; margin: 25px 0;">
                <table style="width: 100%; border-collapse: collapse;">
                    <tr><td style="padding: 5px 0; color: #64748b; width: 40%;">Employee</td><td style="font-weight: 600;">{employee_name}</td></tr>
                    <tr><td style="padding: 5px 0; color: #64748b;">Asset requested</td><td style="font-weight: 600;">{asset_name}</td></tr>
                    <tr><td style="padding: 5px 0; color: #64748b;">Status</td><td style="font-weight: 600;">Pending HR Verification</td></tr>
                </table>
            </div>
            <p style="font-size: 14px; color: #64748b;">This request has been shared with IT Help Desk, HR, and the department manager.</p>
            """,
        )
        # Note: This method is now secondary to notify_branch_stakeholders
        if manager_email:
            cls._send_email(manager_email, subject, body)

    @classmethod
    def notify_hr_verified(cls, employee_name: str, asset_name: str, is_needed: bool, helpdesk_emails: List[str]):
        status_text = "Verified as NEEDED" if is_needed else "Verified as NOT NEEDED"
        color = "#10b981" if is_needed else "#ef4444"
        
        subject = f"HR Verification: {asset_name} for {employee_name} ({'Needed' if is_needed else 'Not Needed'})"
        body = cls._wrap_email(
            "HR Verification",
            f"{employee_name} · {asset_name}",
            f"""
            <p>HR has completed the necessity review for this request.</p>
            <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px; margin: 25px 0;">
                <table style="width: 100%; border-collapse: collapse;">
                    <tr><td style="padding: 5px 0; color: #64748b; width: 40%;">Employee</td><td style="font-weight: 600;">{employee_name}</td></tr>
                    <tr><td style="padding: 5px 0; color: #64748b;">Asset</td><td style="font-weight: 600;">{asset_name}</td></tr>
                    <tr><td style="padding: 5px 0; color: #64748b;">HR decision</td><td style="font-weight: 700; color: {color};">{status_text}</td></tr>
                </table>
            </div>
            <p style="font-size: 14px; color: #64748b;">Help Desk can now continue the inventory and fulfilment review.</p>
            """,
            accent_color=color,
        )
        for email in set(helpdesk_emails):
            if email:
                cls._send_email(email, subject, body)

    @classmethod
    def notify_stock_info_to_manager(cls, employee_name: str, asset_name: str, manager_email: str, stock_msg: str):
        subject = f"Inventory Check Result: {asset_name} for {employee_name}"
        body = cls._wrap_email(
            "Inventory Triage Report",
            "Manager review required",
            f"""
            <p>Inventory triage is complete and this request is ready for your review.</p>
            <div style="background-color: #f1f5f9; border-radius: 8px; padding: 20px; margin: 25px 0;">
                <table style="width: 100%; border-collapse: collapse;">
                    <tr><td style="padding: 5px 0; color: #64748b; width: 40%;">Employee</td><td style="font-weight: 600;">{employee_name}</td></tr>
                    <tr><td style="padding: 5px 0; color: #64748b;">Asset</td><td style="font-weight: 600;">{asset_name}</td></tr>
                    <tr><td style="padding: 5px 0; color: #64748b;">Stock availability</td><td style="font-weight: 600;">{stock_msg}</td></tr>
                </table>
            </div>
            <p style="font-size: 14px; color: #64748b;">Please review and provide final approval or denial.</p>
            """,
        )
        if manager_email:
            cls._send_email(manager_email, subject, body)

    @classmethod
    def notify_manager_decision(cls, employee_name: str, asset_name: str, is_approved: bool, helpdesk_emails: List[str]):
        subject = f"Final Decision: {asset_name} for {employee_name} ({'Approved' if is_approved else 'Denied'})"
        color = "#10b981" if is_approved else "#ef4444"
        body = cls._wrap_email(
            "Manager Decision",
            f"{'Approved' if is_approved else 'Denied'} request",
            f"""
            <p>The final branch review has been completed for this request.</p>
            <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px; margin: 25px 0;">
                <table style="width: 100%; border-collapse: collapse;">
                    <tr><td style="padding: 5px 0; color: #64748b; width: 40%;">Employee</td><td style="font-weight: 600;">{employee_name}</td></tr>
                    <tr><td style="padding: 5px 0; color: #64748b;">Asset</td><td style="font-weight: 600;">{asset_name}</td></tr>
                    <tr><td style="padding: 5px 0; color: #64748b;">Decision</td><td style="font-weight: 700; color: {color};">{'Approved' if is_approved else 'Denied'}</td></tr>
                </table>
            </div>
            <p style="font-size: 14px; color: #64748b;">{'Fulfilment can begin now.' if is_approved else 'No further action will be taken on this request.'}</p>
            """,
            accent_color=color,
        )
        for email in set(helpdesk_emails):
            if email:
                cls._send_email(email, subject, body)

    @classmethod
    def notify_asset_assigned(cls, employee_name: str, asset_name: str, manager_email: str):
        subject = f"Asset Assigned: {asset_name} to {employee_name}"
        body = cls._wrap_email(
            "Asset Hand-over Complete",
            "Fulfilment completed successfully",
            f"""
            <p>The request has been fulfilled and the asset has been assigned.</p>
            <div style="background-color: #f1f5f9; border-radius: 8px; padding: 20px; margin: 25px 0;">
                <table style="width: 100%; border-collapse: collapse;">
                    <tr><td style="padding: 5px 0; color: #64748b; width: 40%;">Employee</td><td style="font-weight: 600;">{employee_name}</td></tr>
                    <tr><td style="padding: 5px 0; color: #64748b;">Assigned asset</td><td style="font-weight: 600;">{asset_name}</td></tr>
                </table>
            </div>
            <p style="font-size: 14px; color: #64748b;">Inventory and tracking records have been updated.</p>
            """,
        )
        if manager_email:
            cls._send_email(manager_email, subject, body)

    @classmethod
    def notify_support_approaching_expiry(cls, expiring_assets: list):
        helpdesk_email = os.getenv("HELP_DESK_EMAIL")
        if not helpdesk_email:
            return

        subject = "Action Required: Assets Approaching Expiry"
        
        rows = ""
        for item in expiring_assets:
            color = "#ef4444" if item["days_left"] <= 7 else "#f59e0b"
            rows += f"""
            <tr>
                <td style='padding: 8px; border-bottom: 1px solid #ddd;'>{item['asset_name']} ({item['asset_id'][:8]})</td>
                <td style='padding: 8px; border-bottom: 1px solid #ddd;'>{item['type']}</td>
                <td style='padding: 8px; border-bottom: 1px solid #ddd; color: {color};'><strong>{item['days_left']}</strong></td>
                <td style='padding: 8px; border-bottom: 1px solid #ddd;'>{item['expiry_date']}</td>
            </tr>
            """

        body = cls._wrap_email(
            "Upcoming Asset Expirations",
            "Action required within 30 days",
            f"""
            <p>The following assets have warranties or licenses expiring within the next 30 days:</p>
            <table style="width: 100%; border-collapse: collapse; text-align: left; margin-top: 20px;">
                <thead>
                    <tr style="background-color: #f3f4f6;">
                        <th style="padding: 10px; border-bottom: 2px solid #cbd5e1;">Asset</th>
                        <th style="padding: 10px; border-bottom: 2px solid #cbd5e1;">Expiry Type</th>
                        <th style="padding: 10px; border-bottom: 2px solid #cbd5e1;">Days Left</th>
                        <th style="padding: 10px; border-bottom: 2px solid #cbd5e1;">Date</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
            </table>
            <p style="margin-top: 20px; font-size: 14px; color: #64748b;">Please take appropriate renewal action.</p>
            """,
        )
        cls._send_email(helpdesk_email, subject, body)
    @classmethod
    def notify_branch_stakeholders(cls, employee_name: str, asset_name: str, recipients: List[str], requester_role: str, branch: str):
        if not recipients:
            return

        role_label = cls._format_role_label(requester_role)
            
        subject = f"Action Required: New Asset Request from {employee_name} ({branch})"
        body = f"""
        <html>
            <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #1e293b; line-height: 1.6; background-color: #f8fafc; padding: 20px;">
                <div style="max-width: 600px; margin: auto; background: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);">
                    <div style="background-color: #6366f1; padding: 30px; text-align: center;">
                        <h1 style="color: #ffffff; margin: 0; font-size: 24px; font-weight: 600;">{_app_display_name()}</h1>
                        <p style="color: #e0e7ff; margin: 10px 0 0 0; font-size: 14px;">Incoming Resource Request</p>
                    </div>
                    <div style="padding: 40px;">
                        <h2 style="color: #1e293b; margin-top: 0; font-size: 20px; font-weight: 600;">Request Notification</h2>
                        <p>A new asset request has been raised in your branch that requires attention from the relevant stakeholders.</p>
                        
                        <div style="background-color: #f1f5f9; border-radius: 8px; padding: 20px; margin: 25px 0;">
                            <table style="width: 100%; border-collapse: collapse;">
                                <tr>
                                    <td style="padding: 5px 0; color: #64748b; font-size: 14px; width: 40%;">Requester</td>
                                    <td style="padding: 5px 0; color: #1e293b; font-weight: 500;">{employee_name}</td>
                                </tr>
                                <tr>
                                    <td style="padding: 5px 0; color: #64748b; font-size: 14px;">Role</td>
                                    <td style="padding: 5px 0; color: #1e293b; font-weight: 500;">{role_label}</td>
                                </tr>
                                <tr>
                                    <td style="padding: 5px 0; color: #64748b; font-size: 14px;">Branch</td>
                                    <td style="padding: 5px 0; color: #1e293b; font-weight: 500;">{branch}</td>
                                </tr>
                                <tr>
                                    <td style="padding: 5px 0; color: #64748b; font-size: 14px;">Asset Requested</td>
                                    <td style="padding: 5px 0; color: #1e293b; font-weight: 500; color: #6366f1;">{asset_name}</td>
                                </tr>
                            </table>
                        </div>
                        
                        <p style="font-size: 14px; color: #64748b;">The request is currently at the <strong>HR & Support Triage</strong> stage. Please review the details.</p>
                    </div>
                    <div style="background-color: #f8fafc; padding: 20px; text-align: center; border-top: 1px solid #e2e8f0;">
                        <p style="font-size: 12px; color: #94a3b8; margin: 0;">Automated message from {_app_display_name()}.</p>
                    </div>
                </div>
            </body>
        </html>
        """
        for email in set(recipients):
            if email:
                cls._send_email(email, subject, body)

    @classmethod
    def notify_request_stage_update(
        cls,
        employee_name: str,
        asset_name: str,
        branch: str,
        stage_name: str,
        recipients: List[str],
    ):
        if not recipients:
            return

        subject = f"Request Stage Update: {asset_name} - {stage_name}"
        body = f"""
        <html>
            <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #1e293b; line-height: 1.6; background-color: #f8fafc; padding: 20px;">
                <div style="max-width: 600px; margin: auto; background: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);">
                    <div style="background-color: #0ea5e9; padding: 30px; text-align: center;">
                        <h1 style="color: #ffffff; margin: 0; font-size: 24px; font-weight: 600;">Request Workflow Update</h1>
                        <p style="color: #e0f2fe; margin: 10px 0 0 0; font-size: 14px;">{_app_display_name()}</p>
                    </div>
                    <div style="padding: 40px;">
                        <p>The request has moved to a new workflow stage and requires visibility from higher authorities.</p>
                        <div style="background-color: #f1f5f9; border-radius: 8px; padding: 20px; margin: 25px 0;">
                            <table style="width: 100%; border-collapse: collapse;">
                                <tr>
                                    <td style="padding: 5px 0; color: #64748b; font-size: 14px; width: 40%;">Requester</td>
                                    <td style="padding: 5px 0; color: #1e293b; font-weight: 500;">{employee_name}</td>
                                </tr>
                                <tr>
                                    <td style="padding: 5px 0; color: #64748b; font-size: 14px;">Branch</td>
                                    <td style="padding: 5px 0; color: #1e293b; font-weight: 500;">{branch}</td>
                                </tr>
                                <tr>
                                    <td style="padding: 5px 0; color: #64748b; font-size: 14px;">Asset Requested</td>
                                    <td style="padding: 5px 0; color: #1e293b; font-weight: 500;">{asset_name}</td>
                                </tr>
                                <tr>
                                    <td style="padding: 5px 0; color: #64748b; font-size: 14px;">Current Stage</td>
                                    <td style="padding: 5px 0; color: #0369a1; font-weight: 700;">{stage_name}</td>
                                </tr>
                            </table>
                        </div>
                    </div>
                    <div style="background-color: #f8fafc; padding: 20px; text-align: center; border-top: 1px solid #e2e8f0;">
                        <p style="font-size: 12px; color: #94a3b8; margin: 0;">Automated message from {_app_display_name()}.</p>
                    </div>
                </div>
            </body>
        </html>
        """
        for email in set(recipients):
            if email:
                cls._send_email(email, subject, body)

    @classmethod
    def notify_health_alert(
        cls,
        recipients: List[str],
        asset_name: str,
        instance_id: str,
        score: int,
        classification: str,
        recommendation: str,
        branch: str,
    ):
        if not recipients:
            return
        subject = f"[HEALTH ALERT] {asset_name} ({instance_id}) score={score}"
        body = cls._wrap_email(
            "Asset Health Alert",
            f"{asset_name} · Branch {branch}",
            f"""
            <p>An asset instance health score has fallen below the configured threshold.</p>
            <div style=\"background-color:#fef2f2;border:1px solid #fecaca;border-radius:8px;padding:20px;margin:25px 0;\">
                <table style=\"width:100%;border-collapse:collapse;\">
                    <tr><td style=\"padding:5px 0;color:#64748b;width:40%;\">Asset</td><td style=\"font-weight:600;\">{asset_name}</td></tr>
                    <tr><td style=\"padding:5px 0;color:#64748b;\">Instance ID</td><td style=\"font-family:monospace;font-weight:600;\">{instance_id}</td></tr>
                    <tr><td style=\"padding:5px 0;color:#64748b;\">Branch</td><td style=\"font-weight:600;\">{branch}</td></tr>
                    <tr><td style=\"padding:5px 0;color:#64748b;\">Score</td><td style=\"font-weight:700;color:#b91c1c;\">{score}</td></tr>
                    <tr><td style=\"padding:5px 0;color:#64748b;\">Classification</td><td style=\"font-weight:700;color:#b91c1c;\">{classification}</td></tr>
                    <tr><td style=\"padding:5px 0;color:#64748b;\">Recommendation</td><td style=\"font-weight:700;color:#7f1d1d;\">{recommendation}</td></tr>
                </table>
            </div>
            <p style=\"font-size:14px;color:#64748b;\">Please review lifecycle events and schedule replacement if required.</p>
            """,
            accent_color="#ef4444",
        )
        for email in set(recipients):
            if email:
                cls._send_email(email, subject, body)

    @classmethod
    def notify_budget_alert(
        cls,
        recipients: List[str],
        asset_name: str,
        instance_id: str,
        repair_cost: float,
        threshold: float,
        branch: str,
    ):
        if not recipients:
            return
        subject = f"[BUDGET ALERT] {asset_name} ({instance_id}) repair cost threshold exceeded"
        body = cls._wrap_email(
            "Repair Budget Alert",
            f"{asset_name} · Branch {branch}",
            f"""
            <p>A repair cost entry exceeded the configured threshold and requires finance review.</p>
            <div style=\"background-color:#fff7ed;border:1px solid #fed7aa;border-radius:8px;padding:20px;margin:25px 0;\">
                <table style=\"width:100%;border-collapse:collapse;\">
                    <tr><td style=\"padding:5px 0;color:#64748b;width:40%;\">Asset</td><td style=\"font-weight:600;\">{asset_name}</td></tr>
                    <tr><td style=\"padding:5px 0;color:#64748b;\">Instance ID</td><td style=\"font-family:monospace;font-weight:600;\">{instance_id}</td></tr>
                    <tr><td style=\"padding:5px 0;color:#64748b;\">Branch</td><td style=\"font-weight:600;\">{branch}</td></tr>
                    <tr><td style=\"padding:5px 0;color:#64748b;\">Repair Cost</td><td style=\"font-weight:700;color:#9a3412;\">{repair_cost:.2f}</td></tr>
                    <tr><td style=\"padding:5px 0;color:#64748b;\">Threshold</td><td style=\"font-weight:700;color:#9a3412;\">{threshold:.2f}</td></tr>
                </table>
            </div>
            <p style=\"font-size:14px;color:#64748b;\">Please review lifecycle and maintenance plans for this asset.</p>
            """,
            accent_color="#f97316",
        )
        for email in set(recipients):
            if email:
                cls._send_email(email, subject, body)

    @classmethod
    def notify_requester_confirmation(cls, requester_email: str, employee_name: str, asset_name: str, branch: str):
        if not requester_email:
            return
            
        subject = f"Request Received: {asset_name} for {branch}"
        body = f"""
        <html>
            <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #1e293b; line-height: 1.6; background-color: #f8fafc; padding: 20px;">
                <div style="max-width: 600px; margin: auto; background: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);">
                    <div style="background-color: #10b981; padding: 30px; text-align: center;">
                        <h1 style="color: #ffffff; margin: 0; font-size: 24px; font-weight: 600;">Request Confirmed</h1>
                        <p style="color: #d1fae5; margin: 10px 0 0 0; font-size: 14px;">Your request has been submitted in {_app_display_name()}</p>
                    </div>
                    <div style="padding: 40px;">
                        <p>Hello <strong>{employee_name}</strong>,</p>
                        <p>We've received your request for a <strong>{asset_name}</strong> in the <strong>{branch}</strong> branch. Our team is now verifying the necessity and availability of this resource.</p>
                        
                        <div style="border-left: 4px solid #10b981; background-color: #f0fdf4; padding: 15px; margin: 25px 0; font-size: 14px;">
                            <strong>What's Next?</strong><br>
                            Our HR and Support teams will review your request. You will receive an automated notification once your Manager or an Admin makes a decision.
                        </div>
                        
                        <p style="font-size: 14px; color: #64748b;">You can track the progress of your request at any time via the employee portal.</p>
                    </div>
                    <div style="background-color: #f8fafc; padding: 20px; text-align: center; border-top: 1px solid #e2e8f0;">
                        <p style="font-size: 12px; color: #94a3b8; margin: 0;">Automated message from {_app_display_name()}.</p>
                    </div>
                </div>
            </body>
        </html>
        """
        cls._send_email(requester_email, subject, body)

    @classmethod
    def notify_admin_of_manager_request(cls, manager_name: str, asset_name: str, admin_emails: List[str]):
        if not admin_emails:
            return
            
        subject = f"Urgent: Manager Request Needs Your Approval ({asset_name})"
        body = f"""
        <html>
            <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #1e293b; line-height: 1.6; background-color: #f8fafc; padding: 20px;">
                <div style="max-width: 600px; margin: auto; background: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);">
                    <div style="background-color: #ef4444; padding: 30px; text-align: center;">
                        <h1 style="color: #ffffff; margin: 0; font-size: 24px; font-weight: 600;">Admin Approval Required</h1>
                        <p style="color: #fee2e2; margin: 10px 0 0 0; font-size: 14px;">A Manager has raised a restricted request</p>
                    </div>
                    <div style="padding: 40px;">
                        <p>Manager <strong>{manager_name}</strong> has raised a request for <strong>{asset_name}</strong>. As per the system security policy, requests raised by Managers require high-level Admin authorization.</p>
                        
                        <div style="background-color: #fef2f2; border-radius: 8px; padding: 20px; margin: 25px 0; border: 1px solid #fee2e2;">
                            <p style="margin-top: 0;"><strong>Details:</strong></p>
                            <p style="margin-bottom: 0; font-size: 15px;">Target Asset: <span style="color: #ef4444; font-weight: 600;">{asset_name}</span></p>
                        </div>
                        
                        <p style="font-size: 14px; color: #64748b;">Please review this request at your earliest convenience to maintain operational efficiency.</p>
                    </div>
                </div>
            </body>
        </html>
        """
        for email in set(admin_emails):
            if email:
                cls._send_email(email, subject, body)

    @classmethod
    def notify_cross_branch_transfer_request(cls, requester_branch: str, target_branch: str, asset_name: str, recipients: List[str], reply_to_email: str):
        if not recipients:
            return
            
        subject = f"Urgent Transfer Request: {asset_name} from {requester_branch} Branch"
        body = f"""
        <html>
            <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #1e293b; line-height: 1.6; background-color: #f8fafc; padding: 20px;">
                <div style="max-width: 600px; margin: auto; background: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);">
                    <div style="background-color: #f59e0b; padding: 30px; text-align: center;">
                        <h1 style="color: #ffffff; margin: 0; font-size: 24px; font-weight: 600;">Cross-Branch Transfer Required</h1>
                        <p style="color: #fef3c7; margin: 10px 0 0 0; font-size: 14px;">Incoming Resource Request from {requester_branch}</p>
                    </div>
                    <div style="padding: 40px;">
                        <p>Hello <strong>{target_branch} IT & Management</strong>,</p>
                        <p>The <strong>{requester_branch}</strong> branch is completely out of stock and urgently requires an asset to fulfill an employee request.</p>
                        
                        <div style="background-color: #fffbeb; border-radius: 8px; padding: 20px; margin: 25px 0; border: 1px solid #fde68a;">
                            <table style="width: 100%; border-collapse: collapse;">
                                <tr>
                                    <td style="padding: 5px 0; color: #b45309; font-size: 14px; width: 40%;">Target Asset Name</td>
                                    <td style="padding: 5px 0; color: #92400e; font-weight: 600;">{asset_name}</td>
                                </tr>
                                <tr>
                                    <td style="padding: 5px 0; color: #b45309; font-size: 14px;">Requesting Branch</td>
                                    <td style="padding: 5px 0; color: #92400e; font-weight: 600;">{requester_branch}</td>
                                </tr>
                            </table>
                        </div>
                        
                        <div style="border-left: 4px solid #f59e0b; background-color: #f8fafc; padding: 15px; margin: 25px 0; font-size: 14px;">
                            <strong>How to Respond:</strong><br>
                            To formally accept or politely decline this transfer, please <strong>reply to this email directly</strong>. Your reply will be sent straight to the {requester_branch} Manager's inbox.
                        </div>
                    </div>
                </div>
            </body>
        </html>
        """
        for email in set(recipients):
            if email:
                cls._send_email(email, subject, body, reply_to=reply_to_email)

    @classmethod
    def notify_asset_expiration(cls, asset_name: str, asset_id: str, expiry_date: str, attribute_name: str, owner_name: str, recipients: List[str]):
        if not recipients:
            return
            
        subject = f"Warning: {attribute_name} Expiring for {asset_name} in 30 Days"
        body = f"""
        <html>
            <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #1e293b; line-height: 1.6; background-color: #f8fafc; padding: 20px;">
                <div style="max-width: 600px; margin: auto; background: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);">
                    <div style="background-color: #ef4444; padding: 30px; text-align: center;">
                        <h1 style="color: #ffffff; margin: 0; font-size: 24px; font-weight: 600;">{attribute_name} Expiration Alert</h1>
                        <p style="color: #fee2e2; margin: 10px 0 0 0; font-size: 14px;">Action Required within 30 days</p>
                    </div>
                    <div style="padding: 40px;">
                        <p>Hello,</p>
                        <p>This is an automated notification that the <strong>{attribute_name}</strong> for the following asset will expire exactly 30 days from today.</p>
                        
                        <div style="background-color: #fef2f2; border-radius: 8px; padding: 20px; margin: 25px 0; border: 1px solid #fca5a5;">
                            <table style="width: 100%; border-collapse: collapse;">
                                <tr>
                                    <td style="padding: 5px 0; color: #b91c1c; font-size: 14px; width: 40%;">Asset Name</td>
                                    <td style="padding: 5px 0; color: #7f1d1d; font-weight: 600;">{asset_name} ({asset_id})</td>
                                </tr>
                                <tr>
                                    <td style="padding: 5px 0; color: #b91c1c; font-size: 14px;">Current Owner</td>
                                    <td style="padding: 5px 0; color: #7f1d1d; font-weight: 600;">{owner_name}</td>
                                </tr>
                                <tr>
                                    <td style="padding: 5px 0; color: #b91c1c; font-size: 14px;">Expiration Date</td>
                                    <td style="padding: 5px 0; color: #7f1d1d; font-weight: 600;">{expiry_date}</td>
                                </tr>
                            </table>
                        </div>
                        
                        <div style="border-left: 4px solid #ef4444; background-color: #f8fafc; padding: 15px; margin: 25px 0; font-size: 14px;">
                            <strong>Next Steps:</strong><br>
                            If this is a physical warranty, please notify the vendor if service is needed before expiration.
                            If this is a software license, please ensure it is renewed before this date to prevent service disruption.
                        </div>
                    </div>
                </div>
            </body>
        </html>
        """
        for email in set(recipients):
            if email:
                cls._send_email(email, subject, body)

    @staticmethod
    def delivery_email(employee: "Employee") -> str:
        """Route notifications to personal inbox; company email remains the account identity."""
        pe = getattr(employee, "personal_email", None)
        if pe and str(pe).strip():
            return str(pe).strip().lower()
        return (employee.email or "").strip().lower()

    @staticmethod
    def collect_hr_admin_emails(db, branch: Optional[str] = None) -> List[str]:
        from app.server.schema.employee import Employee, EmployeeRole

        out: List[str] = []
        rows = (
            db.query(Employee)
            .filter(
                Employee.is_active == True,  # noqa: E712
                Employee.role.in_([EmployeeRole.HR, EmployeeRole.SUPER_ADMIN]),
            )
            .all()
        )
        for e in rows:
            if e.role == EmployeeRole.SUPER_ADMIN:
                out.append(EmailService.delivery_email(e))
            elif branch is None or (e.branch or "") == (branch or ""):
                out.append(EmailService.delivery_email(e))
        return list({x for x in out if x})

    @classmethod
    def send_provisioning_credentials(cls, personal_email: str, employee_name: str, company_email: str, temp_password: str):
        if not personal_email:
            return
        app_name = _app_display_name()
        subject = f"Your {app_name} account is ready"
        body = cls._wrap_email(
            f"Welcome to {app_name}",
            "Sign-in details",
            f"""
            <p>Hello <strong>{employee_name}</strong>,</p>
            <p>Your company account has been created in {app_name}. Use the credentials below to sign in; you will be prompted to change your password after first login.</p>
            <div style="background-color:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:20px;margin:20px 0;">
                <table style="width:100%;border-collapse:collapse;">
                    <tr><td style="padding:6px 0;color:#64748b;width:40%;">Company email (username)</td><td style="font-family:monospace;font-weight:600;">{company_email}</td></tr>
                    <tr><td style="padding:6px 0;color:#64748b;">Temporary password</td><td style="font-family:monospace;font-weight:600;">{temp_password}</td></tr>
                </table>
            </div>
            <p style="font-size:13px;color:#64748b;">This message was sent to your personal email on file. All system notifications will be delivered here.</p>
            """,
            accent_color="#6366f1",
        )
        cls._send_email(personal_email, subject, body)

    @classmethod
    def send_password_reset_email(cls, email: str, new_password: str, employee_name: str):
        """Send new password via email"""
        
        app_name = _app_display_name()
        subject = f"Password reset — {app_name}"
        body = cls._wrap_email(
            "Password reset",
            "Your new password",
            f"""
            <p>Hello <strong>{employee_name}</strong>,</p>
            <p>Your {app_name} password has been reset. Use the credentials below to sign in:</p>
            <div style="background-color:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:20px;margin:20px 0;">
                <table style="width:100%;border-collapse:collapse;">
                    <tr><td style="padding:6px 0;color:#64748b;width:40%;">New Password</td><td style="font-family:monospace;font-weight:600;font-size:16px;">{new_password}</td></tr>
                </table>
            </div>
            <p style="font-size: 14px; color: #64748b;">For security reasons, please change this password after signing in.</p>
            """,
            accent_color="#6366f1",
        )
        cls._send_email(email, subject, body)




