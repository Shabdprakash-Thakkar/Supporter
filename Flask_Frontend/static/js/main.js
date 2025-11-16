// ==================== MAIN JAVASCRIPT FILE ====================

// Wait for DOM to be fully loaded
document.addEventListener('DOMContentLoaded', function() {
    console.log('🚀 Supporter BOT Frontend Loaded');
    
    // Initialize animations
    initScrollAnimations();
    
    // Initialize smooth scrolling
    initSmoothScroll();
    
    // Initialize navbar effects
    initNavbarEffects();
});

// ==================== SCROLL ANIMATIONS ====================
function initScrollAnimations() {
    const observerOptions = {
        threshold: 0.1,
        rootMargin: '0px 0px -100px 0px'
    };
    
    const observer = new IntersectionObserver(function(entries) {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('animate-slide-up');
                observer.unobserve(entry.target);
            }
        });
    }, observerOptions);
    
    // Observe all cards and sections
    document.querySelectorAll('.stat-card, .feature-card, .command-category, .info-card').forEach(el => {
        observer.observe(el);
    });
}

// ==================== SMOOTH SCROLLING ====================
function initSmoothScroll() {
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            const href = this.getAttribute('href');
            if (href === '#') return;
            
            e.preventDefault();
            const target = document.querySelector(href);
            
            if (target) {
                const offset = 80; // Navbar height
                const targetPosition = target.getBoundingClientRect().top + window.pageYOffset - offset;
                
                window.scrollTo({
                    top: targetPosition,
                    behavior: 'smooth'
                });
            }
        });
    });
}

// ==================== NAVBAR EFFECTS ====================
function initNavbarEffects() {
    const navbar = document.querySelector('.navbar');
    let lastScroll = 0;
    
    window.addEventListener('scroll', function() {
        const currentScroll = window.pageYOffset;
        
        // Add shadow on scroll
        if (currentScroll > 50) {
            navbar.classList.add('shadow-lg');
        } else {
            navbar.classList.remove('shadow-lg');
        }
        
        lastScroll = currentScroll;
    });
}

// ==================== NUMBER COUNTER ANIMATION ====================
function animateCounter(element, target, duration = 2000) {
    let current = 0;
    const increment = target / (duration / 16);
    const isFloat = target.toString().includes('.');
    
    const timer = setInterval(() => {
        current += increment;
        if (current >= target) {
            element.textContent = isFloat ? target.toFixed(1) : Math.floor(target);
            clearInterval(timer);
        } else {
            element.textContent = isFloat ? current.toFixed(1) : Math.floor(current);
        }
    }, 16);
}

// ==================== UTILITY FUNCTIONS ====================

// Format numbers with commas
function formatNumber(num) {
    return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

// Show toast notification
function showToast(message, type = 'success') {
    const toast = document.createElement('div');
    toast.className = `alert alert-${type} position-fixed top-0 start-50 translate-middle-x mt-3 shadow-lg`;
    toast.style.zIndex = '9999';
    toast.style.minWidth = '300px';
    toast.innerHTML = `
        <i class="fas fa-${type === 'success' ? 'check' : 'exclamation'}-circle me-2"></i>
        ${message}
    `;
    
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.classList.add('fade');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// Copy text to clipboard
async function copyToClipboard(text) {
    try {
        await navigator.clipboard.writeText(text);
        showToast('Copied to clipboard!', 'success');
    } catch (err) {
        console.error('Failed to copy:', err);
        showToast('Failed to copy!', 'danger');
    }
}

// ==================== CONSOLE MESSAGE ====================
console.log('%c🤖 Supporter BOT', 'color: #5865F2; font-size: 24px; font-weight: bold;');
console.log('%cFrontend by Supporter BOT Team', 'color: #57F287; font-size: 14px;');
console.log('%cInterested in the bot? Add it to your server!', 'color: #999; font-size: 12px;');
