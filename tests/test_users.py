import pytest
from unittest.mock import patch

@pytest.fixture
def auth(org_admin_token):
    return{"Authorization": f"Bearer {org_admin_token}"}

@pytest.fixture
def employee_payload(default_branch):
    return{"name":"Prabhu","email":"prabhu@test1.com","role":"employee","branch_id":default_branch.branch_id,"password":"Pass@123"}

def test_register(client, auth, employee_payload):
    response=client.post("/employees/register", json=employee_payload, headers=auth)
    assert response.status_code==201
    body=response.json()
    assert body["name"]==employee_payload["name"]
    assert body["email"]==employee_payload["email"]
    assert body["role"]==employee_payload["role"]
    assert body["branch_id"]==employee_payload["branch_id"]
    assert body["is_active"]==True
    assert body["password_reset_required"]==False
    
def test_list_employees(client, auth):
    response=client.get("/employees", headers=auth)
    assert response.status_code==200
    body=response.json()
    assert isinstance(body, dict)
    assert "items" in body

def test_update_user(client, auth, test_employee):
    update_data={"name":"Prabhu Updated","phone":"1234567890"}
    with patch("app.server.routes.employee.AuditService.log_change") as mock_audit:
        response=client.put(f"/employees/{test_employee.employee_id}", json=update_data, headers=auth)
    assert response.status_code==200
    body=response.json()
    assert body["name"]==update_data["name"]
    assert body["phone"]==update_data["phone"]
    assert body["is_active"]==True
    mock_audit.assert_not_called()
    
def test_deactivate_user(client, auth, test_employee):
    with patch("app.server.routes.employee.EmployeeLifecycleService.deactivate_and_recover_assets",
            return_value={"status":"deleted","employee_id":test_employee.employee_id,"recovered_hardware":0 }) as mock_deactivate:
        response=client.post(f"/employees/{test_employee.employee_id}/deactivate", headers=auth)

    assert response.status_code==200
    assert response.json()["status"]=="deleted"
    mock_deactivate.assert_called_once()