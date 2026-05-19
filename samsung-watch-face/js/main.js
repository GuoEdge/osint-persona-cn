(function () {
    'use strict';

    var animFrame;
    var ambient = false;

    function drawFrame(ts) {
        Starfield.draw();
        Earth3D.draw(ts);
        Clock.draw(ts);
    }

    function loop(ts) {
        drawFrame(ts);
        animFrame = requestAnimationFrame(loop);
    }

    function init() {
        Starfield.init();
        Earth3D.init();
        Clock.init();

        Indicators.start();
        loop(performance.now());
    }

    function handleResize() {
        Starfield.resize();
        Earth3D.resize();
        Clock.resize();
    }

    function handleVisibility() {
        if (document.hidden) {
            ambient = true;
            Earth3D.stop();
        } else {
            if (ambient) {
                Earth3D.triggerWakeUp();
                Earth3D.start();
            }
            ambient = false;
        }
    }

    if (typeof window !== 'undefined') {
        window.addEventListener('resize', handleResize);
        document.addEventListener('visibilitychange', handleVisibility);

        if (typeof tizen !== 'undefined' && tizen.power) {
            tizen.power.request('SCREEN', 'SCREEN_NORMAL');
        }

        window.addEventListener('tizenhwkey', function (e) {
            if (e.keyName === 'back') {
                try { tizen.application.getCurrentApplication().exit(); } catch (err) {}
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();