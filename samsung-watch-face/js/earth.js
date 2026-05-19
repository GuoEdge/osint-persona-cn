var Earth3D = (function () {
    'use strict';

    var canvas, ctx;
    var width, height, centerX, centerY, watchRadius;
    var earthCX, earthCY, earthRadius;
    var animationId;
    var dayTex = null, nightTex = null;
    var realDayTex = null;
    var REAL_EARTH_URL = 'https://eoimages.gsfc.nasa.gov/images/imagerecords/57000/57723/land_ocean_ice_cloud_2048.jpg';

    var CHINA_LON = 105;
    var CHINA_LAT = 35;
    var baseRotation = -CHINA_LON / 360;

    var wakeUpAnim = {
        active: false,
        startTime: 0,
        duration: 2500,
        totalRotations: 2.0
    };

    function createHighQualityTexture() {
        var tc = document.createElement('canvas');
        tc.width = 2048;
        tc.height = 1024;
        var tctx = tc.getContext('2d');

        var oceanGrad = tctx.createLinearGradient(0, 0, 0, tc.height);
        oceanGrad.addColorStop(0, '#0a3d68');
        oceanGrad.addColorStop(0.2, '#0d5490');
        oceanGrad.addColorStop(0.5, '#156eb8');
        oceanGrad.addColorStop(0.8, '#0d5490');
        oceanGrad.addColorStop(1, '#0a3d68');
        tctx.fillStyle = oceanGrad;
        tctx.fillRect(0, 0, tc.width, tc.height);

        for (var i = 0; i < 6000; i++) {
            tctx.fillStyle = 'rgba(15,80,160,' + (Math.random() * 0.06) + ')';
            tctx.fillRect(Math.random() * tc.width, Math.random() * tc.height,
                Math.random() * 6 + 1, Math.random() * 3 + 0.5);
        }

        var continents = [
            { cx: 0.73, cy: 0.30, rx: 0.16, ry: 0.24 },
            { cx: 0.74, cy: 0.28, rx: 0.14, ry: 0.21 },
            { cx: 0.69, cy: 0.40, rx: 0.11, ry: 0.17 },
            { cx: 0.76, cy: 0.55, rx: 0.09, ry: 0.09 },
            { cx: 0.70, cy: 0.19, rx: 0.13, ry: 0.13 },
            { cx: 0.60, cy: 0.34, rx: 0.07, ry: 0.11 },
            { cx: 0.30, cy: 0.27, rx: 0.11, ry: 0.17 },
            { cx: 0.31, cy: 0.29, rx: 0.09, ry: 0.15 },
            { cx: 0.17, cy: 0.37, rx: 0.13, ry: 0.21 },
            { cx: 0.19, cy: 0.35, rx: 0.11, ry: 0.19 },
            { cx: 0.85, cy: 0.29, rx: 0.08, ry: 0.11 },
            { cx: 0.21, cy: 0.17, rx: 0.10, ry: 0.11 },
            { cx: 0.50, cy: 0.37, rx: 0.05, ry: 0.07 },
            { cx: 0.35, cy: 0.50, rx: 0.04, ry: 0.06 },
            { cx: 0.90, cy: 0.50, rx: 0.04, ry: 0.05 },
            { cx: 0.79, cy: 0.43, rx: 0.05, ry: 0.06 },
            { cx: 0.81, cy: 0.15, rx: 0.06, ry: 0.08 },
            { cx: 0.48, cy: 0.55, rx: 0.04, ry: 0.05 },
            { cx: 0.16, cy: 0.28, rx: 0.07, ry: 0.09 },
            { cx: 0.23, cy: 0.45, rx: 0.06, ry: 0.08 },
            { cx: 0.83, cy: 0.35, rx: 0.06, ry: 0.09 },
            { cx: 0.65, cy: 0.45, rx: 0.04, ry: 0.06 },
            { cx: 0.72, cy: 0.32, rx: 0.05, ry: 0.07 },
            { cx: 0.25, cy: 0.26, rx: 0.05, ry: 0.07 },
            { cx: 0.15, cy: 0.33, rx: 0.04, ry: 0.06 },
            { cx: 0.38, cy: 0.29, rx: 0.04, ry: 0.05 },
        ];

        for (var j = 0; j < continents.length; j++) {
            var c = continents[j];
            var cxx = c.cx * tc.width;
            var cyy = c.cy * tc.height;
            var rx = c.rx * tc.width;
            var ry = c.ry * tc.height;

            tctx.save();
            tctx.translate(cxx, cyy);

            var land = tctx.createRadialGradient(0, 0, 0, 0, 0, rx);
            land.addColorStop(0, '#6a9a42');
            land.addColorStop(0.2, '#5d8c38');
            land.addColorStop(0.5, '#4a7a2a');
            land.addColorStop(0.8, '#356820');
            land.addColorStop(1, 'rgba(30,60,18,0)');
            tctx.fillStyle = land;
            tctx.beginPath();
            tctx.ellipse(0, 0, rx, ry, (Math.random() - 0.5) * 0.3, 0, Math.PI * 2);
            tctx.fill();

            for (var k = 0; k < 20; k++) {
                var bx = (Math.random() - 0.5) * rx * 1.1;
                var by = (Math.random() - 0.5) * ry * 1.1;
                var br = Math.random() * rx * 0.25 + rx * 0.04;
                tctx.beginPath();
                tctx.arc(bx, by, br, 0, Math.PI * 2);
                tctx.fillStyle = 'rgba(90,140,55,0.3)';
                tctx.fill();
            }

            if (Math.random() < 0.3) {
                var mx = (Math.random() - 0.5) * rx * 0.5;
                var my = (Math.random() - 0.5) * ry * 0.5;
                var mrx = Math.random() * rx * 0.25 + rx * 0.1;
                var mry = Math.random() * ry * 0.25 + ry * 0.1;
                var peak = tctx.createRadialGradient(mx, my, 0, mx, my, mrx);
                peak.addColorStop(0, 'rgba(190,170,140,0.45)');
                peak.addColorStop(0.5, 'rgba(160,140,110,0.2)');
                peak.addColorStop(1, 'transparent');
                tctx.fillStyle = peak;
                tctx.beginPath();
                tctx.ellipse(mx, my, mrx, mry, 0, 0, Math.PI * 2);
                tctx.fill();
            }

            tctx.restore();
        }

        var cc = document.createElement('canvas');
        cc.width = 2048;
        cc.height = 1024;
        var cctx = cc.getContext('2d');
        for (var m = 0; m < 1500; m++) {
            var clx = Math.random() * cc.width;
            var cly = Math.random() * cc.height;
            var clr = Math.random() * 35 + 8;
            cctx.beginPath();
            cctx.arc(clx, cly, clr, 0, Math.PI * 2);
            cctx.fillStyle = 'rgba(255,255,255,' + (Math.random() * 0.1) + ')';
            cctx.fill();
        }
        tctx.drawImage(cc, 0, 0);

        return tc;
    }

    function createNightTexture() {
        var nc = document.createElement('canvas');
        nc.width = 2048;
        nc.height = 1024;
        var nctx = nc.getContext('2d');
        nctx.fillStyle = '#020812';
        nctx.fillRect(0, 0, nc.width, nc.height);

        var clusters = [
            { x: 0.74, y: 0.30, r: 60, i: 0.9 },{ x: 0.75, y: 0.32, r: 50, i: 0.85 },
            { x: 0.73, y: 0.29, r: 40, i: 0.8 },{ x: 0.76, y: 0.31, r: 55, i: 0.9 },
            { x: 0.82, y: 0.33, r: 70, i: 0.95 },{ x: 0.83, y: 0.32, r: 55, i: 0.9 },
            { x: 0.81, y: 0.30, r: 60, i: 0.92 },{ x: 0.80, y: 0.34, r: 45, i: 0.85 },
            { x: 0.68, y: 0.36, r: 40, i: 0.75 },{ x: 0.67, y: 0.35, r: 35, i: 0.7 },
            { x: 0.58, y: 0.34, r: 35, i: 0.7 },{ x: 0.57, y: 0.35, r: 30, i: 0.65 },
            { x: 0.30, y: 0.28, r: 45, i: 0.8 },{ x: 0.31, y: 0.30, r: 40, i: 0.75 },
            { x: 0.29, y: 0.32, r: 35, i: 0.7 },{ x: 0.32, y: 0.27, r: 35, i: 0.7 },
            { x: 0.28, y: 0.29, r: 35, i: 0.75 },{ x: 0.85, y: 0.28, r: 50, i: 0.85 },
            { x: 0.86, y: 0.30, r: 35, i: 0.75 },{ x: 0.87, y: 0.29, r: 30, i: 0.7 },
            { x: 0.40, y: 0.30, r: 30, i: 0.7 },{ x: 0.41, y: 0.31, r: 25, i: 0.65 },
            { x: 0.34, y: 0.29, r: 20, i: 0.6 },{ x: 0.33, y: 0.31, r: 18, i: 0.55 },
            { x: 0.50, y: 0.33, r: 22, i: 0.6 },{ x: 0.20, y: 0.32, r: 28, i: 0.65 },
            { x: 0.18, y: 0.30, r: 22, i: 0.6 },{ x: 0.23, y: 0.33, r: 18, i: 0.55 },
        ];

        for (var i = 0; i < clusters.length; i++) {
            var cl = clusters[i];
            var clx = cl.x * nc.width;
            var cly = cl.y * nc.height;
            var g = nctx.createRadialGradient(clx, cly, 0, clx, cly, cl.r * 3);
            g.addColorStop(0, 'rgba(255,200,100,' + (cl.i * 0.5) + ')');
            g.addColorStop(0.25, 'rgba(255,180,60,' + (cl.i * 0.3) + ')');
            g.addColorStop(0.5, 'rgba(200,140,30,' + (cl.i * 0.12) + ')');
            g.addColorStop(1, 'transparent');
            nctx.fillStyle = g;
            nctx.fillRect(clx - cl.r * 3, cly - cl.r * 3, cl.r * 6, cl.r * 6);
        }

        for (var j = 0; j < 2000; j++) {
            nctx.beginPath();
            nctx.arc(Math.random() * nc.width, Math.random() * nc.height,
                Math.random() * 2.5 + 0.5, 0, Math.PI * 2);
            nctx.fillStyle = 'rgba(255,170,50,' + (Math.random() * 0.22 + 0.02) + ')';
            nctx.fill();
        }
        return nc;
    }

    function loadRealTexture() {
        var img = new Image();
        img.crossOrigin = 'anonymous';
        img.onload = function () {
            var tc = document.createElement('canvas');
            tc.width = img.width;
            tc.height = img.height;
            var tctx = tc.getContext('2d');
            tctx.drawImage(img, 0, 0);
            realDayTex = tc;
        };
        img.onerror = function () {};
        img.src = REAL_EARTH_URL;
    }

    function init() {
        canvas = document.getElementById('earth-canvas');
        ctx = canvas.getContext('2d');
        dayTex = createHighQualityTexture();
        nightTex = createNightTexture();
        loadRealTexture();
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
        earthRadius = watchRadius * 0.23;
        earthCX = centerX;
        earthCY = centerY + watchRadius * 0.24;
    }

    function triggerWakeUp() {
        wakeUpAnim.active = true;
        wakeUpAnim.startTime = performance.now();
    }

    function getWakeUpRotation(now) {
        if (!wakeUpAnim.active) return 0;
        var elapsed = now - wakeUpAnim.startTime;
        if (elapsed >= wakeUpAnim.duration) {
            wakeUpAnim.active = false;
            return wakeUpAnim.totalRotations;
        }
        var t = elapsed / wakeUpAnim.duration;
        var eased = 1 - Math.pow(1 - t, 4);
        return wakeUpAnim.totalRotations * eased;
    }

    function getSunAngleRad() {
        var now = new Date();
        var total = (now.getUTCHours() + 8) * 3600 + now.getUTCMinutes() * 60 + now.getUTCSeconds();
        return ((total / 86400) * 360 - 90) * Math.PI / 180;
    }

    function draw(timestamp) {
        ctx.clearRect(0, 0, width, height);
        var now = new Date();
        var totalSec = (now.getUTCHours() + 8) * 3600 + now.getUTCMinutes() * 60 + now.getUTCSeconds();

        var wakeRot = getWakeUpRotation(timestamp);
        var texOffset = (totalSec / 86400 + baseRotation + wakeRot) % 1;

        var srcTex = realDayTex || dayTex;
        var tex = srcTex || dayTex;

        ctx.save();
        ctx.beginPath();
        ctx.arc(earthCX, earthCY, earthRadius, 0, Math.PI * 2);
        ctx.clip();

        var texW = tex.width;
        var halfW = texW / 2;
        var sx = texOffset * texW;

        ctx.drawImage(tex, sx, 0, halfW, tex.height,
            earthCX - earthRadius, earthCY - earthRadius, earthRadius * 2, earthRadius * 2);
        ctx.drawImage(tex, sx - texW, 0, halfW, tex.height,
            earthCX - earthRadius, earthCY - earthRadius, earthRadius * 2, earthRadius * 2);

        var sunRad = getSunAngleRad();
        var shadeGrad = ctx.createLinearGradient(
            earthCX + Math.cos(sunRad + Math.PI / 2) * earthRadius,
            earthCY + Math.sin(sunRad + Math.PI / 2) * earthRadius,
            earthCX + Math.cos(sunRad - Math.PI / 2) * earthRadius,
            earthCY + Math.sin(sunRad - Math.PI / 2) * earthRadius
        );
        shadeGrad.addColorStop(0, 'rgba(0,0,0,0.72)');
        shadeGrad.addColorStop(0.3, 'rgba(0,0,0,0.6)');
        shadeGrad.addColorStop(0.45, 'rgba(0,0,0,0.2)');
        shadeGrad.addColorStop(0.5, 'rgba(0,0,0,0)');
        shadeGrad.addColorStop(0.55, 'rgba(0,0,0,0)');
        shadeGrad.addColorStop(0.7, 'rgba(0,0,0,0.05)');
        shadeGrad.addColorStop(1, 'rgba(0,0,0,0.1)');
        ctx.fillStyle = shadeGrad;
        ctx.fillRect(earthCX - earthRadius, earthCY - earthRadius, earthRadius * 2, earthRadius * 2);

        var nightGrad = ctx.createLinearGradient(
            earthCX + Math.cos(sunRad + Math.PI / 2) * earthRadius,
            earthCY + Math.sin(sunRad + Math.PI / 2) * earthRadius,
            earthCX + Math.cos(sunRad - Math.PI / 2) * earthRadius,
            earthCY + Math.sin(sunRad - Math.PI / 2) * earthRadius
        );
        nightGrad.addColorStop(0, 'rgba(0,0,0,0)');
        nightGrad.addColorStop(0.3, 'rgba(0,0,0,0)');
        nightGrad.addColorStop(0.45, 'rgba(0,0,0,0)');
        nightGrad.addColorStop(0.5, 'rgba(0,0,0,0.25)');
        nightGrad.addColorStop(0.55, 'rgba(0,0,0,0.6)');
        nightGrad.addColorStop(0.7, 'rgba(0,0,0,0.7)');
        nightGrad.addColorStop(1, 'rgba(0,0,0,0.75)');

        ctx.drawImage(nightTex, sx, 0, halfW, nightTex.height,
            earthCX - earthRadius, earthCY - earthRadius, earthRadius * 2, earthRadius * 2);
        ctx.drawImage(nightTex, sx - texW, 0, halfW, nightTex.height,
            earthCX - earthRadius, earthCY - earthRadius, earthRadius * 2, earthRadius * 2);
        ctx.globalCompositeOperation = 'destination-in';
        ctx.fillStyle = nightGrad;
        ctx.fillRect(earthCX - earthRadius, earthCY - earthRadius, earthRadius * 2, earthRadius * 2);
        ctx.globalCompositeOperation = 'source-over';

        ctx.restore();

        ctx.beginPath();
        ctx.arc(earthCX, earthCY, earthRadius + 1, 0, Math.PI * 2);
        ctx.strokeStyle = 'rgba(100,150,220,0.25)';
        ctx.lineWidth = 1.5;
        ctx.stroke();

        ctx.beginPath();
        ctx.arc(earthCX, earthCY, earthRadius + 3, 0, Math.PI * 2);
        var glow = ctx.createRadialGradient(earthCX, earthCY, earthRadius * 0.85, earthCX, earthCY, earthRadius + 4);
        glow.addColorStop(0, 'transparent');
        glow.addColorStop(1, 'rgba(60,100,200,0.15)');
        ctx.strokeStyle = glow;
        ctx.lineWidth = 3;
        ctx.stroke();
    }

    function animate(timestamp) {
        draw(timestamp);
        animationId = requestAnimationFrame(animate);
    }

    function start() {
        if (animationId) return;
        triggerWakeUp();
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
        triggerWakeUp: triggerWakeUp
    };
})();