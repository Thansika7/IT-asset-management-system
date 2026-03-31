// app/client/js/api.js

const API_BASE_URL = 'http://127.0.0.1:9000';

window.API = {
    // Basic wrapper to include Authorization automatically
    async fetchWithAuth(endpoint, options = {}) {
        const token = localStorage.getItem('access_token');
        
        const headers = {
            'Content-Type': 'application/json',
            ...(options.headers || {})
        };
        
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }
        
        const config = {
            ...options,
            headers
        };

        try {
            const response = await fetch(`${API_BASE_URL}${endpoint}`, config);
            const data = await response.json();
            
            if (!response.ok) {
                throw new Error(data.message || data.detail || 'API request failed');
            }
            return data;
        } catch (error) {
            console.error('API Error:', error);
            throw error;
        }
    },

    async login(username, password) {
        // FastAPI OAuth2PasswordRequestForm expects x-www-form-urlencoded
        const formData = new URLSearchParams();
        formData.append('username', username);
        formData.append('password', password);

        try {
            const response = await fetch(`${API_BASE_URL}/auth/login`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: formData
            });
            const data = await response.json();
            
            if (!response.ok) {
                throw new Error(data.message || data.detail || 'Login failed');
            }
            return data;
        } catch (error) {
            console.error('Login Error:', error);
            throw error;
        }
    },

    async getMyAssets(empId) {
        return this.fetchWithAuth(`/employees/${empId}/assets`, { method: 'GET' });
    },

    async getRequests() {
        return this.fetchWithAuth('/requests/', { method: 'GET' });
    },

    async createRequest(payload) {
        return this.fetchWithAuth('/requests/', {
            method: 'POST',
            body: JSON.stringify(payload)
        });
    },

    async getProfile() {
        return this.fetchWithAuth('/auth/me', { method: 'GET' });
    },
    
    async logout() {
        localStorage.removeItem('access_token');
        localStorage.removeItem('user_data');
        window.location.href = 'index.html';
    }
};
