var Indicators = (function () {
    'use strict';

    var indicators = {};
    var mockData = {
        weather: { temp: 26, icon: '☀', condition: '晴' },
        battery: { level: 85, charging: false },
        heartRate: { value: 72, unit: 'bpm' },
        stress: { level: '低', value: 25 }
    };

    var stressLevels = ['低', '中', '高'];
    var weatherIcons = ['☀', '⛅', '☁', '🌧', '⛈', '🌨', '🌫'];

    var animationId;

    function getStressLevel(value) {
        if (value < 33) return stressLevels[0];
        if (value < 66) return stressLevels[1];
        return stressLevels[2];
    }

    function getWeatherIcon(condition) {
        var icons = {
            '晴': '☀',
            '多云': '⛅',
            '阴': '☁',
            '雨': '🌧',
            '雷雨': '⛈',
            '雪': '🌨',
            '雾': '🌫'
        };
        return icons[condition] || '☀';
    }

    function updateAll() {
        var wData = mockData.weather;
        updateIndicator('weather',
            getWeatherIcon(wData.condition),
            wData.temp + '°',
            wData.condition);

        var bData = mockData.battery;
        var batteryIcon = bData.charging ? '⚡' : (bData.level > 80 ? '🔋' : bData.level > 30 ? '🔋' : '🪫');
        updateIndicator('battery',
            batteryIcon,
            bData.level + '%',
            '电量');

        var hData = mockData.heartRate;
        updateIndicator('heart',
            '♥',
            hData.value + '',
            '心率');

        var sData = mockData.stress;
        updateIndicator('stress',
            '🧘',
            getStressLevel(sData.value),
            '压力');
    }

    function updateIndicator(id, icon, value, label) {
        var el = document.getElementById('indicator-' + id);
        if (!el) return;
        var iconEl = el.querySelector('.indicator-icon');
        var valueEl = el.querySelector('.indicator-value');
        var labelEl = el.querySelector('.indicator-label');
        if (iconEl) iconEl.textContent = icon;
        if (valueEl) valueEl.textContent = value;
        if (labelEl) labelEl.textContent = label;
    }

    function simulateData(timestamp) {
        var cycle = Math.sin(timestamp * 0.0001) * 0.5 + 0.5;

        mockData.weather.temp = Math.round(22 + cycle * 10);
        mockData.battery.level = Math.max(10, Math.round(85 + Math.sin(timestamp * 0.00005) * 10));
        mockData.heartRate.value = Math.round(68 + cycle * 16);
        mockData.stress.value = Math.round(20 + cycle * 40);
    }

    function animate(timestamp) {
        simulateData(timestamp);
        updateAll();
        animationId = requestAnimationFrame(animate);
    }

    function start() {
        if (animationId) return;
        animationId = requestAnimationFrame(animate);
    }

    function stop() {
        if (animationId) {
            cancelAnimationFrame(animationId);
            animationId = null;
        }
    }

    function setWeather(temp, condition) {
        mockData.weather.temp = temp;
        mockData.weather.condition = condition;
        mockData.weather.icon = getWeatherIcon(condition);
    }

    function setBattery(level, charging) {
        mockData.battery.level = level;
        mockData.battery.charging = charging;
    }

    function setHeartRate(value) {
        mockData.heartRate.value = value;
    }

    function setStress(value) {
        mockData.stress.value = value;
    }

    return {
        start: start,
        stop: stop,
        setWeather: setWeather,
        setBattery: setBattery,
        setHeartRate: setHeartRate,
        setStress: setStress
    };
})();