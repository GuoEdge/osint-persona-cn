var Clock = (function () {
    'use strict';

    var canvas, ctx;
    var width, height, centerX, centerY, watchRadius;
    var animationId;

    var HOUR_HAND_COLOR = '#e8e8f0';
    var MINUTE_HAND_COLOR = '#d0d0e0';
    var SECOND_HAND_COLOR = '#ff4444';
    var TICK_COLOR = 'rgba(200, 210, 240, 0.5)';
    var TICK_HIGHLIGHT_COLOR = 'rgba(255, 255, 255, 0.8)';

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

    function drawTickMarks() {
        var outerRadius = watchRadius * 0.92;
        var innerRadiusLong = watchRadius * 0.82;
        var innerRadiusShort = watchRadius * 0.86;

        for (var i = 0; i < 60; i++) {
            var angle = (i * 6 - 90) * Math.PI / 180;
            var isHour = i % 5 === 0;
            var innerR = isHour ? innerRadiusLong : innerRadiusShort;
            var tickWidth = isHour ? 2.5 : 1;

            ctx.beginPath();
            ctx.moveTo(
                centerX + Math.cos(angle) * innerR,
                centerY + Math.sin(angle) * innerR
            );
            ctx.lineTo(
                centerX + Math.cos(angle) * outerRadius,
                centerY + Math.sin(angle) * outerRadius
            );
            ctx.strokeStyle = isHour ? TICK_HIGHLIGHT_COLOR : TICK_COLOR;
            ctx.lineWidth = tickWidth;
            ctx.lineCap = 'round';
            ctx.stroke();
        }

        var numRadius = watchRadius * 0.72;
        var hourMarks = [12, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11];
        for (var j = 0; j < 12; j++) {
            var numAngle = (j * 30 - 90) * Math.PI / 180;
            var nx = centerX + Math.cos(numAngle) * numRadius;
            var ny = centerY + Math.sin(numAngle) * numRadius;

            ctx.font = 'bold ' + (watchRadius * 0.08) + 'px "Helvetica Neue", sans-serif';
            ctx.fillStyle = 'rgba(255, 255, 255, 0.7)';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText(hourMarks[j], nx, ny);
        }
    }

    function drawHand(length, angle, width, color, shadow) {
        ctx.save();
        ctx.translate(centerX, centerY);
        ctx.rotate(angle);

        if (shadow) {
            ctx.shadowColor = 'rgba(0, 0, 0, 0.6)';
            ctx.shadowBlur = 4;
            ctx.shadowOffsetX = 1;
            ctx.shadowOffsetY = 2;
        }

        ctx.beginPath();
        ctx.moveTo(0, width * 1.5);
        ctx.lineTo(-width, 0);
        ctx.lineTo(0, -length);
        ctx.lineTo(width, 0);
        ctx.closePath();

        var grad = ctx.createLinearGradient(0, -length, 0, 0);
        grad.addColorStop(0, color);
        grad.addColorStop(1, 'rgba(255, 255, 255, 0.6)');
        ctx.fillStyle = grad;
        ctx.fill();

        ctx.shadowColor = 'transparent';
        ctx.shadowBlur = 0;

        ctx.restore();
    }

    function drawSecondHand(angle) {
        ctx.save();
        ctx.translate(centerX, centerY);
        ctx.rotate(angle);

        var len = watchRadius * 0.78;
        var tail = watchRadius * 0.18;

        ctx.shadowColor = 'rgba(255, 50, 50, 0.4)';
        ctx.shadowBlur = 6;

        ctx.beginPath();
        ctx.moveTo(0, 3);
        ctx.lineTo(2, 0);
        ctx.lineTo(0, -len);
        ctx.lineTo(-2, 0);
        ctx.closePath();
        ctx.fillStyle = SECOND_HAND_COLOR;
        ctx.fill();

        ctx.beginPath();
        ctx.arc(0, -len * 0.65, 3.5, 0, Math.PI * 2);
        ctx.fillStyle = SECOND_HAND_COLOR;
        ctx.fill();

        ctx.shadowColor = 'transparent';
        ctx.shadowBlur = 0;

        ctx.beginPath();
        ctx.arc(0, 0, watchRadius * 0.04, 0, Math.PI * 2);
        ctx.fillStyle = SECOND_HAND_COLOR;
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
        ctx.save();
        ctx.clip();

        var bezelOuter = watchRadius;
        var bezelInner = watchRadius * 0.95;
        for (var i = 0; i < 360; i += 3) {
            var a1 = (i - 90) * Math.PI / 180;
            var a2 = (i + 3 - 90) * Math.PI / 180;
            var brightness = 0.08 + Math.abs(Math.sin(i * 0.05)) * 0.04;

            ctx.beginPath();
            ctx.arc(centerX, centerY, bezelOuter, a1, a2);
            ctx.arc(centerX, centerY, bezelInner, a2, a1, true);
            ctx.closePath();
            ctx.fillStyle = 'rgba(80, 100, 180, ' + brightness + ')';
            ctx.fill();
        }

        ctx.beginPath();
        ctx.arc(centerX, centerY, watchRadius, 0, Math.PI * 2);
        ctx.strokeStyle = 'rgba(120, 150, 220, 0.3)';
        ctx.lineWidth = 2;
        ctx.stroke();

        ctx.beginPath();
        ctx.arc(centerX, centerY, watchRadius - 1, 0, Math.PI * 2);
        ctx.strokeStyle = 'rgba(80, 100, 160, 0.15)';
        ctx.lineWidth = 1;
        ctx.stroke();

        ctx.restore();
    }

    function draw(timestamp) {
        ctx.clearRect(0, 0, width, height);
        drawBezel();
        drawTickMarks();

        var now = new Date();
        var hours = now.getHours();
        var minutes = now.getMinutes();
        var seconds = now.getSeconds();
        var milliseconds = now.getMilliseconds();

        var secondAngle = ((seconds + milliseconds / 1000) / 60) * Math.PI * 2 - Math.PI / 2;
        var minuteAngle = ((minutes + seconds / 60) / 60) * Math.PI * 2 - Math.PI / 2;
        var hourAngle = ((hours % 12 + minutes / 60) / 12) * Math.PI * 2 - Math.PI / 2;

        drawHand(watchRadius * 0.42, hourAngle, watchRadius * 0.035, HOUR_HAND_COLOR, true);
        drawHand(watchRadius * 0.58, minuteAngle, watchRadius * 0.025, MINUTE_HAND_COLOR, true);
        drawSecondHand(secondAngle);
    }

    function updateDigitalTime() {
        var now = new Date();
        var hours = now.getHours();
        var minutes = now.getMinutes();
        var timeStr = String(hours).padStart(2, '0') + ':' + String(minutes).padStart(2, '0');

        var timeEl = document.getElementById('digital-time');
        if (timeEl) {
            timeEl.textContent = timeStr;
        }

        var weekdays = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
        var month = now.getMonth() + 1;
        var day = now.getDate();
        var weekday = weekdays[now.getDay()];
        var dateStr = month + '月' + day + '日 ' + weekday;

        var dateEl = document.getElementById('date-display');
        if (dateEl) {
            dateEl.textContent = dateStr;
        }
    }

    function animate(timestamp) {
        draw(timestamp);
        updateDigitalTime();
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