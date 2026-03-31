// app/client/js/theme.js

// Retrieve user's previous theme or fallback to true (Light Mode equivalent to checking media queries)
function initTheme() {
    const savedTheme = localStorage.getItem('theme');
    
    if (savedTheme) {
        document.documentElement.setAttribute('data-theme', savedTheme);
        updateToggleButton(savedTheme);
    } else {
        // Check system preference
        const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
        const theme = prefersDark ? 'dark' : 'light';
        document.documentElement.setAttribute('data-theme', theme);
        localStorage.setItem('theme', theme);
        updateToggleButton(theme);
    }
}

function updateToggleButton(theme) {
    const btn = document.getElementById('themeToggleBtn');
    if (btn) {
        // Using emoji/unicode for simplicity to avoid SVG overhead
        btn.innerHTML = theme === 'dark' ? '☀️' : '🌙'; 
    }
}

function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    
    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
    updateToggleButton(newTheme);
}

// Initialize immediately before DOM content loads to avoid flash
initTheme();

document.addEventListener('DOMContentLoaded', () => {
    // Re-verify the toggle button is in sync once the DOM is fully constructed
    const currentTheme = document.documentElement.getAttribute('data-theme');
    updateToggleButton(currentTheme || 'light');
    
    // Attach listener if the button exists
    const toggleBtn = document.getElementById('themeToggleBtn');
    if (toggleBtn) {
        toggleBtn.addEventListener('click', toggleTheme);
    }
});
