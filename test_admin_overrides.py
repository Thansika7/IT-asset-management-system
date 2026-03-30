import os
import requests
import uuid
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "http://127.0.0.1:8000"
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

def test_admin_hierarchy():
    print("--- Testing Admin Hierarchy Overrides & Single-Table Auth ---")
    
    session = requests.Session()
    
    # 1. Login as Admin
    print(f"Step 1: Logging in as Admin ({ADMIN_EMAIL})...")
    login_data = {"username": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    response = session.post(f"{BASE_URL}/auth/login", data=login_data)
    
    if response.status_code != 200:
        print(f"FAILED: Admin login failed. Status: {response.status_code}")
        return
    print("SUCCESS: Admin logged in.")

    # 2. Create a Test Employee
    print("\nStep 2: Registering a test employee...")
    emp_email = f"test_{uuid.uuid4().hex[:4]}@example.com"
    emp_payload = {
        "name": "Test Subject",
        "email": emp_email,
        "role": "employee",
        "branch": "Test Branch"
    }
    response = session.post(f"{BASE_URL}/employees/register", json=emp_payload)
    if response.status_code != 201:
        print(f"FAILED: Employee registration failed. Status: {response.status_code}")
        return
    
    reg_data = response.json()
    emp_id = reg_data["employee_id"]
    gen_pass = reg_data["generated_password"]
    print(f"SUCCESS: Employee {emp_id} created with generated password.")

    # 3. Create a Request as the new Employee
    print("\nStep 3: Submitting asset request as employee...")
    emp_session = requests.Session()
    login_data = {"username": emp_email, "password": gen_pass}
    emp_session.post(f"{BASE_URL}/auth/login", data=login_data)
    
    req_payload = {
        "asset_name": "Pro Laptop",
        "asset_category": "Laptops",
        "reason": "Engineering work"
    }
    response = emp_session.post(f"{BASE_URL}/requests/", json=req_payload)
    req_id = response.json()["request_id"]
    print(f"SUCCESS: Request {req_id} submitted.")

    # 4. Admin Triage - Testing Override
    print("\nStep 4: Admin Triaging request (Should skip Manager)...")
    triage_payload = {"action_type": "NEW"}
    response = session.post(f"{BASE_URL}/requests/{req_id}/triage", json=triage_payload)
    
    new_status = response.json()["status"]
    print(f"Post-Triage Status: {new_status}")
    
    if new_status == "APPROVED_FOR_SUPPORT":
        print("SUCCESS: Admin triage bypassed PENDING_MANAGER!")
    else:
        print(f"FAILED: Expected APPROVED_FOR_SUPPORT, got {new_status}")

    # 5. Admin Direct Review Override
    # Let's create another request to test the Direct Admin Review route
    print("\nStep 5: Testing Direct Admin Review Override...")
    response = emp_session.post(f"{BASE_URL}/requests/", json=req_payload)
    req_id_2 = response.json()["request_id"]
    
    # Support Triages (non-admin support team would set to PENDING_MANAGER)
    # But for this test, we just call the admin review directly
    review_payload = {"is_approved": True, "comment": "Admin override"}
    response = session.post(f"{BASE_URL}/requests/{req_id_2}/review/admin", json=review_payload)
    
    if response.status_code == 200 and response.json()["status"] == "APPROVED_FOR_SUPPORT":
        print("SUCCESS: Admin direct review override working!")
    else:
        print(f"FAILED: Admin review override failed. Status: {response.status_code}")

if __name__ == "__main__":
    test_admin_hierarchy()
