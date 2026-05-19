var Earth3D = (function () {
    'use strict';

    var canvas, ctx;
    var width, height, centerX, centerY, watchRadius;
    var earthCX, earthCY, earthRadius;
    var dayTexture = null;
    var realTexCanvas = null;
    var realTexLoaded = false;

    var TEXTURE_URLS = [
        'https://eoimages.gsfc.nasa.gov/images/imagerecords/57000/57730/land_ocean_ice_cloud_2048.jpg',
        'https://upload.wikimedia.org/wikipedia/commons/thumb/2/23/Blue_Marble_2002.png/1024px-Blue_Marble_2002.png',
        'https://eoimages.gsfc.nasa.gov/images/imagerecords/57000/57723/land_ocean_ice_8192.jpg'
    ];

    function loadRealTexture(urlIndex, callback) {
        if (urlIndex >= TEXTURE_URLS.length) {
            callback(null);
            return;
        }
        var img = new Image();
        img.crossOrigin = 'anonymous';
        var timeout = setTimeout(function () {
            img.src = '';
            loadRealTexture(urlIndex + 1, callback);
        }, 8000);
        img.onload = function () {
            clearTimeout(timeout);
            var tc = document.createElement('canvas');
            var maxDim = 1024;
            var scale = Math.min(maxDim / img.width, maxDim / img.height);
            tc.width = Math.round(img.width * scale);
            tc.height = Math.round(img.height * scale);
            var tctx = tc.getContext('2d');
            tctx.drawImage(img, 0, 0, tc.width, tc.height);
            callback(tc);
        };
        img.onerror = function () {
            clearTimeout(timeout);
            loadRealTexture(urlIndex + 1, callback);
        };
        img.src = TEXTURE_URLS[urlIndex];
    }

    function createDayFromReal(realTex) {
        var c = document.createElement('canvas');
        c.width = 1024; c.height = 1024;
        var t = c.getContext('2d');

        t.fillStyle = '#020a18';
        t.fillRect(0, 0, c.width, c.height);

        var r = c.width * 0.48;
        var cx = c.width * 0.5;
        var cy = c.height * 0.49;

        t.save();
        t.beginPath();
        t.arc(cx, cy, r, 0, Math.PI * 2);
        t.clip();

        var texW = realTex.width;
        var texH = realTex.height;
        var srcCX = texW * 0.755;
        var srcCY = texH * 0.36;
        var srcR = Math.min(texW * 0.14, texH * 0.28);

        t.drawImage(realTex,
            srcCX - srcR, srcCY - srcR, srcR * 2, srcR * 2,
            cx - r, cy - r, r * 2, r * 2);

        t.restore();

        t.beginPath();
        t.arc(cx, cy, r + 2, 0, Math.PI * 2);
        t.strokeStyle = 'rgba(140,210,255,0.22)';
        t.lineWidth = 2;
        t.stroke();

        return c;
    }

    function createProceduralEarth() {
        var c = document.createElement('canvas');
        var S = 1024;
        c.width = S; c.height = S;
        var t = c.getContext('2d');

        t.fillStyle = '#020a18';
        t.fillRect(0, 0, S, S);

        var r = S * 0.48;
        var cx = S * 0.5;
        var cy = S * 0.49;

        t.save();
        t.beginPath();
        t.arc(cx, cy, r, 0, Math.PI * 2);
        t.clip();

        var ocean = t.createRadialGradient(410, 360, r * 0.08, cx, cy, r);
        ocean.addColorStop(0, '#3399dd');
        ocean.addColorStop(0.15, '#2288cc');
        ocean.addColorStop(0.4, '#1868a8');
        ocean.addColorStop(0.7, '#105090');
        ocean.addColorStop(1, '#083060');
        t.fillStyle = ocean;
        t.fillRect(cx - r, cy - r, r * 2, r * 2);

        function blob(mx, my, rx, ry, rot, color1, color2, detailCount) {
            t.save();
            t.translate(mx, my);
            t.rotate(rot || 0);

            var grad = t.createRadialGradient(0, 0, Math.max(rx, ry) * 0.05, 0, 0, Math.max(rx, ry));
            grad.addColorStop(0, color1);
            grad.addColorStop(0.45, color1);
            grad.addColorStop(1, color2);
            t.fillStyle = grad;

            t.beginPath();
            t.ellipse(0, 0, rx, ry, 0, 0, Math.PI * 2);
            t.fill();

            var dc = detailCount || 10;
            for (var k = 0; k < dc; k++) {
                var kx = (Math.random() - 0.5) * rx * 1.6;
                var ky = (Math.random() - 0.5) * ry * 1.6;
                t.beginPath();
                t.arc(kx, ky, Math.random() * rx * 0.2 + rx * 0.05, 0, Math.PI * 2);
                var kg = t.createRadialGradient(kx, ky, 0, kx, ky, rx * 0.22);
                kg.addColorStop(0, 'rgba(95,160,58,0.55)');
                kg.addColorStop(1, 'rgba(55,105,25,0)');
                t.fillStyle = kg;
                t.fill();
            }

            t.restore();
        }

        blob(480, 300, 120, 80, -0.12, '#4a8c2c', '#2e6018', 15);
        blob(450, 340, 100, 70, 0.08, '#4a8228', '#2e5c16', 12);
        blob(510, 370, 90, 75, 0.06, '#427a24', '#2a5818', 12);
        blob(540, 430, 75, 65, -0.05, '#3c7220', '#265414', 10);
        blob(560, 470, 45, 55, 0.18, '#346c1c', '#224e10', 8);
        blob(440, 255, 70, 45, -0.05, '#4a8828', '#30681a', 10);
        blob(500, 240, 65, 40, 0.06, '#468228', '#2e6418', 10);
        blob(540, 240, 55, 38, 0.04, '#447e26', '#2c6018', 10);
        blob(580, 230, 60, 40, -0.08, '#488428', '#30641a', 10);
        blob(620, 215, 75, 40, -0.06, '#4a862a', '#32661c', 10);
        blob(590, 280, 55, 38, 0.05, '#427a24', '#2a5c16', 8);
        blob(640, 250, 30, 40, 0.12, '#3c7220', '#265412', 6);
        blob(670, 320, 25, 35, 0.22, '#366c1c', '#224e10', 5);
        blob(690, 350, 20, 25, -0.08, '#326818', '#1e480c', 4);
        blob(710, 340, 18, 45, 0.15, '#346a1a', '#204c0e', 5);
        blob(640, 380, 28, 25, 0.25, '#366c1c', '#224e10', 5);
        blob(680, 420, 18, 20, 0.1, '#306416', '#1c460a', 4);
        blob(400, 320, 60, 70, 0.05, '#427824', '#2a5c16', 10);
        blob(370, 350, 45, 48, 0.1, '#3e7420', '#285414', 8);
        blob(340, 380, 38, 42, 0.08, '#3a6e1c', '#244e10', 8);
        blob(360, 430, 30, 38, -0.05, '#366a18', '#22480e', 6);
        blob(390, 470, 32, 28, 0.12, '#326616', '#1e440c', 6);
        blob(420, 490, 28, 30, 0.05, '#306416', '#1c420a', 6);
        blob(460, 480, 40, 35, 0.08, '#326818', '#1e460c', 8);
        blob(500, 460, 48, 40, -0.04, '#346a1a', '#204c0e', 8);
        blob(530, 490, 35, 30, 0.15, '#306416', '#1c420a', 6);
        blob(560, 510, 28, 25, -0.05, '#2e6014', '#1a4008', 5);
        blob(590, 530, 22, 22, 0.08, '#2c5e14', '#183e08', 4);
        blob(450, 225, 55, 35, 0.04, '#468228', '#2e6418', 8);
        blob(520, 215, 50, 32, -0.06, '#447e26', '#2c6018', 8);
        blob(360, 260, 48, 38, 0.1, '#427824', '#2a5c16', 8);
        blob(330, 280, 40, 32, 0.05, '#3e7420', '#285414', 6);
        blob(380, 240, 42, 32, -0.05, '#447e26', '#2c6018', 7);
        blob(270, 350, 38, 48, 0.08, '#3a6e1c', '#244e10', 7);
        blob(250, 380, 32, 42, 0.05, '#366a18', '#22480e', 6);
        blob(290, 430, 34, 45, -0.08, '#366a18', '#22480e', 6);
        blob(230, 370, 24, 36, 0.1, '#326616', '#1e440c', 5);
        blob(670, 380, 18, 22, 0.15, '#306416', '#1c420a', 4);
        blob(340, 490, 22, 22, 0.12, '#2e6014', '#1a4008', 4);
        blob(370, 510, 18, 22, 0.08, '#2c5e14', '#183e08', 3);
        blob(310, 520, 20, 24, 0.1, '#2c5e14', '#183e08', 3);

        for (var j = 0; j < 400; j++) {
            var wx = cx + (Math.random() - 0.5) * r * 2;
            var wy = cy + (Math.random() - 0.5) * r * 2;
            t.beginPath();
            t.arc(wx, wy, Math.random() * 25 + 4, 0, Math.PI * 2);
            t.fillStyle = 'rgba(255,255,255,' + (Math.random() * 0.06) + ')';
            t.fill();
        }

        t.restore();

        t.beginPath();
        t.arc(cx, cy, r + 2, 0, Math.PI * 2);
        t.strokeStyle = 'rgba(140,210,255,0.22)';
        t.lineWidth = 2;
        t.stroke();

        return c;
    }

    function drawTerminator(img, beijingHour) {
        var srcR = img.width * 0.48;
        var srcCX = img.width * 0.5;
        var srcCY = img.height * 0.49;

        ctx.save();
        ctx.beginPath();
        ctx.arc(earthCX, earthCY, earthRadius, 0, Math.PI * 2);
        ctx.clip();

        ctx.drawImage(img,
            srcCX - srcR, srcCY - srcR, srcR * 2, srcR * 2,
            earthCX - earthRadius, earthCY - earthRadius, earthRadius * 2, earthRadius * 2);

        var nightAlpha = 0;
        var terminatorX = 0;

        if (beijingHour >= 6 && beijingHour < 19) {
            var daytime = beijingHour - 6;
            var maxDay = 13;
            var sunAngle = (daytime / maxDay) * Math.PI;
            var termOffset = Math.cos(sunAngle) * earthRadius;
            terminatorX = earthCX + termOffset;
            var fadeWidth = earthRadius * 0.6;
            var nightGrad = ctx.createLinearGradient(
                terminatorX + fadeWidth, 0,
                terminatorX - fadeWidth, 0
            );
            nightGrad.addColorStop(0, 'rgba(2,8,30,0.75)');
            nightGrad.addColorStop(0.35, 'rgba(2,8,30,0.45)');
            nightGrad.addColorStop(0.6, 'rgba(2,8,30,0.08)');
            nightGrad.addColorStop(1, 'rgba(2,8,30,0)');
            ctx.fillStyle = nightGrad;
            ctx.fillRect(earthCX - earthRadius, earthCY - earthRadius,
                earthRadius * 2, earthRadius * 2);
        } else {
            nightAlpha = 0.55 + Math.min(0.2, Math.abs(beijingHour - 1) * 0.04);
            if (beijingHour >= 19) {
                var nightProgress = (beijingHour - 19) / 5;
                nightAlpha = 0.55 + Math.min(0.35, nightProgress * 0.35);
                terminatorX = earthCX - earthRadius * (1 - nightProgress * 1.5);
            } else {
                var beforeDawn = (6 - beijingHour) / 6;
                nightAlpha = 0.55 + Math.min(0.35, beforeDawn * 0.35);
                terminatorX = earthCX + earthRadius * (1 - beforeDawn * 1.5);
            }
            terminatorX = Math.max(earthCX - earthRadius, Math.min(earthCX + earthRadius, terminatorX));
            var fadeWidth = earthRadius * 0.6;
            var nightGrad = ctx.createLinearGradient(
                terminatorX + fadeWidth, 0,
                terminatorX - fadeWidth, 0
            );
            nightGrad.addColorStop(0, 'rgba(2,6,26,' + nightAlpha + ')');
            nightGrad.addColorStop(0.3, 'rgba(2,6,26,' + (nightAlpha * 0.6) + ')');
            nightGrad.addColorStop(0.6, 'rgba(2,6,26,' + (nightAlpha * 0.15) + ')');
            nightGrad.addColorStop(1, 'rgba(2,6,26,0)');
            ctx.fillStyle = nightGrad;
            ctx.fillRect(earthCX - earthRadius, earthCY - earthRadius,
                earthRadius * 2, earthRadius * 2);

            if (nightAlpha > 0.6) {
                var cityLights = [
                    [0.58,0.24,32],[0.60,0.26,28],[0.56,0.28,26],
                    [0.54,0.30,24],[0.52,0.32,22],[0.50,0.34,20],
                    [0.52,0.38,22],[0.54,0.40,20],[0.50,0.42,18],
                    [0.46,0.40,16],[0.48,0.36,20],[0.70,0.24,22],
                    [0.74,0.26,18],[0.68,0.30,20],[0.66,0.32,16],
                    [0.64,0.34,15],[0.68,0.36,14],[0.70,0.32,15],
                    [0.64,0.38,13],[0.66,0.40,12],[0.62,0.42,11],
                    [0.54,0.46,12],[0.50,0.48,10],[0.42,0.46,12],
                    [0.40,0.42,10],[0.38,0.44,11],
                ];
                var lightAlpha = (nightAlpha - 0.6) / 0.3;
                for (var i = 0; i < cityLights.length; i++) {
                    var cl = cityLights[i];
                    var lx = earthCX + (cl[0] - 0.5) * earthRadius * 2;
                    var ly = earthCY + (cl[1] - 0.49) * earthRadius * 2;
                    var lr = cl[2] * (earthRadius / 480);
                    var lg = ctx.createRadialGradient(lx, ly, 0, lx, ly, lr * 3);
                    lg.addColorStop(0, 'rgba(255,215,100,' + (0.7 * lightAlpha) + ')');
                    lg.addColorStop(0.2, 'rgba(255,185,60,' + (0.35 * lightAlpha) + ')');
                    lg.addColorStop(0.5, 'rgba(220,150,40,' + (0.08 * lightAlpha) + ')');
                    lg.addColorStop(1, 'transparent');
                    ctx.fillStyle = lg;
                    ctx.fillRect(lx - lr * 3, ly - lr * 3, lr * 6, lr * 6);
                }
            }
        }

        ctx.restore();
    }

    function drawAtmosphere() {
        var glow = ctx.createRadialGradient(earthCX, earthCY, earthRadius * 0.88,
            earthCX, earthCY, earthRadius * 1.06);
        glow.addColorStop(0, 'transparent');
        glow.addColorStop(0.5, 'rgba(100,180,255,0.10)');
        glow.addColorStop(1, 'transparent');
        ctx.beginPath();
        ctx.arc(earthCX, earthCY, earthRadius * 1.06, 0, Math.PI * 2);
        ctx.fillStyle = glow;
        ctx.fill();
    }

    function init() {
        canvas = document.getElementById('earth-canvas');
        ctx = canvas.getContext('2d');

        dayTexture = createProceduralEarth();

        loadRealTexture(0, function (realTex) {
            if (realTex) {
                dayTexture = createDayFromReal(realTex);
                realTexLoaded = true;
            }
        });

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

        earthRadius = watchRadius * 0.42;
        earthCX = centerX;
        earthCY = centerY + watchRadius * 0.10;
    }

    function draw() {
        var bh = new Date().getUTCHours() + 8;
        if (bh >= 24) bh -= 24;
        if (bh < 0) bh += 24;

        ctx.clearRect(0, 0, width, height);
        drawAtmosphere();

        if (dayTexture) {
            drawTerminator(dayTexture, bh);
        }

        ctx.beginPath();
        ctx.arc(earthCX, earthCY, earthRadius + 1.5, 0, Math.PI * 2);
        ctx.strokeStyle = 'rgba(130,195,255,0.25)';
        ctx.lineWidth = 2;
        ctx.stroke();
    }

    return { init: init, draw: draw, resize: resize };
})();