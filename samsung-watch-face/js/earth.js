var Earth3D = (function () {
    'use strict';

    var canvas, ctx;
    var width, height, centerX, centerY, watchRadius;
    var earthCX, earthCY, earthRadius;
    var dayTexture = null;
    var realTexLoaded = false;

    var TEXTURE_URLS = [
        'https://eoimages.gsfc.nasa.gov/images/imagerecords/57000/57730/land_ocean_ice_cloud_2048.jpg',
        'https://upload.wikimedia.org/wikipedia/commons/thumb/2/23/Blue_Marble_2002.png/1024px-Blue_Marble_2002.png'
    ];

    function loadRealTexture(urlIndex, callback) {
        if (urlIndex >= TEXTURE_URLS.length) { callback(null); return; }
        var img = new Image();
        img.crossOrigin = 'anonymous';
        var timeout = setTimeout(function () {
            img.src = '';
            loadRealTexture(urlIndex + 1, callback);
        }, 6000);
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
        var texW = realTex.width, texH = realTex.height;
        var srcCX = texW * 0.755, srcCY = texH * 0.36;
        var srcR = Math.min(texW * 0.14, texH * 0.28);
        t.drawImage(realTex, srcCX - srcR, srcCY - srcR, srcR * 2, srcR * 2, cx - r, cy - r, r * 2, r * 2);
        t.restore();
        return c;
    }

    function pointInPolygon(px, py, polygon) {
        var inside = false;
        for (var i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
            var xi = polygon[i][0], yi = polygon[i][1];
            var xj = polygon[j][0], yj = polygon[j][1];
            if ((yi > py) !== (yj > py) && px < (xj - xi) * (py - yi) / (yj - yi) + xi) {
                inside = !inside;
            }
        }
        return inside;
    }

    function distToPolygonEdge(px, py, polygon) {
        var minD = Infinity;
        for (var i = 0; i < polygon.length; i++) {
            var j = (i + 1) % polygon.length;
            var ax = polygon[i][0], ay = polygon[i][1];
            var bx = polygon[j][0], by = polygon[j][1];
            var dx = bx - ax, dy = by - ay;
            var len2 = dx * dx + dy * dy;
            var t = len2 === 0 ? 0 : Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / len2));
            var cx = ax + t * dx, cy = ay + t * dy;
            var d = Math.sqrt((px - cx) * (px - cx) + (py - cy) * (py - cy));
            if (d < minD) minD = d;
        }
        return minD;
    }

    function inRect(lon, lat, lon1, lon2, lat1, lat2) {
        return lon >= lon1 && lon <= lon2 && lat >= lat1 && lat <= lat2;
    }

    function inEllipse(lon, lat, clon, clat, rx, ry) {
        var dx = (lon - clon) / rx, dy = (lat - clat) / ry;
        return dx * dx + dy * dy <= 1;
    }

    var chinaPolygon = [
        [72,53],[80,54],[88,54],[93,53],[98,52],[104,51],[109,50],
        [114,49],[118,49],[123,51],[127,53],[132,54],[137,56],
        [137,48],[136,56],[132,51],[129,47],[126,44],[124,40],
        [123,36],[122,33],[122,29],[120,26],[118,23],[115,19],
        [111,20],[108,22],[105,21],[101,20],[97,19],[94,22],
        [92,29],[88,29],[85,29],[81,30],[78,33],[75,36],[73,43],[72,53]
    ];

    var tibetPolygon = [
        [78,32],[80,30],[84,27],[88,27],[92,28],[96,28],[98,29],[100,29],
        [102,28],[104,28],[104,30],[102,32],[100,34],[98,36],[95,36],
        [92,35],[88,34],[84,33],[80,32],[78,32]
    ];

    function isLand(lon, lat) {
        if (pointInPolygon(lon, lat, chinaPolygon)) return true;

        if (inEllipse(lon, lat, 127, 37, 4, 6)) return true;
        if (inEllipse(lon, lat, 128, 35, 3, 4)) return true;

        if (inEllipse(lon, lat, 137, 38, 2.5, 10)) return true;
        if (inEllipse(lon, lat, 140, 36, 2, 8)) return true;
        if (inEllipse(lon, lat, 135, 34, 2, 6)) return true;
        if (inEllipse(lon, lat, 130, 31, 2, 4)) return true;

        if (inEllipse(lon, lat, 121, 23.5, 1.5, 1.5)) return true;

        if (inRect(lon, lat, 68, 97, 8, 37)) return true;

        if (inRect(lon, lat, 87, 120, 42, 52)) return true;

        if (inRect(lon, lat, 95, 110, 5, 23)) return true;

        if (inRect(lon, lat, 50, 87, 35, 50)) return true;

        if (inRect(lon, lat, 60, 170, 55, 80)) return true;

        if (inRect(lon, lat, 30, 65, 15, 42)) return true;

        if (inEllipse(lon, lat, 106, -6, 6, 3)) return true;
        if (inEllipse(lon, lat, 115, -3, 5, 3)) return true;
        if (inEllipse(lon, lat, 125, -5, 4, 2.5)) return true;
        if (inEllipse(lon, lat, 138, -4, 3, 2)) return true;

        if (inEllipse(lon, lat, 122, 13, 1.5, 4)) return true;
        if (inEllipse(lon, lat, 124, 11, 1, 3)) return true;

        if (inEllipse(lon, lat, 145, 55, 2, 3)) return true;
        if (inEllipse(lon, lat, 143, 45, 1.5, 2)) return true;

        return false;
    }

    function getTerrainType(lon, lat) {
        if (pointInPolygon(lon, lat, tibetPolygon)) return 'tibet';

        if (lon >= 78 && lon <= 103 && lat >= 32 && lat <= 39 && !pointInPolygon(lon, lat, tibetPolygon)) {
            if (lon <= 90 && lat >= 35) return 'highland';
            return 'plateau';
        }

        if (lon >= 73 && lon <= 95 && lat >= 40 && lat <= 50) return 'highland';

        if (lon >= 95 && lon <= 105 && lat >= 38 && lat <= 45) return 'plateau';

        if (lat >= 55) return 'tundra';

        return 'lowland';
    }

    function createProceduralEarth() {
        var S = 1024;
        var c = document.createElement('canvas');
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

        var GW = 300, GH = 300;
        var grid = new Uint8Array(GW * GH);
        var lonMin = 15, lonMax = 195;
        var latMin = -15, latMax = 85;

        function gxToLon(gx) { return lonMin + (gx / (GW - 1)) * (lonMax - lonMin); }
        function gyToLat(gy) { return latMax - (gy / (GH - 1)) * (latMax - latMin); }

        for (var gy = 0; gy < GH; gy++) {
            for (var gx = 0; gx < GW; gx++) {
                var lon = gxToLon(gx);
                var lat = gyToLat(gy);
                grid[gy * GW + gx] = isLand(lon, lat) ? 1 : 0;
            }
        }

        function sampleGrid(tx, ty) {
            var gx = (tx / S) * (GW - 1);
            var gy = (ty / S) * (GH - 1);
            var ix = Math.floor(gx), iy = Math.floor(gy);
            var fx = gx - ix, fy = gy - iy;

            ix = Math.max(0, Math.min(GW - 2, ix));
            iy = Math.max(0, Math.min(GH - 2, iy));

            var v00 = grid[iy * GW + ix];
            var v10 = grid[iy * GW + ix + 1];
            var v01 = grid[(iy + 1) * GW + ix];
            var v11 = grid[(iy + 1) * GW + ix + 1];

            return v00 * (1 - fx) * (1 - fy) + v10 * fx * (1 - fy) + v01 * (1 - fx) * fy + v11 * fx * fy;
        }

        var oceanGrad = t.createRadialGradient(400, 350, r * 0.05, cx, cy, r);
        oceanGrad.addColorStop(0, '#3399dd');
        oceanGrad.addColorStop(0.12, '#2288cc');
        oceanGrad.addColorStop(0.35, '#1868a8');
        oceanGrad.addColorStop(0.65, '#105090');
        oceanGrad.addColorStop(1, '#083060');
        t.fillStyle = oceanGrad;
        t.fillRect(cx - r, cy - r, r * 2, r * 2);

        var step = 3;
        for (var ty = 0; ty < S; ty += step) {
            for (var tx = 0; tx < S; tx += step) {
                var dx = tx - cx, dy = ty - cy;
                if (dx * dx + dy * dy > r * r) continue;

                var landVal = sampleGrid(tx, ty);

                if (landVal < 0.3) continue;

                var lon = lonMin + (tx / S) * (lonMax - lonMin);
                var lat = latMax - (ty / S) * (latMax - latMin);
                var terrain = getTerrainType(lon, lat);
                var alpha = Math.min(1, landVal);

                var color;
                if (terrain === 'tibet') {
                    color = 'rgba(220,210,190,' + alpha + ')';
                } else if (terrain === 'highland') {
                    color = 'rgba(160,140,100,' + alpha + ')';
                } else if (terrain === 'plateau') {
                    color = 'rgba(170,155,115,' + alpha + ')';
                } else if (terrain === 'tundra') {
                    color = 'rgba(120,140,110,' + alpha + ')';
                } else {
                    color = 'rgba(70,130,40,' + alpha + ')';
                }

                t.fillStyle = color;
                t.fillRect(tx, ty, step, step);
            }
        }

        for (var ty = 0; ty < S; ty += step) {
            for (var tx = 0; tx < S; tx += step) {
                var dx = tx - cx, dy = ty - cy;
                if (dx * dx + dy * dy > r * r) continue;
                var landVal = sampleGrid(tx, ty);
                if (landVal > 0.1 && landVal < 0.9) {
                    var alpha = (landVal > 0.5) ? (1 - landVal) * 0.6 : landVal * 0.4;
                    t.fillStyle = 'rgba(50,100,30,' + alpha + ')';
                    t.fillRect(tx, ty, step, step);
                }
            }
        }

        for (var j = 0; j < 500; j++) {
            var wx = cx + (Math.random() - 0.5) * r * 2;
            var wy = cy + (Math.random() - 0.5) * r * 2;
            var wdx = wx - cx, wdy = wy - cy;
            if (wdx * wdx + wdy * wdy > r * r) continue;
            t.beginPath();
            t.arc(wx, wy, Math.random() * 20 + 3, 0, Math.PI * 2);
            t.fillStyle = 'rgba(255,255,255,' + (Math.random() * 0.04) + ')';
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

        var nightAlpha, terminatorX, fadeWidth = earthRadius * 0.55;

        if (beijingHour >= 6 && beijingHour < 19) {
            var daytime = beijingHour - 6;
            var sunAngle = (daytime / 13) * Math.PI;
            terminatorX = earthCX + Math.cos(sunAngle) * earthRadius * 1.05;
            var ng = ctx.createLinearGradient(terminatorX + fadeWidth, 0, terminatorX - fadeWidth, 0);
            ng.addColorStop(0, 'rgba(2,8,30,0.72)');
            ng.addColorStop(0.35, 'rgba(2,8,30,0.4)');
            ng.addColorStop(0.65, 'rgba(2,8,30,0.05)');
            ng.addColorStop(1, 'rgba(2,8,30,0)');
            ctx.fillStyle = ng;
            ctx.fillRect(earthCX - earthRadius, earthCY - earthRadius, earthRadius * 2, earthRadius * 2);
        } else if (beijingHour >= 19) {
            var np = (beijingHour - 19) / 5;
            nightAlpha = 0.55 + Math.min(0.35, np * 0.35);
            terminatorX = earthCX - earthRadius * (1 - Math.min(1.2, np * 1.5));
            terminatorX = Math.max(earthCX - earthRadius, Math.min(earthCX + earthRadius, terminatorX));
            var ng = ctx.createLinearGradient(terminatorX + fadeWidth, 0, terminatorX - fadeWidth, 0);
            ng.addColorStop(0, 'rgba(2,6,26,' + nightAlpha + ')');
            ng.addColorStop(0.3, 'rgba(2,6,26,' + (nightAlpha * 0.6) + ')');
            ng.addColorStop(0.6, 'rgba(2,6,26,' + (nightAlpha * 0.12) + ')');
            ng.addColorStop(1, 'rgba(2,6,26,0)');
            ctx.fillStyle = ng;
            ctx.fillRect(earthCX - earthRadius, earthCY - earthRadius, earthRadius * 2, earthRadius * 2);

            if (nightAlpha > 0.55) {
                var la = (nightAlpha - 0.55) / 0.35;
                drawCityLights(la);
            }
        } else {
            var bd = (6 - beijingHour) / 6;
            nightAlpha = 0.55 + Math.min(0.35, bd * 0.35);
            terminatorX = earthCX + earthRadius * (1 - Math.min(1.2, bd * 1.5));
            terminatorX = Math.max(earthCX - earthRadius, Math.min(earthCX + earthRadius, terminatorX));
            var ng = ctx.createLinearGradient(terminatorX + fadeWidth, 0, terminatorX - fadeWidth, 0);
            ng.addColorStop(0, 'rgba(2,6,26,' + nightAlpha + ')');
            ng.addColorStop(0.3, 'rgba(2,6,26,' + (nightAlpha * 0.6) + ')');
            ng.addColorStop(0.6, 'rgba(2,6,26,' + (nightAlpha * 0.12) + ')');
            ng.addColorStop(1, 'rgba(2,6,26,0)');
            ctx.fillStyle = ng;
            ctx.fillRect(earthCX - earthRadius, earthCY - earthRadius, earthRadius * 2, earthRadius * 2);

            if (nightAlpha > 0.55) {
                var la = (nightAlpha - 0.55) / 0.35;
                drawCityLights(la);
            }
        }

        ctx.restore();
    }

    function drawCityLights(alpha) {
        var lights = [
            [0.58,0.24,30],[0.60,0.26,26],[0.56,0.28,24],
            [0.54,0.30,22],[0.52,0.32,20],[0.50,0.34,18],
            [0.52,0.38,20],[0.54,0.40,18],[0.50,0.42,16],
            [0.48,0.40,14],[0.46,0.36,16],[0.48,0.36,18],
            [0.70,0.24,20],[0.74,0.26,16],[0.68,0.30,18],
            [0.66,0.32,14],[0.64,0.34,13],[0.68,0.36,12],
            [0.70,0.32,14],[0.64,0.38,11],[0.66,0.40,10],
            [0.62,0.42,10],[0.54,0.46,10],[0.50,0.48,9],
            [0.42,0.46,10],[0.40,0.42,9],[0.38,0.44,9],
        ];
        for (var i = 0; i < lights.length; i++) {
            var cl = lights[i];
            var lx = earthCX + (cl[0] - 0.5) * earthRadius * 2;
            var ly = earthCY + (cl[1] - 0.49) * earthRadius * 2;
            var lr = cl[2] * (earthRadius / 480);
            var lg = ctx.createRadialGradient(lx, ly, 0, lx, ly, lr * 3);
            lg.addColorStop(0, 'rgba(255,220,110,' + (0.7 * alpha) + ')');
            lg.addColorStop(0.2, 'rgba(255,190,65,' + (0.35 * alpha) + ')');
            lg.addColorStop(0.5, 'rgba(220,155,45,' + (0.07 * alpha) + ')');
            lg.addColorStop(1, 'transparent');
            ctx.fillStyle = lg;
            ctx.fillRect(lx - lr * 3, ly - lr * 3, lr * 6, lr * 6);
        }
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