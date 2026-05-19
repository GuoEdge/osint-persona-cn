var Clock = (function () {
    'use strict';

    var canvas, ctx;
    var width, height, centerX, centerY, watchRadius;

    var H_COLOR = '#e8e8f0', M_COLOR = '#d0d0e0', S_COLOR = '#ff4444';
    var TICK_COLOR = 'rgba(180,200,230,0.35)', TICK_HI = 'rgba(255,255,255,0.6)';

    var ind = {
        battery: { v: 0.85, color: '#4fc3f7', label: '85%', icon: '🔋' },
        weather: { v: 0.5, color: '#ffb74d', label: '26°', icon: '☀' },
        heart: { v: 0.45, color: '#ef5350', label: '72', icon: '♥' },
        stress: { v: 0.25, color: '#ab47bc', label: '低', icon: '🧘' }
    };

    var timeStr = '00:00', dateStr = '', lunarStr = '';

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

    function drawQuadrantArc(startDeg, sweepDeg, value, color, label, icon) {
        var outR = watchRadius - 3;
        var inR = watchRadius - 18;
        var startA = (startDeg - 90) * Math.PI / 180;
        var sweepA = sweepDeg * Math.PI / 180;
        var endA = startA + sweepA;

        ctx.save();
        ctx.beginPath();
        ctx.arc(centerX, centerY, outR, startA, endA);
        ctx.arc(centerX, centerY, inR, endA, startA, true);
        ctx.closePath();
        ctx.clip();

        ctx.fillStyle = 'rgba(255,255,255,0.04)';
        ctx.fillRect(centerX - watchRadius, centerY - watchRadius, watchRadius * 2, watchRadius * 2);

        if (value > 0.001) {
            var clamped = Math.min(1, Math.max(0, value));
            var fillEnd = startA + sweepA * clamped;
            ctx.beginPath();
            ctx.arc(centerX, centerY, outR, startA, fillEnd);
            ctx.arc(centerX, centerY, inR, fillEnd, startA, true);
            ctx.closePath();
            ctx.shadowColor = color;
            ctx.shadowBlur = 8;
            ctx.fillStyle = color;
            ctx.fill();
            ctx.shadowBlur = 0;
        }

        ctx.restore();

        var outEdgeR = outR;
        ctx.beginPath();
        ctx.arc(centerX, centerY, outEdgeR, startA, endA);
        ctx.strokeStyle = 'rgba(120,150,220,0.2)';
        ctx.lineWidth = 1;
        ctx.stroke();

        var midA = startA + sweepA / 2;
        var iconR = watchRadius * 0.74;
        var textR = watchRadius * 0.65;
        var ix = centerX + Math.cos(midA) * iconR;
        var iy = centerY + Math.sin(midA) * iconR;
        var tx = centerX + Math.cos(midA) * textR;
        var ty = centerY + Math.sin(midA) * textR;

        var iSize = Math.max(12, Math.round(watchRadius * 0.07));
        var tSize = Math.max(10, Math.round(watchRadius * 0.065));
        ctx.font = iSize + 'px "PingFang SC","Helvetica Neue",sans-serif';
        ctx.fillStyle = 'rgba(255,255,255,0.9)';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(icon, ix, iy);

        ctx.font = 'bold ' + tSize + 'px "PingFang SC","Helvetica Neue",sans-serif';
        ctx.fillStyle = 'rgba(240,245,255,0.92)';
        ctx.fillText(label, tx, ty);
    }

    function drawProgressBars() {
        drawQuadrantArc(0, 90, ind.battery.v, ind.battery.color, ind.battery.label, ind.battery.icon);
        drawQuadrantArc(90, 90, ind.weather.v, ind.weather.color, ind.weather.label, ind.weather.icon);
        drawQuadrantArc(180, 90, ind.heart.v, ind.heart.color, ind.heart.label, ind.heart.icon);
        drawQuadrantArc(270, 90, ind.stress.v, ind.stress.color, ind.stress.label, ind.stress.icon);
    }

    function drawTickMarks() {
        var outR = watchRadius * 0.90;
        for (var i = 0; i < 60; i++) {
            var a = (i * 6 - 90) * Math.PI / 180;
            var isH = i % 5 === 0;
            var inR = isH ? watchRadius * 0.80 : watchRadius * 0.85;
            ctx.beginPath();
            ctx.moveTo(centerX + Math.cos(a) * inR, centerY + Math.sin(a) * inR);
            ctx.lineTo(centerX + Math.cos(a) * outR, centerY + Math.sin(a) * outR);
            ctx.strokeStyle = isH ? TICK_HI : TICK_COLOR;
            ctx.lineWidth = isH ? 2.5 : 0.8;
            ctx.lineCap = 'round';
            ctx.stroke();
        }
    }

    function drawBezel() {
        ctx.beginPath();
        ctx.arc(centerX, centerY, watchRadius, 0, Math.PI * 2);
        ctx.strokeStyle = 'rgba(120,150,220,0.18)';
        ctx.lineWidth = 2;
        ctx.stroke();
    }

    function drawHand(length, angle, w, color) {
        ctx.save();
        ctx.translate(centerX, centerY);
        ctx.rotate(angle);
        ctx.shadowColor = 'rgba(0,0,0,0.5)';
        ctx.shadowBlur = 5;
        ctx.shadowOffsetY = 2;
        ctx.beginPath();
        ctx.moveTo(0, w * 1.5);
        ctx.lineTo(-w, 0);
        ctx.lineTo(0, -length);
        ctx.lineTo(w, 0);
        ctx.closePath();
        var g = ctx.createLinearGradient(0, -length, 0, 0);
        g.addColorStop(0, color);
        g.addColorStop(1, 'rgba(255,255,255,0.5)');
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
        var len = watchRadius * 0.77;
        ctx.shadowColor = 'rgba(255,50,50,0.4)';
        ctx.shadowBlur = 6;
        ctx.beginPath();
        ctx.moveTo(0, 2.5);
        ctx.lineTo(2, 0);
        ctx.lineTo(0, -len);
        ctx.lineTo(-2, 0);
        ctx.closePath();
        ctx.fillStyle = S_COLOR;
        ctx.fill();
        ctx.shadowColor = 'transparent';
        ctx.shadowBlur = 0;
        ctx.beginPath();
        ctx.arc(0, 0, watchRadius * 0.04, 0, Math.PI * 2);
        ctx.fillStyle = S_COLOR;
        ctx.fill();
        ctx.beginPath();
        ctx.arc(0, 0, watchRadius * 0.02, 0, Math.PI * 2);
        ctx.fillStyle = '#fff';
        ctx.fill();
        ctx.restore();
    }

    function draw(timestamp) {
        ctx.clearRect(0, 0, width, height);

        drawProgressBars();
        drawBezel();
        drawTickMarks();

        var now = new Date();
        var h = now.getHours(), m = now.getMinutes(), s = now.getSeconds(), ms = now.getMilliseconds();
        var sA = ((s + ms / 1000) / 60) * Math.PI * 2 - Math.PI / 2;
        var mA = ((m + s / 60) / 60) * Math.PI * 2 - Math.PI / 2;
        var hA = ((h % 12 + m / 60) / 12) * Math.PI * 2 - Math.PI / 2;

        drawHand(watchRadius * 0.38, hA, watchRadius * 0.04, H_COLOR);
        drawHand(watchRadius * 0.54, mA, watchRadius * 0.028, M_COLOR);
        drawSecondHand(sA);

        timeStr = String(h).padStart(2, '0') + ':' + String(m).padStart(2, '0');
        var wk = ['周日','周一','周二','周三','周四','周五','周六'];
        dateStr = (now.getMonth() + 1) + '月' + now.getDate() + '日 ' + wk[now.getDay()];
        var lu = LunarCalendar.solarToLunar(now);
        lunarStr = LunarCalendar.getFestival(lu) || LunarCalendar.formatLunarDate(now);

        updateDOM();
    }

    function updateDOM() {
        var dt = document.getElementById('digital-time');
        if (dt) dt.textContent = timeStr;
        var dd = document.getElementById('date-display');
        if (dd) dd.textContent = dateStr;
        var ld = document.getElementById('lunar-display');
        if (ld) ld.textContent = lunarStr;
    }

    function updateIndicator(id, data) {
        if (ind[id]) Object.assign(ind[id], data);
    }

    return {
        init: init, draw: draw, resize: resize, updateIndicator: updateIndicator
    };
})();