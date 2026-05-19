var Indicators = (function () {
    'use strict';

    var mockData = { weather: 0.5, battery: 0.85, heart: 0.45, stress: 0.25 };

    var syncCycle = 0;

    function normalizeHeartRate(bpm) {
        return Math.max(0, Math.min(1, (bpm - 40) / 160));
    }

    function normalizeStress(level) {
        return Math.max(0, Math.min(1, level / 100));
    }

    function normalizeBattery(level) {
        return Math.max(0, Math.min(1, level / 100));
    }

    function normalizeWeather(temp) {
        return Math.max(0, Math.min(1, (temp + 10) / 50));
    }

    function updateFromSystem() {
        if (typeof tizen !== 'undefined' && tizen.systeminfo) {
            try {
                tizen.systeminfo.getPropertyValue('BATTERY', function (battery) {
                    mockData.battery = normalizeBattery(battery.level);
                    Clock.updateIndicator('battery', {
                        value: mockData.battery,
                        text: Math.round(battery.level) + '%',
                        icon: battery.isCharging ? '⚡' : '🔋'
                    });
                }, function () {});
            } catch (e) {}
        }

        if (typeof tizen !== 'undefined' && tizen.humanactivitymonitor) {
            try {
                tizen.humanactivitymonitor.start('HRM', function (hrmInfo) {
                    mockData.heart = normalizeHeartRate(hrmInfo.heartRate);
                    Clock.updateIndicator('heart', {
                        value: mockData.heart,
                        text: hrmInfo.heartRate + ''
                    });
                });
            } catch (e) {}
        }
    }

    function simulateData() {
        var t = syncCycle * 0.0001;
        mockData.weather = 0.4 + Math.sin(t * 3) * 0.2;
        mockData.battery = Math.max(0.1, 0.85 + Math.sin(t * 1.5) * 0.08);
        mockData.heart = 0.35 + Math.sin(t * 2) * 0.2;
        mockData.stress = 0.2 + Math.sin(t * 1.8) * 0.2;

        var temp = Math.round(20 + mockData.weather * 20);
        Clock.updateIndicator('weather', { value: mockData.weather, text: temp + '°' });
        Clock.updateIndicator('battery', { value: mockData.battery, text: Math.round(mockData.battery * 100) + '%' });
        Clock.updateIndicator('heart', { value: mockData.heart, text: Math.round(60 + mockData.heart * 60) + '' });
        Clock.updateIndicator('stress', { value: mockData.stress, text: mockData.stress < 0.33 ? '低' : mockData.stress < 0.66 ? '中' : '高' });

        syncCycle++;
    }

    function start() {
        updateFromSystem();
        setInterval(simulateData, 5000);
    }

    function stop() {}

    return {
        start: start,
        stop: stop,
        updateFromSystem: updateFromSystem,
        normalizeHeartRate: normalizeHeartRate,
        normalizeStress: normalizeStress,
        normalizeBattery: normalizeBattery,
        normalizeWeather: normalizeWeather
    };
})();