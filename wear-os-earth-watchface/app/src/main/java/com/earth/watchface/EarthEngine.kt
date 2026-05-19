package com.earth.watchface

import android.graphics.*
import kotlin.math.*
import java.util.*

class EarthEngine {
    companion object {
        private const val CHINA_LON = 105.0
        private const val REAL_EARTH_URL = "https://eoimages.gsfc.nasa.gov/images/imagerecords/57000/57723/land_ocean_ice_cloud_2048.jpg"
    }

    private var dayBitmap: Bitmap? = null
    private var nightBitmap: Bitmap? = null
    private var earthBitmap: Bitmap? = null

    data class WakeUpAnim(
        var active: Boolean = false,
        var startTime: Long = 0L,
        val duration: Long = 2500L,
        val totalRotations: Float = 2.0f
    )

    val wakeUpAnim = WakeUpAnim()

    fun triggerWakeUp() {
        wakeUpAnim.active = true
        wakeUpAnim.startTime = System.currentTimeMillis()
    }

    private fun getWakeUpRotation(now: Long): Float {
        if (!wakeUpAnim.active) return 0f
        val elapsed = now - wakeUpAnim.startTime
        if (elapsed >= wakeUpAnim.duration) {
            wakeUpAnim.active = false
            return wakeUpAnim.totalRotations
        }
        val t = elapsed.toFloat() / wakeUpAnim.duration
        val eased = 1f - (1f - t).pow(4)
        return wakeUpAnim.totalRotations * eased
    }

    fun init() {
        createDayTexture()
        createNightTexture()
    }

    private fun createDayTexture() {
        val w = 1024; val h = 512
        dayBitmap = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
        val c = Canvas(dayBitmap!!)
        val p = Paint(Paint.ANTI_ALIAS_FLAG)

        val oceanGrad = LinearGradient(0f, 0f, 0f, h.toFloat(),
            intArrayOf(Color.rgb(10, 61, 104), Color.rgb(13, 84, 144), Color.rgb(21, 110, 184), Color.rgb(13, 84, 144), Color.rgb(10, 61, 104)),
            floatArrayOf(0f, 0.25f, 0.5f, 0.75f, 1f), Shader.TileMode.CLAMP)
        p.shader = oceanGrad
        c.drawRect(0f, 0f, w.toFloat(), h.toFloat(), p)
        p.shader = null

        val rand = Random(123)
        for (i in 0 until 3000) {
            p.color = Color.argb((rand.nextFloat() * 0.06f * 255).toInt(), 15, 80, 160)
            c.drawRect(rand.nextFloat() * w, rand.nextFloat() * h,
                rand.nextFloat() * 6 + 1 + rand.nextFloat() * w * 0.1f,
                rand.nextFloat() * 3 + 0.5f, p)
        }

        val continents = listOf(
            Triple(0.73f, 0.30f) to Pair(0.16f, 0.24f),
            Triple(0.74f, 0.28f) to Pair(0.14f, 0.21f),
            Triple(0.69f, 0.40f) to Pair(0.11f, 0.17f),
            Triple(0.76f, 0.55f) to Pair(0.09f, 0.09f),
            Triple(0.70f, 0.19f) to Pair(0.13f, 0.13f),
            Triple(0.60f, 0.34f) to Pair(0.07f, 0.11f),
            Triple(0.30f, 0.27f) to Pair(0.11f, 0.17f),
            Triple(0.31f, 0.29f) to Pair(0.09f, 0.15f),
            Triple(0.17f, 0.37f) to Pair(0.13f, 0.21f),
            Triple(0.19f, 0.35f) to Pair(0.11f, 0.19f),
            Triple(0.85f, 0.29f) to Pair(0.08f, 0.11f),
            Triple(0.21f, 0.17f) to Pair(0.10f, 0.11f),
            Triple(0.50f, 0.37f) to Pair(0.05f, 0.07f),
            Triple(0.35f, 0.50f) to Pair(0.04f, 0.06f),
            Triple(0.79f, 0.43f) to Pair(0.05f, 0.06f),
            Triple(0.81f, 0.15f) to Pair(0.06f, 0.08f),
            Triple(0.48f, 0.55f) to Pair(0.04f, 0.05f),
            Triple(0.16f, 0.28f) to Pair(0.07f, 0.09f),
            Triple(0.23f, 0.45f) to Pair(0.06f, 0.08f),
            Triple(0.83f, 0.35f) to Pair(0.06f, 0.09f),
            Triple(0.65f, 0.45f) to Pair(0.04f, 0.06f),
        )

        for ((pos, size) in continents) {
            val cx = pos.first * w; val cy = pos.second * h
            val rx = size.first * w; val ry = size.second * h
            c.save(); c.translate(cx, cy)

            p.shader = RadialGradient(0f, 0f, rx,
                intArrayOf(Color.rgb(106, 154, 66), Color.rgb(93, 140, 56),
                    Color.rgb(74, 122, 42), Color.rgb(53, 104, 32), Color.argb(0, 30, 60, 18)),
                floatArrayOf(0f, 0.2f, 0.5f, 0.8f, 1f), Shader.TileMode.CLAMP)
            val oval = RectF(-rx, -ry, rx, ry)
            c.drawOval(oval, p)
            p.shader = null

            for (k in 0 until 15) {
                p.color = Color.argb(77, 90, 140, 55)
                c.drawCircle((rand.nextFloat() - 0.5f) * rx * 1.1f,
                    (rand.nextFloat() - 0.5f) * ry * 1.1f,
                    rand.nextFloat() * rx * 0.25f + rx * 0.04f, p)
            }
            c.restore()
        }
    }

    private fun createNightTexture() {
        val w = 1024; val h = 512
        nightBitmap = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
        val c = Canvas(nightBitmap!!)
        val p = Paint(Paint.ANTI_ALIAS_FLAG)
        c.drawColor(Color.rgb(2, 8, 18))

        val clusters = listOf(
            listOf(0.74f, 0.30f, 60f, 0.9f), listOf(0.75f, 0.32f, 50f, 0.85f),
            listOf(0.73f, 0.29f, 40f, 0.8f), listOf(0.76f, 0.31f, 55f, 0.9f),
            listOf(0.82f, 0.33f, 70f, 0.95f), listOf(0.83f, 0.32f, 55f, 0.9f),
            listOf(0.81f, 0.30f, 60f, 0.92f), listOf(0.80f, 0.34f, 45f, 0.85f),
            listOf(0.68f, 0.36f, 40f, 0.75f), listOf(0.67f, 0.35f, 35f, 0.7f),
            listOf(0.58f, 0.34f, 35f, 0.7f), listOf(0.57f, 0.35f, 30f, 0.65f),
            listOf(0.30f, 0.28f, 45f, 0.8f), listOf(0.31f, 0.30f, 40f, 0.75f),
            listOf(0.29f, 0.32f, 35f, 0.7f), listOf(0.32f, 0.27f, 35f, 0.7f),
            listOf(0.85f, 0.28f, 50f, 0.85f), listOf(0.86f, 0.30f, 35f, 0.75f),
            listOf(0.40f, 0.30f, 30f, 0.7f), listOf(0.34f, 0.29f, 20f, 0.6f),
            listOf(0.20f, 0.32f, 28f, 0.65f), listOf(0.18f, 0.30f, 22f, 0.6f),
        )

        for (cl in clusters) {
            val cx = cl[0] * w; val cy = cl[1] * h; val r = cl[2]; val i = cl[3]
            p.shader = RadialGradient(cx, cy, r * 3,
                intArrayOf(
                    Color.argb((i * 0.5f * 255).toInt(), 255, 200, 100),
                    Color.argb((i * 0.3f * 255).toInt(), 255, 180, 60),
                    Color.argb((i * 0.12f * 255).toInt(), 200, 140, 30),
                    Color.TRANSPARENT
                ), floatArrayOf(0f, 0.25f, 0.5f, 1f), Shader.TileMode.CLAMP)
            c.drawRect(cx - r * 3, cy - r * 3, cx + r * 3, cy + r * 3, p)
        }
        p.shader = null

        val rand = Random(456)
        for (j in 0 until 1000) {
            p.color = Color.argb((rand.nextFloat() * 0.22f * 255 + 5).toInt(), 255, 170, 50)
            c.drawCircle(rand.nextFloat() * w, rand.nextFloat() * h,
                rand.nextFloat() * 2.5f + 0.5f, p)
        }
    }

    private fun getSunAngleRad(): Float {
        val cal = Calendar.getInstance(TimeZone.getTimeZone("Asia/Shanghai"))
        val total = cal.get(Calendar.HOUR_OF_DAY) * 3600 +
                cal.get(Calendar.MINUTE) * 60 + cal.get(Calendar.SECOND)
        return ((total.toFloat() / 86400f) * 360f - 90f) * (PI / 180f).toFloat()
    }

    fun draw(canvas: Canvas, centerX: Float, centerY: Float, watchRadius: Float) {
        val earthRadius = watchRadius * 0.23f
        val earthCX = centerX
        val earthCY = centerY + watchRadius * 0.24f

        val cal = Calendar.getInstance(TimeZone.getTimeZone("Asia/Shanghai"))
        val totalSec = cal.get(Calendar.HOUR_OF_DAY) * 3600 +
                cal.get(Calendar.MINUTE) * 60 + cal.get(Calendar.SECOND)

        val wakeRot = getWakeUpRotation(System.currentTimeMillis())
        val texOffset = ((totalSec.toFloat() / 86400f + (-CHINA_LON.toFloat() / 360f) + wakeRot) % 1f)

        val tex = dayBitmap ?: return

        canvas.save()
        canvas.clipPath(Path().apply { addCircle(earthCX, earthCY, earthRadius, Path.Direction.CW) })

        val texW = tex.width.toFloat()
        val halfW = texW / 2f
        val sx = texOffset * texW

        val srcRect = Rect(sx.toInt(), 0, (sx + halfW).toInt(), tex.height)
        val dstRect = RectF(earthCX - earthRadius, earthCY - earthRadius, earthCX + earthRadius, earthCY + earthRadius)
        canvas.drawBitmap(tex, srcRect, dstRect, null)

        if (sx - texW >= -texW) {
            val srcRect2 = Rect((sx - texW).toInt(), 0, (sx - texW + halfW).toInt(), tex.height)
            canvas.drawBitmap(tex, srcRect2, dstRect, null)
        }

        val sunRad = getSunAngleRad()
        val shadePaint = Paint(Paint.ANTI_ALIAS_FLAG)
        shadePaint.shader = LinearGradient(
            earthCX + cos(sunRad + PI.toFloat() / 2f) * earthRadius,
            earthCY + sin(sunRad + PI.toFloat() / 2f) * earthRadius,
            earthCX + cos(sunRad - PI.toFloat() / 2f) * earthRadius,
            earthCY + sin(sunRad - PI.toFloat() / 2f) * earthRadius,
            intArrayOf(
                Color.argb(184, 0, 0, 0), Color.argb(153, 0, 0, 0),
                Color.argb(51, 0, 0, 0), Color.TRANSPARENT,
                Color.TRANSPARENT, Color.argb(13, 0, 0, 0), Color.argb(26, 0, 0, 0)
            ),
            floatArrayOf(0f, 0.3f, 0.45f, 0.5f, 0.55f, 0.7f, 1f),
            Shader.TileMode.CLAMP
        )
        canvas.drawRect(earthCX - earthRadius, earthCY - earthRadius,
            earthCX + earthRadius, earthCY + earthRadius, shadePaint)

        val nightTex = nightBitmap
        if (nightTex != null) {
            val nightSrc = Rect(sx.toInt(), 0, (sx + halfW).toInt(), nightTex.height)
            val nightDst = RectF(earthCX - earthRadius, earthCY - earthRadius,
                earthCX + earthRadius, earthCY + earthRadius)
            canvas.drawBitmap(nightTex, nightSrc, nightDst, null)

            if (sx - texW >= -texW) {
                val nightSrc2 = Rect((sx - texW).toInt(), 0, (sx - texW + halfW).toInt(), nightTex.height)
                canvas.drawBitmap(nightTex, nightSrc2, nightDst, null)
            }

            val nightPaint = Paint(Paint.ANTI_ALIAS_FLAG)
            nightPaint.shader = LinearGradient(
                earthCX + cos(sunRad + PI.toFloat() / 2f) * earthRadius,
                earthCY + sin(sunRad + PI.toFloat() / 2f) * earthRadius,
                earthCX + cos(sunRad - PI.toFloat() / 2f) * earthRadius,
                earthCY + sin(sunRad - PI.toFloat() / 2f) * earthRadius,
                intArrayOf(
                    Color.TRANSPARENT, Color.TRANSPARENT, Color.TRANSPARENT,
                    Color.argb(64, 0, 0, 0), Color.argb(153, 0, 0, 0),
                    Color.argb(179, 0, 0, 0), Color.argb(191, 0, 0, 0)
                ),
                floatArrayOf(0f, 0.3f, 0.45f, 0.5f, 0.55f, 0.7f, 1f),
                Shader.TileMode.CLAMP
            )
            nightPaint.xfermode = PorterDuffXfermode(PorterDuff.Mode.DST_IN)
            canvas.drawRect(earthCX - earthRadius, earthCY - earthRadius,
                earthCX + earthRadius, earthCY + earthRadius, nightPaint)
        }

        canvas.restore()

        val strokePaint = Paint(Paint.ANTI_ALIAS_FLAG)
        strokePaint.style = Paint.Style.STROKE
        strokePaint.color = Color.argb(64, 100, 150, 220)
        strokePaint.strokeWidth = 1.5f
        canvas.drawCircle(earthCX, earthCY, earthRadius + 1f, strokePaint)
    }

    fun release() {
        dayBitmap?.recycle()
        nightBitmap?.recycle()
        earthBitmap?.recycle()
    }
}