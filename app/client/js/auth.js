// app/client/js/auth.js

document.addEventListener('DOMContentLoaded', () => {
    // If user is already logged in, send them straight to the dashboard
    if (localStorage.getItem('access_token')) {
        window.location.href = 'dashboard.html';
        return;
    }

    const loginForm = document.getElementById('loginForm');
    const loginError = document.getElementById('loginError');
    const submitBtn = document.getElementById('loginSubmitBtn');

    if (loginForm) {
        loginForm.addEventListener('submit', async (e) => {
            e.preventDefault(); // Prevent standard POST
            
            // Clear any previous errors
            loginError.style.display = 'none';
            submitBtn.textContent = 'Authenticating...';
            submitBtn.disabled = true;

            const email = document.getElementById('username').value;
            const password = document.getElementById('password').value;

            try {
                // Call global API object from api.js
                const authData = await window.API.login(email, password);
                
                // Save tokens
                localStorage.setItem('access_token', authData.access_token);
                
                // Fetch user profile immediately
                const userProfile = await window.API.getProfile();
                localStorage.setItem('user_data', JSON.stringify(userProfile));
                
                // Redirect on success
                submitBtn.textContent = 'Success!';
                submitBtn.style.backgroundColor = 'var(--success)';
                
                setTimeout(() => {
                    window.location.href = 'dashboard.html';
                }, 500);
                
            } catch (err) {
                loginError.textContent = err.message || 'Login failed. Please check your credentials.';
                loginError.style.display = 'block';
                
                // Shake animation for error
                loginForm.classList.add('shake');
                setTimeout(() => loginForm.classList.remove('shake'), 400);
                
                submitBtn.textContent = 'Secure Login';
                submitBtn.disabled = false;
            }
        });
    }
});
