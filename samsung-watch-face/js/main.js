(function () {
    'use strict';

    var animFrame;

    function loop(ts) {
        Starfield.draw();
        Earth3D.draw();
        Clock.draw(ts);
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

    if (typeof window !== 'undefined') {
        window.addEventListener('resize', handleResize);

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