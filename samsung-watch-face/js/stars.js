var Starfield = (function () {
    'use strict';

    var canvas, ctx, width, height, centerX, centerY, radius;
    var starData = [];
    var drawn = false;
    var offCanvas, offCtx;

    function generateStars() {
        var count = 300;
        starData = [];
        for (var i = 0; i < count; i++) {
            var a = Math.random() * Math.PI * 2;
            var d = Math.pow(Math.random(), 0.5) * radius * 0.96;
            starData.push({
                x: centerX + Math.cos(a) * d,
                y: centerY + Math.sin(a) * d,
                r: Math.random() * 1.6 + 0.3,
                brightness: Math.random() * 0.5 + 0.5,
                isBlue: Math.random() < 0.12
            });
        }
    }

    function prerender() {
        offCanvas = document.createElement('canvas');
        offCanvas.width = width * (window.devicePixelRatio || 1);
        offCanvas.height = height * (window.devicePixelRatio || 1);
        offCtx = offCanvas.getContext('2d');
        var dpr = window.devicePixelRatio || 1;
        offCtx.setTransform(dpr, 0, 0, dpr, 0, 0);

        offCtx.fillStyle = '#020210';
        offCtx.fillRect(0, 0, width, height);

        for (var i = 0; i < 3; i++) {
            var nx = centerX + Math.sin(i * 2.1) * radius * 0.35;
            var ny = centerY + Math.cos(i * 1.7) * radius * 0.35;
            var g = offCtx.createRadialGradient(nx, ny, 0, nx, ny, radius * 0.5);
            var colors = [
                ['rgba(30,20,70,0.04)', 'transparent'],
                ['rgba(15,10,50,0.03)', 'transparent'],
                ['rgba(40,15,60,0.03)', 'transparent']
            ];
            g.addColorStop(0, colors[i][0]);
            g.addColorStop(1, colors[i][1]);
            offCtx.fillStyle = g;
            offCtx.fillRect(centerX - radius, centerY - radius, radius * 2, radius * 2);
        }

        offCtx.save();
        offCtx.beginPath();
        offCtx.arc(centerX, centerY, radius, 0, Math.PI * 2);
        offCtx.clip();

        for (var j = 0; j < starData.length; j++) {
            var s = starData[j];
            offCtx.beginPath();
            offCtx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
            if (s.isBlue) {
                offCtx.fillStyle = 'rgba(150,170,255,' + (s.brightness * 0.7) + ')';
            } else {
                offCtx.fillStyle = 'rgba(255,255,255,' + s.brightness + ')';
            }
            offCtx.fill();
        }

        offCtx.restore();

        drawn = true;
    }

    function init() {
        canvas = document.getElementById('bg-canvas');
        ctx = canvas.getContext('2d');
        resize();
        generateStars();
        prerender();
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
        radius = Math.min(width, height) / 2;
        drawn = false;
    }

    function draw() {
        if (!drawn) {
            generateStars();
            prerender();
        }
        if (offCanvas) {
            ctx.drawImage(offCanvas, 0, 0);
        }
    }

    return {
        init: init,
        draw: draw,
        resize: resize
    };
})();