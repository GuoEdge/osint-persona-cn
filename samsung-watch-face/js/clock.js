var Clock = (function () {
    'use strict';

    var canvas, ctx;
    var width, height, centerX, centerY, watchRadius;
    var animationId;

    var HOUR_COLOR = '#e8e8f0';
    var MIN_COLOR = '#d0d0e0';
    var SEC_COLOR = '#ff4444';
    var TICK_COLOR = 'rgba(200,210,240,0.45)';
    var TICK_HI = 'rgba(255,255,255,0.7)';

    var indicators = {
        weather: { value: 0.5, color: '#4fc3f7', icon: '☀', text: '26°' },
        battery: { value: 0.85, color: '#66bb6a', icon: '🔋', text: '85%' },
        heart: { value: 0.45, color: '#ef5350', icon: '♥', text: '72' },
        stress: { value: 0.25, color: '#ab47bc', icon: '🧘', text: '低' }
    };

    var timeStr = '00:00';
    var dateStr = '';
    var lunarStr = '';
    var weatherStr = '';

    function updateIndicator(id, data) {
        if (indicators[id]) {
            Object.assign(indicators[id], data);
        }
    }

    function init() {
        canvas = document.getElementById('clock-canvas');
        ctx = canvas.getContext('2d');
        resize();
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
        watchRadius = Math.min(width, height) / 2;
    }

    function drawArcProgress(cx, cy, startAngle, sweepAngle, value, color) {
        var outerR = watchRadius - 4;
        var innerR = watchRadius - 10;

        ctx.save();
        ctx.beginPath();
        ctx.arc(cx, cy, watchRadius, startAngle - 0.01, startAngle + sweepAngle + 0.01);
        ctx.arc(cx, cy, innerR, startAngle + sweepAngle + 0.01, startAngle - 0.01, true);
        ctx.clip();

        var bgGrad = ctx.createLinearGradient(
            cx + Math.cos(startAngle) * outerR, cy + Math.sin(startAngle) * outerR,
            cx, cy
        );
        bgGrad.addColorStop(0, 'rgba(255,255,255,0.08)');
        bgGrad.addColorStop(1, 'rgba(255,255,255,0.02)');
        ctx.fillStyle = bgGrad;
        ctx.fillRect(cx - watchRadius, cy - watchRadius, watchRadius * 2, watchRadius * 2);

        if (value > 0.001) {
            var fillEnd = startAngle + sweepAngle * Math.min(1, Math.max(0, value));
            ctx.beginPath();
            ctx.arc(cx, cy, outerR, startAngle, fillEnd);
            ctx.arc(cx, cy, innerR, fillEnd, startAngle, true);
            ctx.closePath();

            var fillGrad = ctx.createLinearGradient(
                cx + Math.cos(startAngle) * outerR, cy + Math.sin(startAngle) * outerR,
                cx + Math.cos(startAngle + sweepAngle) * outerR, cy + Math.sin(startAngle + sweepAngle) * outerR
            );
            fillGrad.addColorStop(0, color);
            fillGrad.addColorStop(1, color.replace(')', ',0.7)').replace('rgb', 'rgba'));
            ctx.fillStyle = fillGrad;
            ctx.fill();
        }

        ctx.restore();
    }

    function drawProgressBars() {
        var arcs = [
            { id: 'weather', centerAngle: -Math.PI / 2, span: 0.35 },
            { id: 'battery', centerAngle: 0, span: 0.35 },
            { id: 'heart', centerAngle: Math.PI / 2, span: 0.35 },
            { id: 'stress', centerAngle: Math.PI, span: 0.35 }
        ];

        for (var i = 0; i < arcs.length; i++) {
            var a = arcs[i];
            var startAngle = a.centerAngle - a.span;
            var sweepAngle = a.span * 2;
            var data = indicators[a.id];
            drawArcProgress(centerX, centerY, startAngle, sweepAngle, data.value, data.color);
        }
    }

    function drawTickMarks() {
        var outerR = watchRadius * 0.88;
        for (var i = 0; i < 60; i++) {
            var angle = (i * 6 - 90) * Math.PI / 180;
            var isHour = i % 5 === 0;
            var innerR = isHour ? watchRadius * 0.78 : watchRadius * 0.83;
            ctx.beginPath();
            ctx.moveTo(centerX + Math.cos(angle) * innerR, centerY + Math.sin(angle) * innerR);
            ctx.lineTo(centerX + Math.cos(angle) * outerR, centerY + Math.sin(angle) * outerR);
            ctx.strokeStyle = isHour ? TICK_HI : TICK_COLOR;
            ctx.lineWidth = isHour ? 2.5 : 1;
            ctx.lineCap = 'round';
            ctx.stroke();
        }
    }

    function drawHand(length, angle, w, color, shadow) {
        ctx.save();
        ctx.translate(centerX, centerY);
        ctx.rotate(angle);
        if (shadow) {
            ctx.shadowColor = 'rgba(0,0,0,0.6)';
            ctx.shadowBlur = 5;
            ctx.shadowOffsetX = 1;
            ctx.shadowOffsetY = 2;
        }
        ctx.beginPath();
        ctx.moveTo(0, w * 1.5);
        ctx.lineTo(-w, 0);
        ctx.lineTo(0, -length);
        ctx.lineTo(w, 0);
        ctx.closePath();
        var g = ctx.createLinearGradient(0, -length, 0, 0);
        g.addColorStop(0, color);
        g.addColorStop(1, 'rgba(255,255,255,0.6)');
        ctx.fillStyle = g;
        ctx.fill();
        ctx.shadowColor = 'transparent';
        ctx.shadowBlur = 0;
        ctx.restore();
    }

    function drawSecondHand(angle) {
        ctx.save();
        ctx.translate(centerX, centerY);
        ctx.rotate(angle);
        var len = watchRadius * 0.75;
        ctx.shadowColor = 'rgba(255,50,50,0.5)';
        ctx.shadowBlur = 6;
        ctx.beginPath();
        ctx.moveTo(0, 3);
        ctx.lineTo(2, 0);
        ctx.lineTo(0, -len);
        ctx.lineTo(-2, 0);
        ctx.closePath();
        ctx.fillStyle = SEC_COLOR;
        ctx.fill();
        ctx.shadowColor = 'transparent';
        ctx.shadowBlur = 0;
        ctx.beginPath();
        ctx.arc(0, 0, watchRadius * 0.04, 0, Math.PI * 2);
        ctx.fillStyle = SEC_COLOR;
        ctx.fill();
        ctx.beginPath();
        ctx.arc(0, 0, watchRadius * 0.02, 0, Math.PI * 2);
        ctx.fillStyle = '#ffffff';
        ctx.fill();
        ctx.restore();
    }

    function drawBezel() {
        ctx.beginPath();
        ctx.arc(centerX, centerY, watchRadius, 0, Math.PI * 2);
        ctx.strokeStyle = 'rgba(120,150,220,0.25)';
        ctx.lineWidth = 2;
        ctx.stroke();
        ctx.beginPath();
        ctx.arc(centerX, centerY, watchRadius - 12, 0, Math.PI * 2);
        ctx.strokeStyle = 'rgba(60,80,140,0.12)';
        ctx.lineWidth = 1;
        ctx.stroke();
    }

    function draw(timestamp) {
        ctx.clearRect(0, 0, width, height);

        drawProgressBars();
        drawBezel();
        drawTickMarks();

        var now = new Date();
        var h = now.getHours();
        var m = now.getMinutes();
        var s = now.getSeconds();
        var ms = now.getMilliseconds();

        var sAngle = ((s + ms / 1000) / 60) * Math.PI * 2 - Math.PI / 2;
        var mAngle = ((m + s / 60) / 60) * Math.PI * 2 - Math.PI / 2;
        var hAngle = ((h % 12 + m / 60) / 12) * Math.PI * 2 - Math.PI / 2;

        drawHand(watchRadius * 0.4, hAngle, watchRadius * 0.038, HOUR_COLOR, true);
        drawHand(watchRadius * 0.56, mAngle, watchRadius * 0.028, MIN_COLOR, true);
        drawSecondHand(sAngle);

        timeStr = String(h).padStart(2, '0') + ':' + String(m).padStart(2, '0');

        var weekdays = ['周日','周一','周二','周三','周四','周五','周六'];
        dateStr = (now.getMonth() + 1) + '月' + now.getDate() + '日 ' + weekdays[now.getDay()];

        var lunar = LunarCalendar.solarToLunar(now);
        var festival = LunarCalendar.getFestival(lunar);
        lunarStr = festival || LunarCalendar.formatLunarDate(now);

        updateDOM();
    }

    function updateDOM() {
        var dt = document.getElementById('digital-time');
        if (dt) dt.textContent = timeStr;

        var dd = document.getElementById('date-display');
        if (dd) dd.textContent = dateStr;

        var ld = document.getElementById('lunar-display');
        if (ld) ld.textContent = lunarStr;

        var wi = document.getElementById('indicator-weather');
        if (wi) {
            wi.querySelector('.indicator-icon').textContent = indicators.weather.icon;
            wi.querySelector('.indicator-value').textContent = indicators.weather.text;
        }
        var bi = document.getElementById('indicator-battery');
        if (bi) {
            bi.querySelector('.indicator-icon').textContent = indicators.battery.icon;
            bi.querySelector('.indicator-value').textContent = indicators.battery.text;
        }
        var hi = document.getElementById('indicator-heart');
        if (hi) {
            hi.querySelector('.indicator-icon').textContent = indicators.heart.icon;
            hi.querySelector('.indicator-value').textContent = indicators.heart.text;
        }
        var si = document.getElementById('indicator-stress');
        if (si) {
            si.querySelector('.indicator-icon').textContent = indicators.stress.icon;
            si.querySelector('.indicator-value').textContent = indicators.stress.text;
        }
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
        resize: resize,
        draw: draw,
        updateIndicator: updateIndicator
    };
})();