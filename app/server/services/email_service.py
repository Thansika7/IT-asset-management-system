import smtplib
import os
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List


logger = logging.getLogger(__name__)

class EmailService:
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
        smtp_from = os.getenv("SMTP_FROM", "IT Asset System").strip()

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
            return

        msg = MIMEMultipart()
        msg["From"] = smtp_from
        msg["To"] = to_email
        msg["Subject"] = subject
        if reply_to:
            msg.add_header('reply-to', reply_to)
        
        msg.attach(MIMEText(html_body, "html"))

        try:
            with smtplib.SMTP(smtp_host, smtp_port) as server:
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
                        <p style="font-size: 14px; color: #64748b;">Manage stock levels from the Inventory section of the IT Asset Management portal.</p>
                    </div>
                    <div style="background-color: #f8fafc; padding: 20px; text-align: center; border-top: 1px solid #e2e8f0;">
                        <p style="font-size: 12px; color: #94a3b8; margin: 0;">Automated alert from IT Asset Management System.</p>
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
        # Note: This method is now secondary to notify_branch_stakeholders
        if manager_email:
            cls._send_email(manager_email, subject, body)

    @classmethod
    def notify_hr_verified(cls, employee_name: str, asset_name: str, is_needed: bool, helpdesk_emails: List[str]):
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
        for email in set(helpdesk_emails):
            if email:
                cls._send_email(email, subject, body)

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
    def notify_manager_decision(cls, employee_name: str, asset_name: str, is_approved: bool, helpdesk_emails: List[str]):
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
        for email in set(helpdesk_emails):
            if email:
                cls._send_email(email, subject, body)

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

        body = f"""
        <html>
            <body style="font-family: Arial, sans-serif; color: #333;">
                <h2 style='color: #6366f1;'>Upcoming Asset Expirations</h2>
                <p>The following assets have warranties or licenses expiring within the next 30 days:</p>
                <table style="width: 100%; border-collapse: collapse; text-align: left;">
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
                <p style="margin-top: 20px;">Please take appropriate renewal action.</p>
            </body>
        </html>
        """
        cls._send_email(helpdesk_email, subject, body)
    @classmethod
    def notify_branch_stakeholders(cls, employee_name: str, asset_name: str, recipients: List[str], requester_role: str, branch: str):
        if not recipients:
            return
            
        subject = f"Action Required: New Asset Request from {employee_name} ({branch})"
        body = f"""
        <html>
            <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #1e293b; line-height: 1.6; background-color: #f8fafc; padding: 20px;">
                <div style="max-width: 600px; margin: auto; background: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);">
                    <div style="background-color: #6366f1; padding: 30px; text-align: center;">
                        <h1 style="color: #ffffff; margin: 0; font-size: 24px; font-weight: 600;">IT Asset Management</h1>
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
                                    <td style="padding: 5px 0; color: #1e293b; font-weight: 500;">{requester_role}</td>
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
                        <p style="font-size: 12px; color: #94a3b8; margin: 0;">Automated message from IT Asset Management System.</p>
                        <p style="font-size: 12px; color: #94a3b8; margin: 5px 0 0 0;">&copy; 2026 Your Organization . IT Dept</p>
                    </div>
                </div>
            </body>
        </html>
        """
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
                        <p style="color: #d1fae5; margin: 10px 0 0 0; font-size: 14px;">Your IT Asset Request has been raised</p>
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
                        <p style="font-size: 12px; color: #94a3b8; margin: 0;">Automated message from IT Asset Management System.</p>
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
    def notify_cross_branch_transfer_request(cls, requester_branch: str, target_branch: str, asset_brand: str, asset_name: str, recipients: List[str], reply_to_email: str):
        if not recipients:
            return
            
        subject = f"Urgent Transfer Request: {asset_brand} {asset_name} from {requester_branch} Branch"
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
                                    <td style="padding: 5px 0; color: #b45309; font-size: 14px;">Asset Brand Spec</td>
                                    <td style="padding: 5px 0; color: #92400e; font-weight: 600;">{asset_brand}</td>
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




