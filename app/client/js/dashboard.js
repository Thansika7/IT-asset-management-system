// app/client/js/dashboard.js

// SPA Routing function exposed globally for HTML onclick handlers
window.switchView = function(viewId, navElement) {
    // Hide all sections
    document.querySelectorAll('main.main-content section').forEach(sec => {
        sec.style.display = 'none';
    });
    
    // Remove active class from all nav items
    document.querySelectorAll('.nav-links a').forEach(a => {
        a.classList.remove('active');
    });
    
    // Show selected view and highlight nav
    document.getElementById(viewId).style.display = 'block';
    if(navElement) navElement.classList.add('active');

    // Trigger data loads if necessary based on view
    if (viewId === 'myRequestsView') {
        loadMyRequests();
    } else if (viewId === 'myAssetsView') {
        loadMyAssets();
    }
};

async function loadMyAssets() {
    const tableBody = document.getElementById('assetsTableBody');
    const loadingMessage = document.getElementById('assetsLoading');
    const assetsTable = document.getElementById('assetsTable');
    const userData = JSON.parse(localStorage.getItem('user_data'));

    try {
        const response = await window.API.getMyAssets(userData.employee_id);
        const assets = response.active_assets || [];

        loadingMessage.style.display = 'none';

        if (assets.length === 0) {
            tableBody.innerHTML = `<tr><td colspan="3" style="text-align:center; padding: 20px;">No hardware assigned to you yet.</td></tr>`;
        } else {
            tableBody.innerHTML = assets.map(asset => `
                <tr>
                    <td style="font-family: monospace; font-size: 13px;">${asset.tracking_id}</td>
                    <td><b>${asset.asset_id}</b></td>
                    <td>
                        <span class="badge ${asset.is_acknowledged ? 'active' : 'pending'}">
                            ${asset.is_acknowledged ? '✓ Received' : '⏳ Action Needed'}
                        </span>
                    </td>
                </tr>
            `).join('');
        }
        assetsTable.style.display = 'table';
    } catch (err) {
        loadingMessage.textContent = 'Failed to load your hardware profile.';
        loadingMessage.style.color = 'var(--error)';
    }
}

async function loadMyRequests() {
    const tableBody = document.getElementById('requestsTableBody');
    const loadingMessage = document.getElementById('requestsLoading');
    const table = document.getElementById('requestsTable');

    loadingMessage.style.display = 'block';
    table.style.display = 'none';

    try {
        const requests = await window.API.getRequests();
        loadingMessage.style.display = 'none';

        if (!requests || requests.length === 0) {
            tableBody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding: 20px;">You have no active IT requests.</td></tr>`;
        } else {
            tableBody.innerHTML = requests.map(req => {
                const dateRaw = new Date(req.created_at);
                const dateStr = dateRaw.toLocaleDateString() + ' ' + dateRaw.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
                
                // Color coding for status
                let statusColor = 'pending'; // yellow
                if(req.status === 'COMPLETED') statusColor = 'active'; // green
                if(req.status === 'REJECTED') statusColor = 'rejected'; // custom red
                
                return `
                <tr>
                    <td style="font-family: monospace; font-size: 13px;">${req.request_id}</td>
                    <td><b>${req.asset_name}</b></td>
                    <td><span class="badge" style="background: rgba(59,130,246,0.1); color: var(--accent-color)">${req.action_type}</span></td>
                    <td style="font-size: 14px;">${req.stage.replace('_', ' ')}</td>
                    <td><span class="badge ${statusColor}">${req.status.replace(/_/g, ' ')}</span></td>
                    <td style="font-size: 13px; color: var(--text-secondary);">${dateStr}</td>
                </tr>
            `}).join('');
        }
        table.style.display = 'table';
    } catch (err) {
        loadingMessage.textContent = 'Failed to securely load request history.';
        loadingMessage.style.color = 'var(--error)';
    }
}

// Bootstrap Initialization
document.addEventListener('DOMContentLoaded', async () => {
    // Authentication Guard
    const token = localStorage.getItem('access_token');
    if (!token) {
        window.location.href = 'index.html';
        return;
    }

    // Retrieve active user profile
    let userData = null;
    try {
        const storedUser = localStorage.getItem('user_data');
        if (storedUser) {
            userData = JSON.parse(storedUser);
        } else {
            userData = await window.API.getProfile();
            localStorage.setItem('user_data', JSON.stringify(userData));
        }
        
        document.getElementById('welcomeText').textContent = `Welcome, ${userData.name}`;
    } catch (err) {
        console.error("Profile load failed", err);
        window.API.logout();
        return;
    }

    // Initial Load for default view (My Assets)
    loadMyAssets();

    // Setup Form Handler for New Request
    const reqForm = document.getElementById('newRequestForm');
    const reqSubmitBtn = document.getElementById('reqSubmitBtn');
    const reqError = document.getElementById('requestError');

    if (reqForm) {
        reqForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            reqError.style.display = 'none';
            reqSubmitBtn.textContent = 'Submitting...';
            reqSubmitBtn.disabled = true;

            const payload = {
                asset_name: document.getElementById('reqAssetName').value,
                action_type: document.getElementById('reqActionType').value,
                priority: document.getElementById('reqPriority').value,
                business_justification: document.getElementById('reqJustification').value
            };

            try {
                await window.API.createRequest(payload);
                reqForm.reset();
                reqSubmitBtn.textContent = 'Success!';
                reqSubmitBtn.style.backgroundColor = 'var(--success)';
                
                setTimeout(() => {
                    reqSubmitBtn.textContent = 'Submit to HelpDesk';
                    reqSubmitBtn.style.backgroundColor = 'var(--accent-color)';
                    reqSubmitBtn.disabled = false;
                    // Switch to Requests view to see the new item
                    document.getElementById('navMyRequests').click();
                }, 1000);

            } catch (err) {
                reqError.textContent = err.message || 'Failed to submit request.';
                reqError.style.display = 'block';
                reqSubmitBtn.textContent = 'Submit to HelpDesk';
                reqSubmitBtn.disabled = false;
            }
        });
    }

    // Nav Bindings
    document.getElementById('logoutBtn').addEventListener('click', () => {
        window.API.logout();
    });
});
