var Earth3D = (function () {
    'use strict';

    var canvas, ctx;
    var width, height, centerX, centerY, watchRadius;
    var earthCX, earthCY, earthRadius;
    var animationId;

    var dayTex = null, nightTex = null;
    var EAST_ASIA_LON = 120;
    var rotationOffset = 0;
    var targetRotation = 0;

    function createDayTexture() {
        var texCanvas = document.createElement('canvas');
        texCanvas.width = 2048;
        texCanvas.height = 512;
        var tctx = texCanvas.getContext('2d');

        var oceanGrad = tctx.createLinearGradient(0, 0, 0, texCanvas.height);
        oceanGrad.addColorStop(0, '#0b4678');
        oceanGrad.addColorStop(0.25, '#1166aa');
        oceanGrad.addColorStop(0.5, '#1a80cc');
        oceanGrad.addColorStop(0.75, '#1166aa');
        oceanGrad.addColorStop(1, '#0b4678');
        tctx.fillStyle = oceanGrad;
        tctx.fillRect(0, 0, texCanvas.width, texCanvas.height);

        for (var i = 0; i < 3000; i++) {
            var ox = Math.random() * texCanvas.width;
            var oy = Math.random() * texCanvas.height;
            tctx.fillStyle = 'rgba(20, 100, 180, ' + (Math.random() * 0.08) + ')';
            tctx.fillRect(ox, oy, Math.random() * 8 + 2, Math.random() * 4 + 1);
        }

        var continents = [
            { cx: 0.72, cy: 0.30, rx: 0.18, ry: 0.25 },
            { cx: 0.73, cy: 0.28, rx: 0.15, ry: 0.22 },
            { cx: 0.68, cy: 0.40, rx: 0.12, ry: 0.18 },
            { cx: 0.76, cy: 0.55, rx: 0.10, ry: 0.10 },
            { cx: 0.70, cy: 0.20, rx: 0.14, ry: 0.14 },
            { cx: 0.60, cy: 0.35, rx: 0.07, ry: 0.12 },
            { cx: 0.30, cy: 0.28, rx: 0.12, ry: 0.18 },
            { cx: 0.31, cy: 0.30, rx: 0.10, ry: 0.16 },
            { cx: 0.18, cy: 0.38, rx: 0.14, ry: 0.22 },
            { cx: 0.20, cy: 0.36, rx: 0.12, ry: 0.20 },
            { cx: 0.85, cy: 0.30, rx: 0.08, ry: 0.12 },
            { cx: 0.22, cy: 0.18, rx: 0.10, ry: 0.12 },
            { cx: 0.50, cy: 0.38, rx: 0.05, ry: 0.07 },
            { cx: 0.35, cy: 0.50, rx: 0.05, ry: 0.06 },
            { cx: 0.90, cy: 0.50, rx: 0.04, ry: 0.05 },
            { cx: 0.79, cy: 0.44, rx: 0.05, ry: 0.06 },
            { cx: 0.81, cy: 0.15, rx: 0.06, ry: 0.08 },
            { cx: 0.48, cy: 0.55, rx: 0.04, ry: 0.05 },
            { cx: 0.16, cy: 0.28, rx: 0.07, ry: 0.10 },
            { cx: 0.24, cy: 0.45, rx: 0.06, ry: 0.08 },
            { cx: 0.82, cy: 0.35, rx: 0.06, ry: 0.10 },
            { cx: 0.65, cy: 0.45, rx: 0.04, ry: 0.06 },
        ];

        for (var j = 0; j < continents.length; j++) {
            var c = continents[j];
            var cx = c.cx * texCanvas.width;
            var cy = c.cy * texCanvas.height;
            var rx = c.rx * texCanvas.width;
            var ry = c.ry * texCanvas.height;

            tctx.save();
            tctx.translate(cx, cy);

            var landGrad = tctx.createRadialGradient(0, 0, 0, 0, 0, rx);
            landGrad.addColorStop(0, '#5a8a3c');
            landGrad.addColorStop(0.3, '#4d7d32');
            landGrad.addColorStop(0.6, '#3d6b25');
            landGrad.addColorStop(0.85, '#2e5a1c');
            landGrad.addColorStop(1, 'rgba(30, 70, 20, 0)');
            tctx.fillStyle = landGrad;

            tctx.beginPath();
            tctx.ellipse(0, 0, rx, ry, (Math.random() - 0.5) * 0.3, 0, Math.PI * 2);
            tctx.fill();

            for (var k = 0; k < 12; k++) {
                var bx = (Math.random() - 0.5) * rx * 1.2;
                var by = (Math.random() - 0.5) * ry * 1.2;
                var br = Math.random() * rx * 0.3 + rx * 0.05;
                tctx.beginPath();
                tctx.arc(bx, by, br, 0, Math.PI * 2);
                tctx.fillStyle = 'rgba(80, 130, 50, 0.35)';
                tctx.fill();
            }

            tctx.restore();
        }

        var cloudCanvas = document.createElement('canvas');
        cloudCanvas.width = 2048;
        cloudCanvas.height = 512;
        var cctx = cloudCanvas.getContext('2d');
        for (var m = 0; m < 800; m++) {
            var clx = Math.random() * cloudCanvas.width;
            var cly = Math.random() * cloudCanvas.height;
            var clr = Math.random() * 30 + 8;
            cctx.beginPath();
            cctx.arc(clx, cly, clr, 0, Math.PI * 2);
            cctx.fillStyle = 'rgba(255, 255, 255, ' + (Math.random() * 0.12) + ')';
            cctx.fill();
        }
        tctx.drawImage(cloudCanvas, 0, 0);

        return texCanvas;
    }

    function createNightTexture() {
        var nCanvas = document.createElement('canvas');
        nCanvas.width = 2048;
        nCanvas.height = 512;
        var nctx = nCanvas.getContext('2d');

        nctx.fillStyle = '#020815';
        nctx.fillRect(0, 0, nCanvas.width, nCanvas.height);

        var cityClusters = [
            { x: 0.74, y: 0.30, r: 60, i: 0.9 },
            { x: 0.75, y: 0.32, r: 50, i: 0.85 },
            { x: 0.73, y: 0.29, r: 40, i: 0.8 },
            { x: 0.76, y: 0.31, r: 55, i: 0.9 },
            { x: 0.82, y: 0.33, r: 70, i: 0.95 },
            { x: 0.83, y: 0.32, r: 55, i: 0.9 },
            { x: 0.81, y: 0.30, r: 60, i: 0.92 },
            { x: 0.80, y: 0.34, r: 45, i: 0.85 },
            { x: 0.68, y: 0.36, r: 40, i: 0.75 },
            { x: 0.67, y: 0.35, r: 35, i: 0.7 },
            { x: 0.58, y: 0.34, r: 35, i: 0.7 },
            { x: 0.57, y: 0.35, r: 30, i: 0.65 },
            { x: 0.30, y: 0.28, r: 45, i: 0.8 },
            { x: 0.31, y: 0.30, r: 40, i: 0.75 },
            { x: 0.29, y: 0.32, r: 35, i: 0.7 },
            { x: 0.32, y: 0.27, r: 35, i: 0.7 },
            { x: 0.28, y: 0.29, r: 35, i: 0.75 },
            { x: 0.33, y: 0.31, r: 25, i: 0.65 },
            { x: 0.50, y: 0.33, r: 25, i: 0.65 },
            { x: 0.51, y: 0.34, r: 20, i: 0.6 },
            { x: 0.85, y: 0.28, r: 50, i: 0.85 },
            { x: 0.86, y: 0.30, r: 35, i: 0.75 },
            { x: 0.87, y: 0.29, r: 30, i: 0.7 },
            { x: 0.20, y: 0.32, r: 30, i: 0.7 },
            { x: 0.18, y: 0.30, r: 25, i: 0.65 },
            { x: 0.23, y: 0.33, r: 20, i: 0.6 },
            { x: 0.40, y: 0.30, r: 30, i: 0.7 },
            { x: 0.41, y: 0.31, r: 25, i: 0.65 },
            { x: 0.34, y: 0.29, r: 20, i: 0.6 },
        ];

        for (var i = 0; i < cityClusters.length; i++) {
            var c = cityClusters[i];
            var cx = c.x * nCanvas.width;
            var cy = c.y * nCanvas.height;

            var glowGrad = nctx.createRadialGradient(cx, cy, 0, cx, cy, c.r * 3);
            glowGrad.addColorStop(0, 'rgba(255, 200, 100, ' + (c.i * 0.5) + ')');
            glowGrad.addColorStop(0.25, 'rgba(255, 180, 60, ' + (c.i * 0.3) + ')');
            glowGrad.addColorStop(0.5, 'rgba(200, 140, 30, ' + (c.i * 0.12) + ')');
            glowGrad.addColorStop(1, 'transparent');
            nctx.fillStyle = glowGrad;
            nctx.fillRect(cx - c.r * 3, cy - c.r * 3, c.r * 6, c.r * 6);
        }

        for (var j = 0; j < 1200; j++) {
            var sx = Math.random() * nCanvas.width;
            var sy = Math.random() * nCanvas.height;
            nctx.beginPath();
            nctx.arc(sx, sy, Math.random() * 2.5 + 0.5, 0, Math.PI * 2);
            nctx.fillStyle = 'rgba(255, 170, 50, ' + (Math.random() * 0.25 + 0.03) + ')';
            nctx.fill();
        }

        return nCanvas;
    }

    function getSunAngle() {
        var now = new Date();
        var beijingHours = now.getUTCHours() + 8;
        var beijingMinutes = now.getMinutes();
        var beijingSeconds = now.getSeconds();
        var totalSeconds = beijingHours * 3600 + beijingMinutes * 60 + beijingSeconds;
        return (totalSeconds / 86400) * 360 - 90;
    }

    function init() {
        canvas = document.getElementById('earth-canvas');
        ctx = canvas.getContext('2d');
        dayTex = createDayTexture();
        nightTex = createNightTexture();
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
        earthRadius = watchRadius * 0.22;
        earthCX = centerX;
        earthCY = centerY + watchRadius * 0.28;
    }

    function draw(timestamp) {
        ctx.clearRect(0, 0, width, height);

        if (!dayTex || !nightTex) return;

        var now = new Date();
        var beijingHours = now.getUTCHours() + 8;
        var beijingMinutes = now.getMinutes();
        var beijingSeconds = now.getSeconds();
        var totalSeconds = beijingHours * 3600 + beijingMinutes * 60 + beijingSeconds;

        var sunAngle = getSunAngle();
        var sunAngleRad = sunAngle * Math.PI / 180;
        var textureScroll = ((sunAngle + 90) / 360) * dayTex.width;

        var slowRotation = timestamp * 0.00001;
        targetRotation = -EAST_ASIA_LON / 360;
        rotationOffset += (targetRotation - rotationOffset) * 0.02;

        var texOffset = (totalSeconds / 86400 + rotationOffset) % 1;

        ctx.save();

        ctx.beginPath();
        ctx.arc(earthCX, earthCY, earthRadius, 0, Math.PI * 2);
        ctx.clip();

        var texWidth = dayTex.width;

        var sx = texOffset * texWidth;
        ctx.drawImage(dayTex, sx, 0, texWidth / 2, dayTex.height,
            earthCX - earthRadius, earthCY - earthRadius, earthRadius * 2, earthRadius * 2);
        ctx.drawImage(dayTex, sx - texWidth, 0, texWidth / 2, dayTex.height,
            earthCX - earthRadius, earthCY - earthRadius, earthRadius * 2, earthRadius * 2);

        var shadeGrad = ctx.createLinearGradient(
            earthCX + Math.cos(sunAngleRad + Math.PI / 2) * earthRadius,
            earthCY + Math.sin(sunAngleRad + Math.PI / 2) * earthRadius,
            earthCX + Math.cos(sunAngleRad - Math.PI / 2) * earthRadius,
            earthCY + Math.sin(sunAngleRad - Math.PI / 2) * earthRadius
        );

        shadeGrad.addColorStop(0, 'rgba(0, 0, 0, 0.75)');
        shadeGrad.addColorStop(0.3, 'rgba(0, 0, 0, 0.65)');
        shadeGrad.addColorStop(0.45, 'rgba(0, 0, 0, 0.3)');
        shadeGrad.addColorStop(0.5, 'rgba(0, 0, 0, 0)');
        shadeGrad.addColorStop(0.55, 'rgba(0, 0, 0, 0)');
        shadeGrad.addColorStop(0.7, 'rgba(0, 0, 0, 0.05)');
        shadeGrad.addColorStop(1, 'rgba(0, 0, 0, 0.1)');

        ctx.fillStyle = shadeGrad;
        ctx.fillRect(earthCX - earthRadius, earthCY - earthRadius, earthRadius * 2, earthRadius * 2);

        var nightAlpha = Math.max(0, 0.7);
        var nightGrad = ctx.createLinearGradient(
            earthCX + Math.cos(sunAngleRad + Math.PI / 2) * earthRadius,
            earthCY + Math.sin(sunAngleRad + Math.PI / 2) * earthRadius,
            earthCX + Math.cos(sunAngleRad - Math.PI / 2) * earthRadius,
            earthCY + Math.sin(sunAngleRad - Math.PI / 2) * earthRadius
        );

        nightGrad.addColorStop(0, 'rgba(0, 0, 0, 0)');
        nightGrad.addColorStop(0.3, 'rgba(0, 0, 0, 0)');
        nightGrad.addColorStop(0.45, 'rgba(0, 0, 0, 0)');
        nightGrad.addColorStop(0.5, 'rgba(0, 0, 0, 0.3)');
        nightGrad.addColorStop(0.55, 'rgba(0, 0, 0, 0.65)');
        nightGrad.addColorStop(0.7, 'rgba(0, 0, 0, 0.72)');
        nightGrad.addColorStop(1, 'rgba(0, 0, 0, 0.78)');

        ctx.globalCompositeOperation = 'source-over';

        ctx.drawImage(nightTex, sx, 0, texWidth / 2, nightTex.height,
            earthCX - earthRadius, earthCY - earthRadius, earthRadius * 2, earthRadius * 2);
        ctx.drawImage(nightTex, sx - texWidth, 0, texWidth / 2, nightTex.height,
            earthCX - earthRadius, earthCY - earthRadius, earthRadius * 2, earthRadius * 2);

        ctx.fillStyle = nightGrad;
        ctx.globalCompositeOperation = 'destination-in';
        ctx.fillRect(earthCX - earthRadius, earthCY - earthRadius, earthRadius * 2, earthRadius * 2);

        ctx.globalCompositeOperation = 'source-over';

        ctx.restore();

        ctx.save();
        ctx.beginPath();
        ctx.arc(earthCX, earthCY, earthRadius, 0, Math.PI * 2);
        ctx.clip();

        var sunAngleRad2 = sunAngle * Math.PI / 180;
        var edgeGrad1 = ctx.createLinearGradient(
            earthCX + Math.cos(sunAngleRad2) * earthRadius * 0.7,
            earthCY + Math.sin(sunAngleRad2) * earthRadius * 0.7,
            earthCX + Math.cos(sunAngleRad2 + Math.PI) * earthRadius * 0.7,
            earthCY + Math.sin(sunAngleRad2 + Math.PI) * earthRadius * 0.7
        );
        edgeGrad1.addColorStop(0, 'rgba(80, 140, 255, 0.12)');
        edgeGrad1.addColorStop(1, 'rgba(0, 0, 0, 0)');
        ctx.fillStyle = edgeGrad1;
        ctx.fillRect(earthCX - earthRadius, earthCY - earthRadius, earthRadius * 2, earthRadius * 2);

        ctx.restore();

        ctx.beginPath();
        ctx.arc(earthCX, earthCY, earthRadius + 1, 0, Math.PI * 2);
        ctx.strokeStyle = 'rgba(100, 150, 220, 0.25)';
        ctx.lineWidth = 1.5;
        ctx.stroke();

        ctx.beginPath();
        ctx.arc(earthCX, earthCY, earthRadius + 3, 0, Math.PI * 2);
        var glowGrad = ctx.createRadialGradient(earthCX, earthCY, earthRadius * 0.85, earthCX, earthCY, earthRadius + 4);
        glowGrad.addColorStop(0, 'transparent');
        glowGrad.addColorStop(1, 'rgba(60, 100, 200, 0.15)');
        ctx.strokeStyle = glowGrad;
        ctx.lineWidth = 3;
        ctx.stroke();
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