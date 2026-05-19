var Indicators = (function () {
    'use strict';

    var mock = { weather: 0.5, battery: 0.85, heart: 0.45, stress: 0.25 };
    var cycle = 0;

    function simulateData() {
        var t = cycle * 0.0001;
        mock.battery = Math.max(0.05, 0.85 + Math.sin(t * 1.5) * 0.07);
        mock.weather = 0.4 + Math.sin(t * 3) * 0.2;
        mock.heart = 0.35 + Math.sin(t * 2) * 0.2;
        mock.stress = 0.2 + Math.sin(t * 1.8) * 0.2;

        var temp = Math.round(20 + mock.weather * 20);
        Clock.updateIndicator('battery', { v: mock.battery, label: Math.round(mock.battery * 100) + '%' });
        Clock.updateIndicator('weather', { v: mock.weather, label: temp + '°' });
        Clock.updateIndicator('heart', { v: mock.heart, label: Math.round(60 + mock.heart * 60) + '' });
        Clock.updateIndicator('stress', { v: mock.stress, label: mock.stress < 0.33 ? '低' : mock.stress < 0.66 ? '中' : '高' });

        cycle++;
    }

    function updateFromSystem() {
        if (typeof tizen !== 'undefined' && tizen.systeminfo) {
            try {
                tizen.systeminfo.getPropertyValue('BATTERY', function (b) {
                    mock.battery = b.level / 100;
                    Clock.updateIndicator('battery', { v: mock.battery, label: Math.round(b.level) + '%' });
                }, function () {});
            } catch (e) {}
        }
        if (typeof tizen !== 'undefined' && tizen.humanactivitymonitor) {
            try {
                tizen.humanactivitymonitor.start('HRM', function (hrm) {
                    mock.heart = Math.max(0, Math.min(1, (hrm.heartRate - 40) / 160));
                    Clock.updateIndicator('heart', { v: mock.heart, label: hrm.heartRate + '' });
                });
            } catch (e) {}
        }
    }

    function start() {
        updateFromSystem();
        setInterval(simulateData, 5000);
    }

    function stop() {}

    return { start: start, stop: stop };
})();