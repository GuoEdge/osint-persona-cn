var Earth3D = (function () {
    'use strict';

    var canvas, ctx;
    var width, height, centerX, centerY, watchRadius;
    var earthCX, earthCY, earthRadius;
    var dayImage = null, nightImage = null, currentImage = null;

    function createSatelliteDay() {
        var c = document.createElement('canvas');
        c.width = 1024; c.height = 1024;
        var t = c.getContext('2d');

        t.fillStyle = '#071830';
        t.fillRect(0, 0, c.width, c.height);

        var r = c.width * 0.42;
        var cx = c.width * 0.52;
        var cy = c.height * 0.45;

        t.save();
        t.beginPath(); t.arc(cx, cy, r, 0, Math.PI * 2); t.clip();

        var og = t.createRadialGradient(cx, cy, r * 0.3, cx, cy, r);
        og.addColorStop(0, '#0d5494'); og.addColorStop(0.5, '#0b4578'); og.addColorStop(1, '#082d50');
        t.fillStyle = og;
        t.fillRect(cx - r, cy - r, r * 2, r * 2);

        var lands = [
            [0.62,0.35,0.22,0.30,'#3d6b22','#5a9038'],[0.58,0.38,0.18,0.24,'#4a8030','#68a040'],
            [0.48,0.42,0.14,0.20,'#3a6520','#558a32'],[0.55,0.28,0.20,0.18,'#3d6822','#5c9436'],
            [0.40,0.32,0.12,0.14,'#356020','#508030'],[0.38,0.36,0.10,0.12,'#3a6522','#558a35'],
            [0.42,0.50,0.08,0.10,'#2e5c1c','#4a7a28'],[0.35,0.48,0.06,0.08,'#305e1e','#4c7c2a'],
            [0.52,0.22,0.12,0.10,'#3b6622','#589034'],[0.68,0.50,0.08,0.10,'#346020','#508a30'],
            [0.70,0.55,0.06,0.08,'#2e5a1c','#4a7e28'],[0.75,0.52,0.04,0.05,'#2c581a','#467a26']
        ];

        for (var i = 0; i < lands.length; i++) {
            var L = lands[i];
            var bx = L[0] * c.width, by = L[1] * c.height, brx = L[2] * c.width, bry = L[3] * c.height;
            t.save(); t.translate(bx, by);
            var g = t.createRadialGradient(0, 0, 0, 0, 0, brx);
            g.addColorStop(0, L[5]); g.addColorStop(0.5, L[4]); g.addColorStop(1, 'rgba(30,50,15,0)');
            t.fillStyle = g;
            t.beginPath(); t.ellipse(0, 0, brx, bry, (Math.random() - 0.5) * 0.2, 0, Math.PI * 2); t.fill();
            for (var k = 0; k < 8; k++) {
                t.beginPath();
                t.arc((Math.random() - 0.5) * brx, (Math.random() - 0.5) * bry,
                    Math.random() * brx * 0.3 + brx * 0.06, 0, Math.PI * 2);
                t.fillStyle = 'rgba(80,130,50,0.3)'; t.fill();
            }
            t.restore();
        }

        for (var j = 0; j < 500; j++) {
            t.beginPath();
            t.arc(cx + (Math.random() - 0.5) * r * 2, cy + (Math.random() - 0.5) * r * 2,
                Math.random() * 30 + 8, 0, Math.PI * 2);
            t.fillStyle = 'rgba(255,255,255,' + (Math.random() * 0.08) + ')'; t.fill();
        }

        t.restore();
        t.beginPath(); t.arc(cx, cy, r + 2, 0, Math.PI * 2);
        t.strokeStyle = 'rgba(140,200,255,0.15)'; t.lineWidth = 2; t.stroke();
        return c;
    }

    function createSatelliteNight() {
        var c = document.createElement('canvas');
        c.width = 1024; c.height = 1024;
        var t = c.getContext('2d');
        t.fillStyle = '#020812'; t.fillRect(0, 0, c.width, c.height);

        var r = c.width * 0.42;
        var cx = c.width * 0.52;
        var cy = c.height * 0.45;

        t.save();
        t.beginPath(); t.arc(cx, cy, r, 0, Math.PI * 2); t.clip();
        var bg = t.createRadialGradient(cx, cy, r * 0.3, cx, cy, r);
        bg.addColorStop(0, '#061225'); bg.addColorStop(1, '#020a18');
        t.fillStyle = bg; t.fillRect(cx - r, cy - r, r * 2, r * 2);

        var cities = [
            [0.62,0.32,65,0.95],[0.64,0.34,55,0.9],[0.60,0.31,50,0.88],[0.63,0.35,60,0.92],
            [0.58,0.38,48,0.85],[0.56,0.36,42,0.82],[0.66,0.40,45,0.85],[0.68,0.38,40,0.8],
            [0.54,0.44,38,0.75],[0.52,0.42,35,0.72],[0.48,0.35,32,0.7],[0.46,0.34,30,0.68],
            [0.50,0.30,28,0.65],[0.42,0.46,35,0.72],[0.40,0.48,30,0.68],[0.38,0.50,28,0.65],
            [0.70,0.45,30,0.7],[0.72,0.48,25,0.65],[0.44,0.40,25,0.6],[0.55,0.28,22,0.58]
        ];

        for (var i = 0; i < cities.length; i++) {
            var C = cities[i];
            var ctx2 = C[0] * c.width, cty = C[1] * c.height, s = C[2], iv = C[3];
            var g = t.createRadialGradient(ctx2, cty, 0, ctx2, cty, s * 3.5);
            g.addColorStop(0, 'rgba(255,210,110,' + (iv * 0.55) + ')');
            g.addColorStop(0.2, 'rgba(255,185,70,' + (iv * 0.35) + ')');
            g.addColorStop(0.45, 'rgba(210,150,40,' + (iv * 0.15) + ')');
            g.addColorStop(1, 'transparent');
            t.fillStyle = g; t.fillRect(ctx2 - s * 3.5, cty - s * 3.5, s * 7, s * 7);
        }

        for (var j = 0; j < 1500; j++) {
            t.beginPath();
            t.arc(cx + (Math.random() - 0.5) * r * 2, cy + (Math.random() - 0.5) * r * 2,
                Math.random() * 2.5 + 0.4, 0, Math.PI * 2);
            t.fillStyle = 'rgba(255,175,55,' + (Math.random() * 0.25 + 0.03) + ')'; t.fill();
        }

        t.restore();
        t.beginPath(); t.arc(cx, cy, r + 2, 0, Math.PI * 2);
        t.strokeStyle = 'rgba(140,200,255,0.12)'; t.lineWidth = 2; t.stroke();
        return c;
    }

    function selectImage() {
        var bh = new Date().getUTCHours() + 8;
        currentImage = (bh >= 6 && bh < 19) ? dayImage : nightImage;
    }

    function init() {
        canvas = document.getElementById('earth-canvas');
        ctx = canvas.getContext('2d');
        dayImage = createSatelliteDay();
        nightImage = createSatelliteNight();
        resize();
    }

    function resize() {
        width = window.innerWidth; height = window.innerHeight;
        var dpr = window.devicePixelRatio || 1;
        canvas.width = width * dpr; canvas.height = height * dpr;
        canvas.style.width = width + 'px'; canvas.style.height = height + 'px';
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        centerX = width / 2; centerY = height / 2;
        watchRadius = Math.min(width, height) / 2;
        earthRadius = watchRadius * 0.34;
        earthCX = centerX;
        earthCY = centerY + watchRadius * 0.16;
    }

    function draw() {
        selectImage();
        var img = currentImage;
        if (!img) return;

        ctx.clearRect(0, 0, width, height);

        var srcR = img.width * 0.42;
        var srcCX = img.width * 0.52;
        var srcCY = img.height * 0.45;

        ctx.save();
        ctx.beginPath();
        ctx.arc(earthCX, earthCY, earthRadius, 0, Math.PI * 2);
        ctx.clip();
        ctx.drawImage(img,
            srcCX - srcR, srcCY - srcR, srcR * 2, srcR * 2,
            earthCX - earthRadius, earthCY - earthRadius, earthRadius * 2, earthRadius * 2);
        ctx.restore();

        ctx.beginPath();
        ctx.arc(earthCX, earthCY, earthRadius + 2, 0, Math.PI * 2);
        ctx.strokeStyle = 'rgba(130,180,240,0.18)';
        ctx.lineWidth = 2;
        ctx.stroke();
    }

    return { init: init, draw: draw, resize: resize };
})();