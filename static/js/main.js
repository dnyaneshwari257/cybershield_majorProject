// static/js/main.js - Main JavaScript File

// Utility functions
function showLoading() {
    document.getElementById('loadingOverlay').style.display = 'flex';
}

function hideLoading() {
    document.getElementById('loadingOverlay').style.display = 'none';
}

function showAlert(message, type = 'success') {
    // Remove existing alerts
    const existingAlerts = document.querySelectorAll('.alert');
    existingAlerts.forEach(alert => alert.remove());
    
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type}`;
    
    // Add icon based on type
    let icon = '';
    switch(type) {
        case 'success':
            icon = '<i class="fas fa-check-circle"></i>';
            break;
        case 'error':
            icon = '<i class="fas fa-exclamation-circle"></i>';
            break;
        case 'info':
            icon = '<i class="fas fa-info-circle"></i>';
            break;
        default:
            icon = '<i class="fas fa-bell"></i>';
    }
    
    alertDiv.innerHTML = `${icon} ${message}`;
    
    const container = document.querySelector('.container');
    if (container) {
        container.insertBefore(alertDiv, container.firstChild);
    }
    
    // Auto-remove alert after 5 seconds
    setTimeout(() => {
        if (alertDiv.parentNode) {
            alertDiv.remove();
        }
    }, 5000);
}

// Password visibility toggle
function togglePassword(inputId = 'password', iconId = 'eyeIcon') {
    const passwordInput = document.getElementById(inputId);
    const eyeIcon = document.getElementById(iconId);
    
    if (passwordInput && eyeIcon) {
        if (passwordInput.type === 'password') {
            passwordInput.type = 'text';
            eyeIcon.className = 'fas fa-eye-slash';
        } else {
            passwordInput.type = 'password';
            eyeIcon.className = 'fas fa-eye';
        }
    }
}

// Form validation functions
function validateEmail(email) {
    const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return re.test(email);
}

function validatePhone(phone) {
    const re = /^[\+]?[1-9][\d]{0,15}$/;
    return re.test(phone.replace(/[\s\-\(\)]/g, ''));
}

function validateMoodleId(moodleId) {
    if(username.length < 1){
    alert("Username required");
}
}

// Registration form handler
function initializeRegistrationForm() {
    const form = document.getElementById('registerForm');
    if (!form) return;
    
    form.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        const formData = new FormData(this);
        const data = Object.fromEntries(formData.entries());
        
        // Client-side validation
        if (!data.full_name || data.full_name.length < 2) {
            showAlert('Please enter a valid full name (at least 2 characters)', 'error');
            return;
        }
        
        if (!data.email || !validateEmail(data.email)) {
            showAlert('Please enter a valid email address', 'error');
            return;
        }
        
        if (!data.phone || !validatePhone(data.phone)) {
            showAlert('Please enter a valid phone number', 'error');
            return;
        }
        
        if (!data.course) {
            showAlert('Please select a course', 'error');
            return;
        }
        
        showLoading();
        
        try {
            
            const response = await fetch('/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data)
});

const result = await response.json();

if (result.success) {
    showAlert(`🎉 Registration successful! Your Moodle ID: ${result.username}. Check your email for password.`, 'success');
    this.reset();
    setTimeout(() => window.location.href = '/login', 3000);
} else {
    showAlert(result.message || 'Registration failed', 'error');
}

        } catch (error) {
            console.error('Registration error:', error);
            showAlert('Registratio  n failed. Please try again later.', 'error');
        } finally {
            hideLoading();
        }
    });
    
    // Real-time validation feedback
    const emailInput = form.querySelector('input[name="email"]');
    if (emailInput) {
        emailInput.addEventListener('blur', function() {
            if (this.value && !validateEmail(this.value)) {
                this.style.borderColor = '#f56565';
                showAlert('Please enter a valid email address', 'error');
            } else {
                this.style.borderColor = '#e1e5e9';
            }
        });
    }
    
    const phoneInput = form.querySelector('input[name="phone"]');
    if (phoneInput) {
        phoneInput.addEventListener('blur', function() {
            if (this.value && !validatePhone(this.value)) {
                this.style.borderColor = '#f56565';
                showAlert('Please enter a valid phone number', 'error');
            } else {
                this.style.borderColor = '#e1e5e9';
            }
        });
    }
}

// Login form handler
function initializeLoginForm() {
    const form = document.getElementById('loginForm');
    if (!form) return;
    
    form.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        const formData = new FormData(this);
        const data = Object.fromEntries(formData.entries());
        
        // Client-side validation
        if (!data.moodle_id) {
            showAlert('Please enter your Moodle ID', 'error');
            return;
        }
        
        if (!validateMoodleId(data.moodle_id)) {
            showAlert('Please enter a valid Moodle ID format (e.g., EDU24001)', 'error');
            return;
        }
        
        if (!data.password) {
            showAlert('Please enter your password', 'error');
            return;
        }
        
        showLoading();
        
        try {
            const response = await fetch('/login', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                 credentials: 'include', //new addition to ensure session remains same
                body: JSON.stringify(data)
            });
            
           
            const result = await response.json();

if (result.success) {
    if (result.must_change_password) {
        showAlert('Please update your password', 'info');
        setTimeout(() => {
            window.location.href = '/change-password';
        }, 1500);
    } else {
        showAlert('🎉 Login successful! Redirecting to dashboard...', 'success');
        setTimeout(() => {
            window.location.href = result.redirect || '/dashboard'; //change made here result.redirect
        }, 1500);
    }
} else {
    showAlert(result.message, 'error');
    form.querySelector('input[name="password"]').value = '';
}

        } catch (error) {
            console.error('Login error:', error);
            showAlert('Login failed. Please try again later.', 'error');
        } finally {
            hideLoading();
        }
    });
    
    // Auto-format Moodle ID input
    const moodleIdInput = form.querySelector('input[name="moodle_id"]');
    if (moodleIdInput) {
        moodleIdInput.addEventListener('input', function(e) {
            e.target.value = e.target.value.toUpperCase();
        });
        
        moodleIdInput.addEventListener('blur', function() {
            if (this.value && !validateMoodleId(this.value)) {
                this.style.borderColor = '#f56565';
                showAlert('Moodle ID should be in format: EDU24001', 'error');
            } else {
                this.style.borderColor = '#e1e5e9';
            }
        });
    }
}

// Add floating particles animation
function createFloatingParticles() {
    const particlesContainer = document.querySelector('.floating-particles');
    if (!particlesContainer) return;
    
    // Add more particles dynamically
    for (let i = 6; i <= 15; i++) {
        const particle = document.createElement('div');
        particle.className = 'particle';
        
        // Random properties
        const size = Math.random() * 15 + 5;
        const left = Math.random() * 100;
        const animationDelay = Math.random() * 5;
        const animationDuration = Math.random() * 10 + 10;
        
        particle.style.cssText = `
            left: ${left}%;
            width: ${size}px;
            height: ${size}px;
            animation-delay: ${animationDelay}s;
            animation-duration: ${animationDuration}s;
        `;
        
        particlesContainer.appendChild(particle);
    }
}

// Dashboard animations
function initializeDashboard() {
    const statCards = document.querySelectorAll('.stat-card');
    
    // Animate stat numbers
    statCards.forEach((card, index) => {
        const statNumber = card.querySelector('.stat-number');
        if (statNumber) {
            const finalValue = parseInt(statNumber.textContent);
            let currentValue = 0;
            const increment = finalValue / 50;
            
            setTimeout(() => {
                const timer = setInterval(() => {
                    currentValue += increment;
                    if (currentValue >= finalValue) {
                        currentValue = finalValue;
                        clearInterval(timer);
                    }
                    
                    if (statNumber.textContent.includes('%')) {
                        statNumber.textContent = Math.round(currentValue) + '%';
                    } else if (statNumber.textContent.includes('h')) {
                        statNumber.textContent = Math.round(currentValue) + 'h';
                    } else {
                        statNumber.textContent = Math.round(currentValue);
                    }
                }, 30);
            }, index * 200);
        }
    });
}

// Smooth scrolling for anchor links
function initializeSmoothScrolling() {
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();
            const target = document.querySelector(this.getAttribute('href'));
            if (target) {
                target.scrollIntoView({
                    behavior: 'smooth',
                    block: 'start'
                });
            }
        });
    });
}

// Form input animations
function initializeFormAnimations() {
    const inputs = document.querySelectorAll('.form-input');
    
    inputs.forEach(input => {
        input.addEventListener('focus', function() {
            this.parentElement.classList.add('focused');
        });
        
        input.addEventListener('blur', function() {
            if (!this.value) {
                this.parentElement.classList.remove('focused');
            }
        });
        
        // Check if input has value on page load
        if (input.value) {
            input.parentElement.classList.add('focused');
        }
    });
}

// Keyboard shortcuts
function initializeKeyboardShortcuts() {
    document.addEventListener('keydown', function(e) {
        // Escape key to close modals/alerts
        if (e.key === 'Escape') {
            const alerts = document.querySelectorAll('.alert');
            alerts.forEach(alert => alert.remove());
            
            const loadingOverlay = document.getElementById('loadingOverlay');
            if (loadingOverlay && loadingOverlay.style.display === 'flex') {
                hideLoading();
            }
        }
        
        // Ctrl/Cmd + Enter to submit forms
        if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
            const activeForm = document.querySelector('form');
            if (activeForm) {
                activeForm.dispatchEvent(new Event('submit'));
            }
        }
    });
}

// Session timeout warning
function initializeSessionTimeout() {
    let timeoutWarning;
    let sessionTimeout;
    
    function resetSessionTimer() {
        clearTimeout(timeoutWarning);
        clearTimeout(sessionTimeout);
        
        // Warn user 2 minutes before session expires (28 minutes)
        timeoutWarning = setTimeout(() => {
            showAlert('Your session will expire in 2 minutes. Please save your work.', 'info');
        }, 28 * 60 * 1000);
        
        // Auto-logout after 30 minutes of inactivity
        sessionTimeout = setTimeout(() => {
            showAlert('Session expired. Redirecting to login...', 'error');
            setTimeout(() => {
                window.location.href = '/login';
            }, 2000);
        }, 30 * 60 * 1000);
    }
    
    // Reset timer on user activity
    ['mousedown', 'mousemove', 'keypress', 'scroll', 'touchstart'].forEach(event => {
        document.addEventListener(event, resetSessionTimer, true);
    });
    
    // Initialize timer
    resetSessionTimer();
}

// Accessibility improvements
function initializeAccessibility() {
    // Add skip to content link
    const skipLink = document.createElement('a');
    skipLink.href = '#main-content';
    skipLink.textContent = 'Skip to main content';
    skipLink.className = 'skip-link';
    skipLink.style.cssText = `
        position: absolute;
        top: -40px;
        left: 6px;
        background: #667eea;
        color: white;
        padding: 8px;
        text-decoration: none;
        z-index: 1000;
        border-radius: 4px;
    `;
    
    skipLink.addEventListener('focus', () => {
        skipLink.style.top = '6px';
    });
    
    skipLink.addEventListener('blur', () => {
        skipLink.style.top = '-40px';
    });
    
    document.body.insertBefore(skipLink, document.body.firstChild);
    
    // Add main content landmark
    const mainContent = document.querySelector('.container');
    if (mainContent && !mainContent.id) {
        mainContent.id = 'main-content';
    }
}

// Error handling for failed network requests
function handleNetworkError(error) {
    console.error('Network error:', error);
    showAlert('Network connection error. Please check your internet connection and try again.', 'error');
}

// Initialize all components when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    // Core functionality
    initializeRegistrationForm();
    initializeLoginForm();
    initializeDashboard();
    
    // UI enhancements
    createFloatingParticles();
    initializeSmoothScrolling();
    initializeFormAnimations();
    initializeKeyboardShortcuts();
    initializeAccessibility();
    
    // Session management (only for authenticated pages)
    if (window.location.pathname === '/dashboard') {
        initializeSessionTimeout();
    }
    
    // Add loading states to all buttons
    const buttons = document.querySelectorAll('.btn');
    buttons.forEach(button => {
        button.addEventListener('click', function() {
            if (this.type === 'submit') {
                setTimeout(() => {
                    this.classList.add('loading');
                }, 100);
            }
        });
    });
});

// Global error handler
window.addEventListener('error', function(e) {
    console.error('Global error:', e.error);
    showAlert('An unexpected error occurred. Please refresh the page and try again.', 'error');
});

// Global unhandled promise rejection handler
window.addEventListener('unhandledrejection', function(e) {
    console.error('Unhandled promise rejection:', e.reason);
    handleNetworkError(e.reason);
});

// Export functions for global access
window.EduLearnApp = {
    showAlert,
    showLoading,
    hideLoading,
    togglePassword,
    validateEmail,
    validatePhone,
    validateMoodleId
};


