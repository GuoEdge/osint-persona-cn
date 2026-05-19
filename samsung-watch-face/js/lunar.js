var LunarCalendar = (function () {
    'use strict';

    var Gan = ['甲','乙','丙','丁','戊','己','庚','辛','壬','癸'];
    var Zhi = ['子','丑','寅','卯','辰','巳','午','未','申','酉','戌','亥'];
    var Animals = ['鼠','牛','虎','兔','龙','蛇','马','羊','猴','鸡','狗','猪'];
    var lunarMonths = ['正','二','三','四','五','六','七','八','九','十','冬','腊'];
    var lunarDays = [
        '','初一','初二','初三','初四','初五','初六','初七','初八','初九','初十',
        '十一','十二','十三','十四','十五','十六','十七','十八','十九','二十',
        '廿一','廿二','廿三','廿四','廿五','廿六','廿七','廿八','廿九','三十'
    ];

    var cny = {
        1900:[1,31],1901:[2,19],1902:[2,8],1903:[1,29],1904:[2,16],1905:[2,4],
        1906:[1,25],1907:[2,13],1908:[2,2],1909:[1,22],1910:[2,10],1911:[1,30],
        1912:[2,18],1913:[2,6],1914:[1,26],1915:[2,14],1916:[2,3],1917:[1,23],
        1918:[2,11],1919:[2,1],1920:[2,20],1921:[2,8],1922:[1,28],1923:[2,16],
        1924:[2,5],1925:[1,24],1926:[2,13],1927:[2,2],1928:[1,23],1929:[2,10],
        1930:[1,30],1931:[2,17],1932:[2,6],1933:[1,26],1934:[2,14],1935:[2,4],
        1936:[1,24],1937:[2,11],1938:[1,31],1939:[2,19],1940:[2,8],1941:[1,27],
        1942:[2,15],1943:[2,5],1944:[1,25],1945:[2,13],1946:[2,2],1947:[1,22],
        1948:[2,10],1949:[1,29],1950:[2,17],1951:[2,6],1952:[1,27],1953:[2,14],
        1954:[2,3],1955:[1,24],1956:[2,12],1957:[1,31],1958:[2,18],1959:[2,8],
        1960:[1,28],1961:[2,15],1962:[2,5],1963:[1,25],1964:[2,13],1965:[2,2],
        1966:[1,21],1967:[2,9],1968:[1,30],1969:[2,17],1970:[2,6],1971:[1,27],
        1972:[2,15],1973:[2,3],1974:[1,23],1975:[2,11],1976:[1,31],1977:[2,18],
        1978:[2,7],1979:[1,28],1980:[2,16],1981:[2,5],1982:[1,25],1983:[2,13],
        1984:[2,2],1985:[2,20],1986:[2,9],1987:[1,29],1988:[2,17],1989:[2,6],
        1990:[1,27],1991:[2,15],1992:[2,4],1993:[1,23],1994:[2,10],1995:[1,31],
        1996:[2,19],1997:[2,7],1998:[1,28],1999:[2,16],2000:[2,5],2001:[1,24],
        2002:[2,12],2003:[2,1],2004:[1,22],2005:[2,9],2006:[1,29],2007:[2,18],
        2008:[2,7],2009:[1,26],2010:[2,14],2011:[2,3],2012:[1,23],2013:[2,10],
        2014:[1,31],2015:[2,19],2016:[2,8],2017:[1,28],2018:[2,16],2019:[2,5],
        2020:[1,25],2021:[2,12],2022:[2,1],2023:[1,22],2024:[2,10],2025:[1,29],
        2026:[2,17],2027:[2,6],2028:[1,26],2029:[2,13],2030:[2,3],2031:[1,23],
        2032:[2,11],2033:[1,31],2034:[2,19],2035:[2,8],2036:[1,28],2037:[2,15],
        2038:[2,4],2039:[1,24],2040:[2,12],2041:[2,1],2042:[1,22],2043:[2,10],
        2044:[1,30],2045:[2,17],2046:[2,6],2047:[1,26],2048:[2,14],2049:[2,2],
        2050:[1,23]
    };

    var lunarMonthDays = {
        2025:[29,30,29,29,30,29,30,30,29,30,30,30,29],
        2026:[29,30,30,29,30,29,30,29,30,30,29,30],
        2027:[30,29,30,30,29,30,29,30,29,30,29,30],
        2028:[29,30,29,30,30,29,30,29,30,29,30,29],
        2029:[30,29,30,30,29,30,29,30,30,29,30,30],
        2030:[29,30,29,29,30,29,30,30,30,29,30,30]
    };

    var bigMonth = [29,30,30,30,29,30,29,29,30,29,30,29,30];

    function monthLen(y, m) {
        if (lunarMonthDays[y]) return lunarMonthDays[y][m - 1];
        return (m % 2 === 0) ? 29 : 30;
    }

    function getCNY(year) {
        var y = year;
        while (y >= 1900 && !cny[y]) y--;
        if (!cny[y]) return [1, 1];
        
        var c = cny[y];
        var d = new Date(Date.UTC(y, c[0] - 1, c[1]));
        var diff = (year - y) * 365;
        d.setUTCDate(d.getUTCDate() + diff);
        return [d.getUTCMonth() + 1, d.getUTCDate()];
    }

    function dayDiff(d1, d2) {
        return Math.round((d2.getTime() - d1.getTime()) / 86400000);
    }

    function toBeijingDate(date) {
        var bj = new Date(date.getTime() + 8 * 3600000);
        return {
            year: bj.getUTCFullYear(),
            month: bj.getUTCMonth() + 1,
            day: bj.getUTCDate(),
            hours: bj.getUTCHours(),
            dateObj: new Date(Date.UTC(bj.getUTCFullYear(), bj.getUTCMonth(), bj.getUTCDate()))
        };
    }

    function solarToLunar(date) {
        var bj = toBeijingDate(date);
        var year = bj.year;
        var cnyDate = getCNY(year);
        var cnyObj = new Date(Date.UTC(year, cnyDate[0] - 1, cnyDate[1]));

        var daysFromCNY = dayDiff(cnyObj, bj.dateObj);

        if (daysFromCNY < 0) {
            var prevCNY = getCNY(year - 1);
            cnyObj = new Date(Date.UTC(year - 1, prevCNY[0] - 1, prevCNY[1]));
            daysFromCNY = dayDiff(cnyObj, bj.dateObj);
            year = year - 1;
        }

        var lunarMonth = 1;
        var dayCount = daysFromCNY;

        while (true) {
            var mLen = monthLen(year, lunarMonth);
            if (dayCount < mLen) break;
            dayCount -= mLen;
            lunarMonth++;
            if (lunarMonth > 12) break;
        }

        var lunarDay = dayCount + 1;

        if (lunarMonth > 12) {
            lunarMonth = 12;
            lunarDay = monthLen(year, 12);
        }

        return {
            year: year,
            month: lunarMonth,
            day: lunarDay,
            isLeap: false,
            yearName: Gan[(year - 4) % 10] + Zhi[(year - 4) % 12],
            animal: Animals[(year - 4) % 12],
            monthName: lunarMonths[lunarMonth - 1],
            dayName: lunarDays[Math.min(lunarDay, 30)]
        };
    }

    function getFestival(lunar) {
        if (lunar.month === 1 && lunar.day === 1) return '春节';
        if (lunar.month === 1 && lunar.day === 15) return '元宵节';
        if (lunar.month === 5 && lunar.day === 5) return '端午节';
        if (lunar.month === 7 && lunar.day === 7) return '七夕';
        if (lunar.month === 7 && lunar.day === 15) return '中元节';
        if (lunar.month === 8 && lunar.day === 15) return '中秋节';
        if (lunar.month === 9 && lunar.day === 9) return '重阳节';
        if (lunar.month === 12 && (lunar.day === 30 || lunar.day === 29)) return '除夕';
        return null;
    }

    function formatLunarDate(date) {
        var lunar = solarToLunar(date);
        var festival = getFestival(lunar);
        return festival || (lunar.monthName + '月' + lunar.dayName);
    }

    return {
        solarToLunar: solarToLunar,
        formatLunarDate: formatLunarDate,
        getFestival: getFestival
    };
})();