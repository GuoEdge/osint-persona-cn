package com.earth.watchface

import android.graphics.*
import kotlin.math.*

class StarfieldEngine {
    private var starBitmap: Bitmap? = null
    private var lastWidth = 0
    private var lastHeight = 0

    fun prerender(width: Int, height: Int, centerX: Float, centerY: Float, radius: Float) {
        if (starBitmap != null && lastWidth == width && lastHeight == height) return

        lastWidth = width
        lastHeight = height
        starBitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(starBitmap!!)

        val paint = Paint(Paint.ANTI_ALIAS_FLAG)
        canvas.drawColor(Color.rgb(2, 2, 16))

        for (i in 0 until 3) {
            val nx = centerX + sin(i * 2.1f) * radius * 0.35f
            val ny = centerY + cos(i * 1.7f) * radius * 0.35f
            paint.shader = RadialGradient(nx, ny, radius * 0.5f,
                intArrayOf(
                    Color.argb(10, 30, 20, 70),
                    Color.argb(8, 15, 10, 50),
                    Color.argb(8, 40, 15, 60)
                )[i],
                intArrayOf(Color.TRANSPARENT),
                Shader.TileMode.CLAMP
            )
            canvas.drawRect(centerX - radius, centerY - radius, centerX + radius, centerY + radius, paint)
        }
        paint.shader = null

        canvas.save()
        canvas.clipPath(Path().apply { addCircle(centerX, centerY, radius, Path.Direction.CW) })

        val rand = java.util.Random(42)
        for (i in 0 until 300) {
            val a = rand.nextFloat() * PI.toFloat() * 2f
            val d = sqrt(rand.nextFloat().toDouble()).toFloat() * radius * 0.96f
            val sx = centerX + cos(a) * d
            val sy = centerY + sin(a) * d
            val sr = rand.nextFloat() * 1.6f + 0.3f
            val bright = rand.nextFloat() * 0.5f + 0.5f
            val isBlue = rand.nextFloat() < 0.12f

            if (isBlue) {
                paint.color = Color.argb((bright * 0.7f * 255).toInt(), 150, 170, 255)
            } else {
                paint.color = Color.argb((bright * 255).toInt(), 255, 255, 255)
            }
            canvas.drawCircle(sx, sy, sr, paint)
        }

        canvas.restore()
    }

    fun draw(canvas: Canvas) {
        starBitmap?.let { canvas.drawBitmap(it, 0f, 0f, null) }
    }

    fun invalidate() {
        starBitmap?.recycle()
        starBitmap = null
    }
}