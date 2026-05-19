var LunarCalendar = (function () {
    'use strict';

    var lunarInfo = [
        0x04bd8,0x04ae0,0x0a570,0x054d5,0x0d260,0x0d950,0x16554,0x056a0,0x09ad0,0x055d2,
        0x04ae0,0x0a5b6,0x0a4d0,0x0d250,0x1d255,0x0b540,0x0d6a0,0x0ada2,0x095b0,0x14977,
        0x04970,0x0a4b0,0x0b4b5,0x06a50,0x06d40,0x1ab54,0x02b60,0x09570,0x052f2,0x04970,
        0x06566,0x0d4a0,0x0ea50,0x06e95,0x05ad0,0x02b60,0x186e3,0x092e0,0x1c8d7,0x0c950,
        0x0d4a0,0x1d8a6,0x0b550,0x056a0,0x1a5b4,0x025d0,0x092d0,0x0d2b2,0x0a950,0x0b557,
        0x06ca0,0x0b550,0x15355,0x04da0,0x0a5b0,0x14573,0x052b0,0x0a9a8,0x0e950,0x06aa0,
        0x0aea6,0x0ab50,0x04b60,0x0aae4,0x0a570,0x05260,0x0f263,0x0d950,0x05b57,0x056a0,
        0x096d0,0x04dd5,0x04ad0,0x0a4d0,0x0d4d4,0x0d250,0x0d558,0x0b540,0x0b6a0,0x195a6,
        0x095b0,0x049b0,0x0a974,0x0a4b0,0x0b27a,0x06a50,0x06d40,0x0af46,0x0ab60,0x09570,
        0x04af5,0x04970,0x064b0,0x074a3,0x0ea50,0x06b58,0x055c0,0x0ab60,0x096d5,0x092e0,
        0x0c960,0x0d954,0x0d4a0,0x0da50,0x07552,0x056a0,0x0abb7,0x025d0,0x092d0,0x0cab5,
        0x0a950,0x0b4a0,0x0baa4,0x0ad50,0x055d9,0x04ba0,0x0a5b0,0x15176,0x052b0,0x0a930,
        0x07954,0x06aa0,0x0ad50,0x05b52,0x04b60,0x0a6e6,0x0a4e0,0x0d260,0x0ea65,0x0d530,
        0x05aa0,0x076a3,0x096d0,0x04afb,0x04ad0,0x0a4d0,0x1d0b6,0x0d250,0x0d520,0x0dd45,
        0x0b5a0,0x056d0,0x055b2,0x049b0,0x0a577,0x0a4b0,0x0aa50,0x1b255,0x06d20,0x0ada0,
        0x14b63,0x09370,0x049f8,0x04970,0x064b0,0x168a6,0x0ea50,0x06b20,0x1a6c4,0x0aae0,
        0x0a2e0,0x0d2e3,0x0c960,0x0d557,0x0d4a0,0x0da50,0x05d55,0x056a0,0x0a6d0,0x055d4,
        0x052d0,0x0a9b8,0x0a950,0x0b4a0,0x0b6a6,0x0ad50,0x055a0,0x0aba4,0x0a5b0,0x052b0,
        0x0b273,0x06930,0x07337,0x06aa0,0x0ad50,0x14b55,0x04b60,0x0a570,0x054e4,0x0d160,
        0x0e968,0x0d520,0x0daa0,0x16aa6,0x056d0,0x04ae0,0x0a9d4,0x0a2d0,0x0d150,0x0f252,
        0x0d520
    ];

    var Gan = ['甲','乙','丙','丁','戊','己','庚','辛','壬','癸'];
    var Zhi = ['子','丑','寅','卯','辰','巳','午','未','申','酉','戌','亥'];
    var Animals = ['鼠','牛','虎','兔','龙','蛇','马','羊','猴','鸡','狗','猪'];

    var lunarMonths = ['正','二','三','四','五','六','七','八','九','十','冬','腊'];
    var lunarDays = [
        '','初一','初二','初三','初四','初五','初六','初七','初八','初九','初十',
        '十一','十二','十三','十四','十五','十六','十七','十八','十九','二十',
        '廿一','廿二','廿三','廿四','廿五','廿六','廿七','廿八','廿九','三十'
    ];

    var solarTermNames = [
        '小寒','大寒','立春','雨水','惊蛰','春分','清明','谷雨',
        '立夏','小满','芒种','夏至','小暑','大暑','立秋','处暑',
        '白露','秋分','寒露','霜降','立冬','小雪','大雪','冬至'
    ];

    var solarTermInfo = [
        0,21208,42467,63836,85337,107014,128867,150921,
        173149,195551,218072,240693,263343,285989,308563,331033,
        353350,375494,397447,419210,440795,462224,483532,504758
    ];

    var baseYear = 1900;
    var baseDate = new Date(1900, 0, 31);

    function lYearDays(y) {
        var sum = 348;
        for (var i = 0x8000; i > 0x8; i >>= 1) {
            sum += (lunarInfo[y - baseYear] & i) ? 1 : 0;
        }
        return sum + leapDays(y);
    }

    function leapMonth(y) {
        return lunarInfo[y - baseYear] & 0xf;
    }

    function leapDays(y) {
        if (leapMonth(y)) {
            return (lunarInfo[y - baseYear] & 0x10000) ? 30 : 29;
        }
        return 0;
    }

    function monthDays(y, m) {
        return (lunarInfo[y - baseYear] & (0x10000 >> m)) ? 30 : 29;
    }

    function solarToLunar(date) {
        var y = date.getFullYear();
        var m = date.getMonth() + 1;
        var d = date.getDate();

        var offset = 0;
        for (var i = baseYear; i < y; i++) {
            offset += lYearDays(i);
        }

        var leap = leapMonth(y);
        var isLeap = false;

        for (var j = 1; j < m; j++) {
            offset += monthDays(y, j);
        }
        offset += d - 1;

        if (leap > 0 && m > leap) {
            offset += leapDays(y);
        }

        var lunarYear = baseYear;
        var daysInYear = lYearDays(lunarYear);
        while (offset >= daysInYear) {
            offset -= daysInYear;
            lunarYear++;
            daysInYear = lYearDays(lunarYear);
        }

        var lunarMonth = 1;
        var lunarLeap = leapMonth(lunarYear);
        var isLeapMonth = false;
        var daysInMonth = monthDays(lunarYear, lunarMonth);

        while (offset >= daysInMonth) {
            offset -= daysInMonth;
            if (lunarLeap > 0 && lunarMonth === lunarLeap && !isLeapMonth) {
                isLeapMonth = true;
                daysInMonth = leapDays(lunarYear);
            } else {
                isLeapMonth = false;
                lunarMonth++;
                daysInMonth = monthDays(lunarYear, lunarMonth);
            }
        }

        var lunarDay = offset + 1;

        return {
            year: lunarYear,
            month: lunarMonth,
            day: lunarDay,
            isLeap: isLeapMonth,
            yearName: Gan[(lunarYear - 4) % 10] + Zhi[(lunarYear - 4) % 12],
            animal: Animals[(lunarYear - 4) % 12],
            monthName: (isLeapMonth ? '闰' : '') + lunarMonths[lunarMonth - 1],
            dayName: lunarDays[lunarDay]
        };
    }

    function getTerm(y, n) {
        var offDate = new Date((31556925974.7 * (y - baseYear) + solarTermInfo[n] * 60000) + baseDate.getTime());
        return offDate.getUTCDate();
    }

    function formatLunarDate(date) {
        var lunar = solarToLunar(date);
        var monthName = lunar.monthName + '月';
        var dayName = lunar.dayName;

        if (lunar.day === 1) {
            return monthName;
        }

        if (lunar.dayName === '初一') {
            return monthName;
        }

        if (lunar.day === 15) {
            return monthName + '十五';
        }

        return monthName + dayName;
    }

    function getLunarYearName(date) {
        var lunar = solarToLunar(new Date(date.getFullYear(), 0, 1));
        return lunar.yearName + '年';
    }

    function getFestival(lunar) {
        if (lunar.month === 1 && lunar.day === 1) return '春节';
        if (lunar.month === 1 && lunar.day === 15) return '元宵节';
        if (lunar.month === 5 && lunar.day === 5) return '端午节';
        if (lunar.month === 7 && lunar.day === 7) return '七夕';
        if (lunar.month === 7 && lunar.day === 15) return '中元节';
        if (lunar.month === 8 && lunar.day === 15) return '中秋节';
        if (lunar.month === 9 && lunar.day === 9) return '重阳节';
        if (lunar.month === 12 && lunar.day === 30) return '除夕';
        if (lunar.month === 12 && lunar.day === 29) return '除夕';
        return null;
    }

    return {
        solarToLunar: solarToLunar,
        formatLunarDate: formatLunarDate,
        getLunarYearName: getLunarYearName,
        getFestival: getFestival,
        Gan: Gan,
        Zhi: Zhi,
        Animals: Animals
    };
})();