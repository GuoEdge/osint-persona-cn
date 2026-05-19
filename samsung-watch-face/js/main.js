(function () {
    'use strict';

    var ambientMode = false;

    function init() {
        Starfield.init();
        Earth3D.init();
        Clock.init();

        Starfield.start();
        Earth3D.start();
        Clock.start();
        Indicators.start();
    }

    function enterAmbient() {
        ambientMode = true;
        Earth3D.stop();
        document.getElementById('earth-canvas').style.display = 'none';
        document.getElementById('digital-time').style.opacity = '0.5';
        document.getElementById('date-display').style.display = 'none';
        var indicators = document.querySelectorAll('.indicator');
        for (var i = 0; i < indicators.length; i++) {
            indicators[i].style.opacity = '0.3';
        }
    }

    function exitAmbient() {
        ambientMode = false;
        document.getElementById('earth-canvas').style.display = 'block';
        document.getElementById('digital-time').style.opacity = '1';
        document.getElementById('date-display').style.display = 'block';
        var indicators = document.querySelectorAll('.indicator');
        for (var i = 0; i < indicators.length; i++) {
            indicators[i].style.opacity = '1';
        }
        Earth3D.start();
    }

    function handleResize() {
        Starfield.resize();
        Earth3D.resize();
        Clock.resize();
    }

    if (typeof window !== 'undefined') {
        window.addEventListener('resize', handleResize);

        window.addEventListener('tizenhwkey', function (e) {
            if (e.keyName === 'back') {
                try { tizen.application.getCurrentApplication().exit(); } catch (err) {}
            }
        });

        if (typeof tizen !== 'undefined' && tizen.power) {
            tizen.power.request('SCREEN', 'SCREEN_NORMAL');
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    window.watchFace = {
        enterAmbient: enterAmbient,
        exitAmbient: exitAmbient
    };
})();