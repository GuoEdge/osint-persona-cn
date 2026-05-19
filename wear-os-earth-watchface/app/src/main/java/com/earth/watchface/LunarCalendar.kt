package com.earth.watchface

import java.util.*

object LunarCalendar {
    private val lunarInfo = intArrayOf(
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
    )

    private val gan = arrayOf("甲","乙","丙","丁","戊","己","庚","辛","壬","癸")
    private val zhi = arrayOf("子","丑","寅","卯","辰","巳","午","未","申","酉","戌","亥")
    private val lunarMonths = arrayOf("正","二","三","四","五","六","七","八","九","十","冬","腊")
    private val lunarDays = arrayOf(
        "","初一","初二","初三","初四","初五","初六","初七","初八","初九","初十",
        "十一","十二","十三","十四","十五","十六","十七","十八","十九","二十",
        "廿一","廿二","廿三","廿四","廿五","廿六","廿七","廿八","廿九","三十"
    )

    data class LunarDate(
        val year: Int, val month: Int, val day: Int, val isLeap: Boolean,
        val yearName: String, val monthName: String, val dayName: String
    )

    private fun lYearDays(y: Int): Int {
        var sum = 348
        var i = 0x8000
        while (i > 0x8) {
            if ((lunarInfo[y - 1900] and i) != 0) sum++
            i = i shr 1
        }
        return sum + leapDays(y)
    }

    private fun leapMonth(y: Int): Int = lunarInfo[y - 1900] and 0xf

    private fun leapDays(y: Int): Int =
        if (leapMonth(y) != 0) {
            if ((lunarInfo[y - 1900] and 0x10000) != 0) 30 else 29
        } else 0

    private fun monthDays(y: Int, m: Int): Int =
        if ((lunarInfo[y - 1900] and (0x10000 shr m)) != 0) 30 else 29

    fun solarToLunar(date: Calendar): LunarDate {
        val y = date.get(Calendar.YEAR)
        val m = date.get(Calendar.MONTH) + 1
        val d = date.get(Calendar.DAY_OF_MONTH)

        var offset = 0
        for (i in 1900 until y) offset += lYearDays(i)

        val leap = leapMonth(y)
        var isLeap = false
        for (j in 1 until m) offset += monthDays(y, j)

        offset += d - 1

        var lunarYear = 1900
        while (offset >= lYearDays(lunarYear)) {
            offset -= lYearDays(lunarYear)
            lunarYear++
        }

        var lunarMonth = 1
        val lunarLeap = leapMonth(lunarYear)
        var isLeapMonth = false

        while (offset >= monthDays(lunarYear, lunarMonth)) {
            offset -= monthDays(lunarYear, lunarMonth)
            if (lunarLeap > 0 && lunarMonth == lunarLeap && !isLeapMonth) {
                isLeapMonth = true
                offset -= 0
            } else {
                lunarMonth++
            }
        }

        val lunarDay = offset + 1
        val yearName = gan[(lunarYear - 4) % 10] + zhi[(lunarYear - 4) % 12]

        return LunarDate(
            year = lunarYear, month = lunarMonth, day = lunarDay,
            isLeap = isLeapMonth,
            yearName = yearName,
            monthName = (if (isLeapMonth) "闰" else "") + lunarMonths[lunarMonth - 1],
            dayName = lunarDays[lunarDay]
        )
    }

    fun getFestival(lunar: LunarDate): String? {
        return when {
            lunar.month == 1 && lunar.day == 1 -> "春节"
            lunar.month == 1 && lunar.day == 15 -> "元宵节"
            lunar.month == 5 && lunar.day == 5 -> "端午节"
            lunar.month == 7 && lunar.day == 7 -> "七夕"
            lunar.month == 7 && lunar.day == 15 -> "中元节"
            lunar.month == 8 && lunar.day == 15 -> "中秋节"
            lunar.month == 9 && lunar.day == 9 -> "重阳节"
            lunar.month == 12 && (lunar.day == 30 || lunar.day == 29) -> "除夕"
            else -> null
        }
    }

    fun formatLunarDate(date: Calendar): String {
        val lunar = solarToLunar(date)
        val festival = getFestival(lunar)
        return festival ?: "${lunar.monthName}月${lunar.dayName}"
    }
}