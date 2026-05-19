var Earth3D = (function () {
    'use strict';

    var canvas, ctx;
    var width, height, centerX, centerY, watchRadius;
    var earthCX, earthCY, earthRadius;
    var dayImage = null, nightImage = null;
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

    function createNightFromReal(realTex) {
        var c = document.createElement('canvas');
        c.width = 1024; c.height = 1024;
        var t = c.getContext('2d');

        t.fillStyle = '#020812';
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

        t.fillStyle = 'rgba(2,2,40,0.55)';
        t.fillRect(cx - r, cy - r, r * 2, r * 2);

        var cityLights = [
            [0.60,0.25,32,0.95],[0.62,0.27,30,0.9],[0.58,0.28,28,0.88],
            [0.55,0.32,26,0.85],[0.52,0.34,24,0.82],[0.50,0.36,22,0.8],
            [0.54,0.38,24,0.84],[0.56,0.40,22,0.8],[0.53,0.42,20,0.75],
            [0.48,0.40,18,0.7],[0.46,0.38,16,0.65],[0.51,0.44,18,0.72],
            [0.72,0.25,24,0.88],[0.75,0.28,20,0.82],[0.78,0.26,18,0.78],
            [0.70,0.30,20,0.84],[0.66,0.34,18,0.75],[0.68,0.36,16,0.72],
            [0.72,0.32,16,0.76],[0.65,0.40,15,0.7],[0.68,0.42,14,0.68],
            [0.55,0.46,14,0.62],[0.50,0.48,12,0.6],[0.42,0.46,14,0.62],
            [0.38,0.44,13,0.6],[0.35,0.46,12,0.55],
            [0.44,0.26,10,0.45],[0.40,0.28,8,0.4],
            [0.65,0.15,12,0.5],[0.55,0.18,8,0.4],
            [0.68,0.20,10,0.45],[0.62,0.35,14,0.6],
        ];

        for (var i = 0; i < cityLights.length; i++) {
            var cl = cityLights[i];
            var clx = cl[0] * c.width;
            var cly = cl[1] * c.height;
            var grad = t.createRadialGradient(clx, cly, 0, clx, cly, cl[2] * 4.5);
            grad.addColorStop(0, 'rgba(255,220,120,' + (cl[3] * 0.7) + ')');
            grad.addColorStop(0.15, 'rgba(255,200,80,' + (cl[3] * 0.4) + ')');
            grad.addColorStop(0.4, 'rgba(230,160,50,' + (cl[3] * 0.12) + ')');
            grad.addColorStop(1, 'transparent');
            t.fillStyle = grad;
            t.fillRect(clx - cl[2] * 4.5, cly - cl[2] * 4.5, cl[2] * 9, cl[2] * 9);
        }

        for (var j = 0; j < 1000; j++) {
            t.beginPath();
            t.arc(cx + (Math.random() - 0.5) * r * 2, cy + (Math.random() - 0.5) * r * 2,
                Math.random() * 2.8 + 0.4, 0, Math.PI * 2);
            t.fillStyle = 'rgba(255,180,55,' + (Math.random() * 0.22 + 0.03) + ')';
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

    function createProceduralDay() {
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

        var ocean = t.createRadialGradient(cx * 0.8, cy * 0.7, r * 0.1, cx, cy, r);
        ocean.addColorStop(0, '#2288cc');
        ocean.addColorStop(0.3, '#1868a8');
        ocean.addColorStop(0.6, '#105090');
        ocean.addColorStop(1, '#083060');
        t.fillStyle = ocean;
        t.fillRect(cx - r, cy - r, r * 2, r * 2);

        var n = c.width / 1024;

        var landBlobs = [
            [0.480*n,0.280*n,0.22*n,0.16*n,-0.15,'#3a7220','#2d5a16'],
            [0.440*n,0.340*n,0.18*n,0.14*n,0.1,'#4a8228','#386620'],
            [0.510*n,0.360*n,0.16*n,0.14*n,0.05,'#3d7622','#2e5c18'],
            [0.530*n,0.420*n,0.14*n,0.12*n,-0.08,'#38701e','#285416'],
            [0.550*n,0.460*n,0.08*n,0.10*n,0.2,'#32681a','#224c10'],
            [0.570*n,0.340*n,0.10*n,0.08*n,0,'#4a8026','#36661e'],
            [0.590*n,0.300*n,0.14*n,0.10*n,-0.1,'#427a24','#32601a'],
            [0.610*n,0.260*n,0.12*n,0.08*n,0.1,'#4c842a','#3a6a22'],
            [0.630*n,0.240*n,0.08*n,0.07*n,-0.05,'#3e7420','#2c5816'],
            [0.380*n,0.320*n,0.10*n,0.12*n,0,'#3a6e1c','#285010'],
            [0.350*n,0.360*n,0.08*n,0.08*n,0.15,'#346a18','#244c0e'],
            [0.400*n,0.380*n,0.08*n,0.06*n,0.1,'#326818','#22480e'],
            [0.620*n,0.360*n,0.07*n,0.06*n,0,'#3c7020','#2a5414'],
            [0.640*n,0.320*n,0.06*n,0.07*n,-0.1,'#386c1c','#265012'],
            [0.670*n,0.300*n,0.03*n,0.05*n,0.2,'#2e6016','#1e480c'],
            [0.690*n,0.320*n,0.03*n,0.04*n,0,'#2a5c14','#1a440a'],
            [0.660*n,0.380*n,0.04*n,0.04*n,0.3,'#306418','#204c0e'],
            [0.680*n,0.360*n,0.05*n,0.06*n,-0.1,'#346a1a','#245010'],
            [0.650*n,0.400*n,0.04*n,0.04*n,0.1,'#2c6016','#1c480c'],
            [0.670*n,0.390*n,0.03*n,0.04*n,0,'#285a12','#18440a'],
            [0.340*n,0.400*n,0.06*n,0.05*n,0.1,'#306416','#20480c'],
            [0.360*n,0.420*n,0.05*n,0.06*n,0,'#2e6014','#1e460c'],
            [0.370*n,0.460*n,0.04*n,0.04*n,0.15,'#2a5c12','#1a440a'],
            [0.400*n,0.420*n,0.04*n,0.05*n,-0.1,'#2c5e14','#1c460c'],
            [0.420*n,0.460*n,0.05*n,0.05*n,0.05,'#2e6016','#1e480c'],
            [0.440*n,0.480*n,0.04*n,0.05*n,0,'#2c5e14','#1c460c'],
            [0.480*n,0.460*n,0.07*n,0.06*n,0.1,'#306618','#204c0e'],
            [0.500*n,0.440*n,0.07*n,0.07*n,-0.05,'#346a1a','#245010'],
            [0.520*n,0.480*n,0.06*n,0.05*n,0.2,'#2e6016','#1e480c'],
            [0.560*n,0.500*n,0.05*n,0.05*n,0,'#2c5e14','#1c460c'],
            [0.540*n,0.540*n,0.04*n,0.04*n,0.15,'#285a12','#18440a'],
            [0.580*n,0.520*n,0.04*n,0.05*n,-0.1,'#2a5c14','#1a440a'],
            [0.600*n,0.540*n,0.04*n,0.04*n,0.1,'#265812','#164208'],
            [0.620*n,0.560*n,0.05*n,0.04*n,0,'#285a12','#18440a'],
            [0.700*n,0.340*n,0.04*n,0.08*n,0.2,'#326818','#22480e'],
            [0.720*n,0.360*n,0.03*n,0.05*n,0.1,'#2e6016','#1e460c'],
            [0.740*n,0.350*n,0.03*n,0.06*n,-0.1,'#2c5e14','#1c460c'],
            [0.680*n,0.420*n,0.03*n,0.04*n,0,'#2a5c12','#1a440a'],
            [0.700*n,0.440*n,0.03*n,0.04*n,0.15,'#2c5e14','#1c460c'],
            [0.440*n,0.240*n,0.12*n,0.08*n,0,'#427824','#306218'],
            [0.480*n,0.220*n,0.10*n,0.06*n,-0.1,'#3e7420','#2c5a16'],
            [0.520*n,0.240*n,0.08*n,0.06*n,0.1,'#407622','#2e5e18'],
            [0.560*n,0.220*n,0.10*n,0.06*n,0,'#447a26','#32601c'],
            [0.600*n,0.200*n,0.10*n,0.06*n,0.05,'#427824','#306218'],
            [0.640*n,0.180*n,0.12*n,0.07*n,-0.1,'#447a26','#32601c'],
            [0.360*n,0.240*n,0.08*n,0.06*n,0.1,'#3a6e1c','#285012'],
            [0.340*n,0.260*n,0.06*n,0.05*n,0,'#366a18','#244c0e'],
            [0.260*n,0.340*n,0.06*n,0.08*n,0.1,'#306416','#20480c'],
            [0.280*n,0.380*n,0.06*n,0.08*n,0,'#326818','#224c0e'],
            [0.300*n,0.420*n,0.05*n,0.08*n,-0.1,'#306416','#20480c'],
            [0.240*n,0.360*n,0.04*n,0.06*n,0.1,'#2e6016','#1e460c'],
        ];

        for (var i = 0; i < landBlobs.length; i++) {
            var b = landBlobs[i];
            t.save();
            t.translate(b[0], b[1]);
            t.rotate(b[4]);

            var grad = t.createRadialGradient(0, 0, b[2] * 0.1, 0, 0, Math.max(b[2], b[3]));
            grad.addColorStop(0, b[5]);
            grad.addColorStop(0.5, b[5]);
            grad.addColorStop(1, b[6]);
            t.fillStyle = grad;

            t.beginPath();
            t.ellipse(0, 0, b[2], b[3], 0, 0, Math.PI * 2);
            t.fill();

            for (var k = 0; k < 12; k++) {
                var kx = (Math.random() - 0.5) * b[2] * 1.5;
                var ky = (Math.random() - 0.5) * b[3] * 1.5;
                t.beginPath();
                t.arc(kx, ky, Math.random() * b[2] * 0.22 + b[2] * 0.06, 0, Math.PI * 2);
                var kg = t.createRadialGradient(kx, ky, 0, kx, ky, b[2] * 0.25);
                kg.addColorStop(0, 'rgba(90,155,55,0.5)');
                kg.addColorStop(1, 'rgba(60,110,30,0)');
                t.fillStyle = kg;
                t.fill();
            }

            t.restore();
        }

        for (var j = 0; j < 400; j++) {
            var wx = cx + (Math.random() - 0.5) * r * 2;
            var wy = cy + (Math.random() - 0.5) * r * 2;
            t.beginPath();
            t.arc(wx, wy, Math.random() * 30 + 5, 0, Math.PI * 2);
            t.fillStyle = 'rgba(255,255,255,' + (Math.random() * 0.07) + ')';
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

    function createProceduralNight() {
        var c = document.createElement('canvas');
        c.width = 1024; c.height = 1024;
        var t = c.getContext('2d');

        t.fillStyle = '#020812';
        t.fillRect(0, 0, c.width, c.height);

        var r = c.width * 0.48;
        var cx = c.width * 0.5;
        var cy = c.height * 0.49;

        t.save();
        t.beginPath();
        t.arc(cx, cy, r, 0, Math.PI * 2);
        t.clip();

        var base = t.createRadialGradient(cx * 1.1, cy * 0.85, r * 0.15, cx, cy, r);
        base.addColorStop(0, '#0a1e3a');
        base.addColorStop(0.5, '#061428');
        base.addColorStop(1, '#020812');
        t.fillStyle = base;
        t.fillRect(cx - r, cy - r, r * 2, r * 2);

        var cityLights = [
            [0.58,0.26,35,0.95],[0.60,0.24,32,0.92],[0.56,0.28,30,0.9],
            [0.54,0.30,28,0.88],[0.52,0.32,26,0.85],[0.50,0.34,24,0.82],
            [0.48,0.36,22,0.8],[0.52,0.38,24,0.84],[0.54,0.40,22,0.8],
            [0.50,0.42,20,0.78],[0.48,0.40,18,0.72],[0.46,0.44,16,0.68],
            [0.50,0.46,16,0.7],[0.54,0.44,18,0.74],[0.56,0.42,16,0.68],
            [0.70,0.24,24,0.88],[0.74,0.26,20,0.82],[0.76,0.30,18,0.78],
            [0.68,0.30,22,0.85],[0.66,0.32,18,0.8],[0.64,0.34,16,0.75],
            [0.68,0.36,16,0.72],[0.70,0.32,16,0.76],[0.64,0.38,14,0.7],
            [0.66,0.40,14,0.68],[0.62,0.42,12,0.62],[0.54,0.48,13,0.62],
            [0.50,0.50,11,0.58],[0.42,0.46,13,0.6],[0.40,0.42,11,0.55],
            [0.38,0.44,12,0.58],[0.44,0.28,10,0.48],[0.42,0.30,9,0.45],
            [0.62,0.16,14,0.52],[0.55,0.20,10,0.45],[0.66,0.20,12,0.48],
            [0.60,0.36,16,0.62],[0.62,0.34,14,0.6],
        ];

        for (var i = 0; i < cityLights.length; i++) {
            var cl = cityLights[i];
            var clx = cl[0] * c.width;
            var cly = cl[1] * c.height;
            var grad = t.createRadialGradient(clx, cly, 0, clx, cly, cl[2] * 5);
            grad.addColorStop(0, 'rgba(255,225,125,' + (cl[3] * 0.7) + ')');
            grad.addColorStop(0.12, 'rgba(255,200,80,' + (cl[3] * 0.4) + ')');
            grad.addColorStop(0.35, 'rgba(230,160,50,' + (cl[3] * 0.12) + ')');
            grad.addColorStop(1, 'transparent');
            t.fillStyle = grad;
            t.fillRect(clx - cl[2] * 5, cly - cl[2] * 5, cl[2] * 10, cl[2] * 10);
        }

        for (var j = 0; j < 1500; j++) {
            t.beginPath();
            t.arc(cx + (Math.random() - 0.5) * r * 2, cy + (Math.random() - 0.5) * r * 2,
                Math.random() * 2.5 + 0.4, 0, Math.PI * 2);
            t.fillStyle = 'rgba(255,180,55,' + (Math.random() * 0.22 + 0.03) + ')';
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

    function init() {
        canvas = document.getElementById('earth-canvas');
        ctx = canvas.getContext('2d');

        dayImage = createProceduralDay();
        nightImage = createProceduralNight();

        loadRealTexture(0, function (realTex) {
            if (realTex) {
                dayImage = createDayFromReal(realTex);
                nightImage = createNightFromReal(realTex);
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

    function drawAtmosphere() {
        var glow = ctx.createRadialGradient(earthCX, earthCY, earthRadius * 0.92, earthCX, earthCY, earthRadius * 1.08);
        glow.addColorStop(0, 'transparent');
        glow.addColorStop(0.5, 'rgba(100,180,255,0.12)');
        glow.addColorStop(1, 'transparent');
        ctx.beginPath();
        ctx.arc(earthCX, earthCY, earthRadius * 1.08, 0, Math.PI * 2);
        ctx.fillStyle = glow;
        ctx.fill();
    }

    function draw() {
        var bh = new Date().getUTCHours() + 8;
        var img = (bh >= 6 && bh < 19) ? dayImage : nightImage;
        if (!img) return;

        ctx.clearRect(0, 0, width, height);

        var srcR = img.width * 0.48;
        var srcCX = img.width * 0.5;
        var srcCY = img.height * 0.49;

        drawAtmosphere();

        ctx.save();
        ctx.beginPath();
        ctx.arc(earthCX, earthCY, earthRadius, 0, Math.PI * 2);
        ctx.clip();
        ctx.drawImage(img,
            srcCX - srcR, srcCY - srcR, srcR * 2, srcR * 2,
            earthCX - earthRadius, earthCY - earthRadius, earthRadius * 2, earthRadius * 2);
        ctx.restore();

        ctx.beginPath();
        ctx.arc(earthCX, earthCY, earthRadius + 1.5, 0, Math.PI * 2);
        ctx.strokeStyle = 'rgba(130,195,255,0.25)';
        ctx.lineWidth = 2;
        ctx.stroke();
    }

    return { init: init, draw: draw, resize: resize };
})();