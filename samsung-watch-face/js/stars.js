var Starfield = (function () {
    'use strict';

    var canvas, ctx, stars = [];
    var width, height, centerX, centerY, radius;
    var animationId;

    var STAR_COUNT = 200;
    var NEBULA_COLORS = [
        'rgba(30, 20, 80, 0.03)',
        'rgba(20, 10, 60, 0.02)',
        'rgba(40, 10, 70, 0.025)',
        'rgba(10, 20, 50, 0.02)'
    ];

    function Star() {
        this.reset();
    }

    Star.prototype.reset = function () {
        var angle = Math.random() * Math.PI * 2;
        var dist = Math.random() * radius * 0.95;
        this.x = centerX + Math.cos(angle) * dist;
        this.y = centerY + Math.sin(angle) * dist;
        this.size = Math.random() * 1.8 + 0.3;
        this.brightness = Math.random();
        this.twinkleSpeed = Math.random() * 0.02 + 0.005;
        this.twinkleOffset = Math.random() * Math.PI * 2;
        this.hue = Math.random() < 0.15 ? Math.random() * 60 + 200 : 0;
        this.saturation = this.hue > 0 ? '60%' : '0%';
    };

    function init() {
        canvas = document.getElementById('bg-canvas');
        ctx = canvas.getContext('2d');
        resize();
        createStars();
    }

    function resize() {
        width = window.innerWidth;
        height = window.innerHeight;
        var dpr = window.devicePixelRatio || 1;
        canvas.width = width * dpr;
        canvas.height = height * dpr;
        canvas.style.width = width + 'px';
        canvas.style.height = height + 'px';
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        centerX = width / 2;
        centerY = height / 2;
        radius = Math.min(width, height) / 2;
    }

    function createStars() {
        stars = [];
        for (var i = 0; i < STAR_COUNT; i++) {
            stars.push(new Star());
        }
    }

    function drawNebula() {
        for (var i = 0; i < NEBULA_COLORS.length; i++) {
            var cx = centerX + (Math.sin(i * 1.7) * radius * 0.35);
            var cy = centerY + (Math.cos(i * 2.1) * radius * 0.35);
            var grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius * 0.5);
            grad.addColorStop(0, NEBULA_COLORS[i]);
            grad.addColorStop(1, 'transparent');

            ctx.save();
            ctx.beginPath();
            ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
            ctx.clip();
            ctx.fillStyle = grad;
            ctx.fillRect(centerX - radius, centerY - radius, radius * 2, radius * 2);
            ctx.restore();
        }
    }

    function drawStars(time) {
        ctx.save();
        ctx.beginPath();
        ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
        ctx.clip();

        for (var i = 0; i < stars.length; i++) {
            var s = stars[i];
            var twinkle = 0.5 + 0.5 * Math.sin(time * s.twinkleSpeed + s.twinkleOffset);
            var alpha = 0.4 + twinkle * 0.6;

            ctx.beginPath();
            ctx.arc(s.x, s.y, s.size, 0, Math.PI * 2);

            if (s.hue > 0) {
                ctx.fillStyle = 'hsla(' + s.hue + ', ' + s.saturation + ', 80%, ' + alpha + ')';
            } else {
                ctx.fillStyle = 'rgba(255, 255, 255, ' + alpha + ')';
            }
            ctx.fill();

            if (twinkle > 0.85 && s.size > 1.0) {
                ctx.beginPath();
                ctx.arc(s.x, s.y, s.size * 1.8, 0, Math.PI * 2);
                ctx.fillStyle = 'rgba(255, 255, 255, ' + (alpha * 0.15) + ')';
                ctx.fill();
            }
        }

        ctx.restore();
    }

    function drawEdgeGlow() {
        ctx.save();
        ctx.beginPath();
        ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
        ctx.clip();

        var edgeGrad = ctx.createRadialGradient(centerX, centerY, radius * 0.82, centerX, centerY, radius);
        edgeGrad.addColorStop(0, 'transparent');
        edgeGrad.addColorStop(1, 'rgba(40, 60, 120, 0.12)');

        ctx.fillStyle = edgeGrad;
        ctx.fillRect(centerX - radius, centerY - radius, radius * 2, radius * 2);
        ctx.restore();
    }

    function draw(time) {
        ctx.clearRect(0, 0, width, height);

        ctx.fillStyle = '#020210';
        ctx.fillRect(0, 0, width, height);

        drawNebula();
        drawStars(time);
        drawEdgeGlow();
    }

    function animate(timestamp) {
        draw(timestamp);
        animationId = requestAnimationFrame(animate);
    }

    function start() {
        if (animationId) return;
        animationId = requestAnimationFrame(animate);
    }

    function stop() {
        if (animationId) {
            cancelAnimationFrame(animationId);
            animationId = null;
        }
    }

    return {
        init: init,
        start: start,
        stop: stop,
        resize: resize
    };
})();