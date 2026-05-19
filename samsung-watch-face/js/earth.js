var Earth3D = (function () {
    'use strict';

    var canvas, ctx;
    var width, height, centerX, centerY, watchRadius;
    var earthCX, earthCY, earthRadius;
    var dayImage = null, nightImage = null;
    var currentImage = null;
    var animFrame;

    var ASIA_LON = 110;
    var ASIA_LAT = 30;

    function createSatelliteDayImage() {
        var c = document.createElement('canvas');
        c.width = 1024;
        c.height = 1024;
        var t = c.getContext('2d');

        t.fillStyle = '#071830';
        t.fillRect(0, 0, c.width, c.height);

        var r = c.width * 0.42;
        var cx = c.width * 0.52;
        var cy = c.height * 0.45;
        t.save();
        t.beginPath();
        t.arc(cx, cy, r, 0, Math.PI * 2);
        t.clip();

        var oceanGrad = t.createRadialGradient(cx, cy, r * 0.3, cx, cy, r);
        oceanGrad.addColorStop(0, '#0d5494');
        oceanGrad.addColorStop(0.5, '#0b4578');
        oceanGrad.addColorStop(1, '#082d50');
        t.fillStyle = oceanGrad;
        t.fillRect(cx - r, cy - r, r * 2, r * 2);

        var landBlobs = [
            { x: 0.62, y: 0.35, rx: 0.22, ry: 0.30, c1: '#3d6b22', c2: '#5a9038' },
            { x: 0.58, y: 0.38, rx: 0.18, ry: 0.24, c1: '#4a8030', c2: '#68a040' },
            { x: 0.48, y: 0.42, rx: 0.14, ry: 0.20, c1: '#3a6520', c2: '#558a32' },
            { x: 0.55, y: 0.28, rx: 0.20, ry: 0.18, c1: '#3d6822', c2: '#5c9436' },
            { x: 0.40, y: 0.32, rx: 0.12, ry: 0.14, c1: '#356020', c2: '#508030' },
            { x: 0.38, y: 0.36, rx: 0.10, ry: 0.12, c1: '#3a6522', c2: '#558a35' },
            { x: 0.42, y: 0.50, rx: 0.08, ry: 0.10, c1: '#2e5c1c', c2: '#4a7a28' },
            { x: 0.35, y: 0.48, rx: 0.06, ry: 0.08, c1: '#305e1e', c2: '#4c7c2a' },
            { x: 0.52, y: 0.22, rx: 0.12, ry: 0.10, c1: '#3b6622', c2: '#589034' },
            { x: 0.68, y: 0.50, rx: 0.08, ry: 0.10, c1: '#346020', c2: '#508a30' },
            { x: 0.70, y: 0.55, rx: 0.06, ry: 0.08, c1: '#2e5a1c', c2: '#4a7e28' },
            { x: 0.75, y: 0.52, rx: 0.04, ry: 0.05, c1: '#2c581a', c2: '#467a26' },
        ];

        for (var i = 0; i < landBlobs.length; i++) {
            var b = landBlobs[i];
            var bx = b.x * c.width;
            var by = b.y * c.height;
            var brx = b.rx * c.width;
            var bry = b.ry * c.height;
            t.save();
            t.translate(bx, by);
            var grad = t.createRadialGradient(0, 0, 0, 0, 0, brx);
            grad.addColorStop(0, b.c2);
            grad.addColorStop(0.5, b.c1);
            grad.addColorStop(1, 'rgba(30,50,15,0)');
            t.fillStyle = grad;
            t.beginPath();
            t.ellipse(0, 0, brx, bry, (Math.random() - 0.5) * 0.2, 0, Math.PI * 2);
            t.fill();

            for (var k = 0; k < 8; k++) {
                var dx = (Math.random() - 0.5) * brx;
                var dy = (Math.random() - 0.5) * bry;
                var dr = Math.random() * brx * 0.3 + brx * 0.06;
                t.beginPath();
                t.arc(dx, dy, dr, 0, Math.PI * 2);
                t.fillStyle = 'rgba(80,130,50,0.3)';
                t.fill();
            }
            t.restore();
        }

        for (var j = 0; j < 500; j++) {
            var wx = (Math.random() - 0.5) * r * 2 + cx;
            var wy = (Math.random() - 0.5) * r * 2 + cy;
            var wr = Math.random() * 30 + 8;
            t.beginPath();
            t.arc(wx, wy, wr, 0, Math.PI * 2);
            t.fillStyle = 'rgba(255,255,255,' + (Math.random() * 0.08) + ')';
            t.fill();
        }

        t.restore();

        t.beginPath();
        t.arc(cx, cy, r + 2, 0, Math.PI * 2);
        t.strokeStyle = 'rgba(140,200,255,0.15)';
        t.lineWidth = 2;
        t.stroke();

        return c;
    }

    function createSatelliteNightImage() {
        var c = document.createElement('canvas');
        c.width = 1024;
        c.height = 1024;
        var t = c.getContext('2d');

        t.fillStyle = '#020812';
        t.fillRect(0, 0, c.width, c.height);

        var r = c.width * 0.42;
        var cx = c.width * 0.52;
        var cy = c.height * 0.45;
        t.save();
        t.beginPath();
        t.arc(cx, cy, r, 0, Math.PI * 2);
        t.clip();

        var baseGrad = t.createRadialGradient(cx, cy, r * 0.3, cx, cy, r);
        baseGrad.addColorStop(0, '#061225');
        baseGrad.addColorStop(1, '#020a18');
        t.fillStyle = baseGrad;
        t.fillRect(cx - r, cy - r, r * 2, r * 2);

        var cities = [
            { x: 0.62, y: 0.32, s: 65, i: 0.95 },
            { x: 0.64, y: 0.34, s: 55, i: 0.9 },
            { x: 0.60, y: 0.31, s: 50, i: 0.88 },
            { x: 0.63, y: 0.35, s: 60, i: 0.92 },
            { x: 0.58, y: 0.38, s: 48, i: 0.85 },
            { x: 0.56, y: 0.36, s: 42, i: 0.82 },
            { x: 0.66, y: 0.40, s: 45, i: 0.85 },
            { x: 0.68, y: 0.38, s: 40, i: 0.8 },
            { x: 0.54, y: 0.44, s: 38, i: 0.75 },
            { x: 0.52, y: 0.42, s: 35, i: 0.72 },
            { x: 0.48, y: 0.35, s: 32, i: 0.7 },
            { x: 0.46, y: 0.34, s: 30, i: 0.68 },
            { x: 0.50, y: 0.30, s: 28, i: 0.65 },
            { x: 0.42, y: 0.46, s: 35, i: 0.72 },
            { x: 0.40, y: 0.48, s: 30, i: 0.68 },
            { x: 0.38, y: 0.50, s: 28, i: 0.65 },
            { x: 0.70, y: 0.45, s: 30, i: 0.7 },
            { x: 0.72, y: 0.48, s: 25, i: 0.65 },
            { x: 0.44, y: 0.40, s: 25, i: 0.6 },
            { x: 0.55, y: 0.28, s: 22, i: 0.58 },
        ];

        for (var i = 0; i < cities.length; i++) {
            var ct = cities[i];
            var ctx2 = ct.x * c.width;
            var cty = ct.y * c.height;
            var g = t.createRadialGradient(ctx2, cty, 0, ctx2, cty, ct.s * 3.5);
            g.addColorStop(0, 'rgba(255,210,110,' + (ct.i * 0.55) + ')');
            g.addColorStop(0.2, 'rgba(255,185,70,' + (ct.i * 0.35) + ')');
            g.addColorStop(0.45, 'rgba(210,150,40,' + (ct.i * 0.15) + ')');
            g.addColorStop(1, 'transparent');
            t.fillStyle = g;
            t.fillRect(ctx2 - ct.s * 3.5, cty - ct.s * 3.5, ct.s * 7, ct.s * 7);
        }

        for (var j = 0; j < 1500; j++) {
            var sx = cx + (Math.random() - 0.5) * r * 2;
            var sy = cy + (Math.random() - 0.5) * r * 2;
            var sr = Math.random() * 2.5 + 0.4;
            t.beginPath();
            t.arc(sx, sy, sr, 0, Math.PI * 2);
            t.fillStyle = 'rgba(255,175,55,' + (Math.random() * 0.25 + 0.03) + ')';
            t.fill();
        }

        t.restore();

        t.beginPath();
        t.arc(cx, cy, r + 2, 0, Math.PI * 2);
        t.strokeStyle = 'rgba(140,200,255,0.12)';
        t.lineWidth = 2;
        t.stroke();

        return c;
    }

    function selectImage() {
        var now = new Date();
        var beijingHour = now.getUTCHours() + 8;
        var isDaytime = beijingHour >= 6 && beijingHour < 19;
        currentImage = isDaytime ? dayImage : nightImage;
    }

    function init() {
        canvas = document.getElementById('earth-canvas');
        ctx = canvas.getContext('2d');
        dayImage = createSatelliteDayImage();
        nightImage = createSatelliteNightImage();
        resize();
        selectImage();
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
        earthRadius = watchRadius * 0.28;
        earthCX = centerX;
        earthCY = centerY + watchRadius * 0.22;
    }

    var fadeProgress = 0;
    var fadeTarget = 0;
    var prevImage = null;

    function draw() {
        ctx.clearRect(0, 0, width, height);
        selectImage();
        var img = currentImage;
        if (!img) return;

        if (img !== prevImage) {
            fadeTarget = 1;
            prevImage = img;
        }
        fadeProgress += (fadeTarget - fadeProgress) * 0.05;

        ctx.save();
        ctx.beginPath();
        ctx.arc(earthCX, earthCY, earthRadius, 0, Math.PI * 2);
        ctx.clip();

        ctx.globalAlpha = 1;
        var srcW = img.width;
        var srcH = img.height;
        var srcR = srcW * 0.42;
        var srcCX = srcW * 0.52;
        var srcCY = srcH * 0.45;
        ctx.drawImage(img,
            srcCX - srcR, srcCY - srcR, srcR * 2, srcR * 2,
            earthCX - earthRadius, earthCY - earthRadius, earthRadius * 2, earthRadius * 2);

        ctx.globalAlpha = 1;

        ctx.restore();

        ctx.beginPath();
        ctx.arc(earthCX, earthCY, earthRadius + 2, 0, Math.PI * 2);
        ctx.strokeStyle = 'rgba(130,180,240,0.18)';
        ctx.lineWidth = 2;
        ctx.stroke();

        var glowGrad = ctx.createRadialGradient(earthCX, earthCY, earthRadius * 0.85, earthCX, earthCY, earthRadius + 8);
        glowGrad.addColorStop(0, 'transparent');
        glowGrad.addColorStop(1, 'rgba(60,120,220,0.08)');
        ctx.beginPath();
        ctx.arc(earthCX, earthCY, earthRadius + 5, 0, Math.PI * 2);
        ctx.strokeStyle = glowGrad;
        ctx.lineWidth = 4;
        ctx.stroke();
    }

    return {
        init: init,
        draw: draw,
        resize: resize
    };
})();