// ===================================================
// STAINLESS MAX — Premium Landing Page Scripts
// ===================================================

// Particle Canvas Background
(function initParticles() {
    const canvas = document.getElementById('particles');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    let w, h, particles = [];
    const PARTICLE_COUNT = 60;

    function resize() {
        w = canvas.width = window.innerWidth;
        h = canvas.height = window.innerHeight;
    }
    resize();
    window.addEventListener('resize', resize);

    class Particle {
        constructor() { this.reset(); }
        reset() {
            this.x = Math.random() * w;
            this.y = Math.random() * h;
            this.vx = (Math.random() - 0.5) * 0.3;
            this.vy = (Math.random() - 0.5) * 0.3;
            this.radius = Math.random() * 1.5 + 0.5;
            this.opacity = Math.random() * 0.4 + 0.1;
        }
        update() {
            this.x += this.vx;
            this.y += this.vy;
            if (this.x < 0 || this.x > w) this.vx *= -1;
            if (this.y < 0 || this.y > h) this.vy *= -1;
        }
        draw() {
            ctx.beginPath();
            ctx.arc(this.x, this.y, this.radius, 0, Math.PI * 2);
            ctx.fillStyle = `rgba(99, 102, 241, ${this.opacity})`;
            ctx.fill();
        }
    }

    for (let i = 0; i < PARTICLE_COUNT; i++) particles.push(new Particle());

    function connectParticles() {
        for (let i = 0; i < particles.length; i++) {
            for (let j = i + 1; j < particles.length; j++) {
                const dx = particles[i].x - particles[j].x;
                const dy = particles[i].y - particles[j].y;
                const dist = Math.sqrt(dx * dx + dy * dy);
                if (dist < 120) {
                    ctx.beginPath();
                    ctx.moveTo(particles[i].x, particles[i].y);
                    ctx.lineTo(particles[j].x, particles[j].y);
                    ctx.strokeStyle = `rgba(99, 102, 241, ${0.06 * (1 - dist / 120)})`;
                    ctx.lineWidth = 0.5;
                    ctx.stroke();
                }
            }
        }
    }

    function animate() {
        ctx.clearRect(0, 0, w, h);
        particles.forEach(p => { p.update(); p.draw(); });
        connectParticles();
        requestAnimationFrame(animate);
    }
    animate();
})();


// Navbar scroll effect
const navbar = document.getElementById('navbar');
let lastScroll = 0;
window.addEventListener('scroll', () => {
    const scrollY = window.scrollY;
    navbar.classList.toggle('scrolled', scrollY > 60);
    lastScroll = scrollY;
}, { passive: true });


// Smooth scroll for anchor links
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
        e.preventDefault();
        const target = document.querySelector(this.getAttribute('href'));
        if (target) {
            const mobileMenu = document.getElementById('mobileMenu');
            if (mobileMenu) mobileMenu.classList.remove('open');
            target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    });
});


// Mobile menu toggle
const mobileMenuBtn = document.getElementById('mobileMenuBtn');
const mobileMenu = document.getElementById('mobileMenu');
if (mobileMenuBtn && mobileMenu) {
    mobileMenuBtn.addEventListener('click', () => {
        mobileMenu.classList.toggle('open');
    });
}


// Set current year
const yearEl = document.getElementById('year');
if (yearEl) yearEl.textContent = new Date().getFullYear();


// Scroll-triggered fade-in animations
const animElements = document.querySelectorAll('.anim-fade');

const observerOptions = {
    threshold: 0.1,
    rootMargin: '0px 0px -60px 0px'
};

const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            entry.target.classList.add('visible');
            observer.unobserve(entry.target);
        }
    });
}, observerOptions);

animElements.forEach(el => observer.observe(el));


// Animated stat counter
function animateCounters() {
    const counters = document.querySelectorAll('.stat-number[data-target]');
    counters.forEach(counter => {
        const target = +counter.getAttribute('data-target');
        const duration = 2000;
        const startTime = performance.now();

        function update(currentTime) {
            const elapsed = currentTime - startTime;
            const progress = Math.min(elapsed / duration, 1);

            // Easing: easeOutExpo
            const eased = 1 - Math.pow(2, -10 * progress);
            counter.textContent = Math.floor(eased * target);

            if (progress < 1) {
                requestAnimationFrame(update);
            } else {
                counter.textContent = target;
            }
        }

        requestAnimationFrame(update);
    });
}

// Trigger counters when hero is visible
const heroSection = document.getElementById('hero');
if (heroSection) {
    const heroObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                animateCounters();
                heroObserver.unobserve(entry.target);
            }
        });
    }, { threshold: 0.3 });
    heroObserver.observe(heroSection);
}


// Tilt effect for mockup window on mouse move (desktop only)
const heroVisual = document.querySelector('.hero-visual .mockup-window:not(.small)');
if (heroVisual && window.innerWidth > 1024) {
    const heroArea = document.querySelector('.hero');
    heroArea.addEventListener('mousemove', (e) => {
        const rect = heroArea.getBoundingClientRect();
        const x = (e.clientX - rect.left) / rect.width - 0.5;
        const y = (e.clientY - rect.top) / rect.height - 0.5;
        heroVisual.style.transform = `perspective(1200px) rotateY(${x * 8}deg) rotateX(${-y * 6}deg)`;
    });
    heroArea.addEventListener('mouseleave', () => {
        heroVisual.style.transform = 'perspective(1200px) rotateY(-4deg) rotateX(2deg)';
    });
}


// Parallax blobs on scroll
window.addEventListener('scroll', () => {
    const scrollY = window.scrollY;
    const blobs = document.querySelectorAll('.blob');
    blobs.forEach((blob, i) => {
        const speed = 0.03 + i * 0.015;
        blob.style.transform = `translateY(${scrollY * speed}px)`;
    });
}, { passive: true });
