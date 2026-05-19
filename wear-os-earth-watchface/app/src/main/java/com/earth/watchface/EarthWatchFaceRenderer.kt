package com.earth.watchface

import android.graphics.*
import android.view.SurfaceHolder
import androidx.wear.watchface.CanvasType
import androidx.wear.watchface.Renderer
import androidx.wear.watchface.WatchState
import androidx.wear.watchface.style.CurrentUserStyleRepository
import java.util.*
import kotlin.math.*

class EarthWatchFaceRenderer(
    surfaceHolder: SurfaceHolder,
    currentUserStyleRepository: CurrentUserStyleRepository,
    watchState: WatchState,
    private val dataProvider: DataProvider
) : Renderer.CanvasRenderer2<EarthWatchFaceRenderer.SharedAssets>(surfaceHolder, currentUserStyleRepository, watchState,
    canvasType = CanvasType.HARDWARE) {

    class SharedAssets

    private val starfield = StarfieldEngine()
    val earth = EarthEngine()
    private var wasAmbient = false

    private var centerX = 0f; private var centerY = 0f; private var watchRadius = 0f

    private val timePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.argb(235, 255, 255, 255)
        textAlign = Paint.Align.CENTER
    }
    private val handPaint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val progressPaint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val tickPaint = Paint(Paint.ANTI_ALIAS_FLAG)

    override suspend fun createSharedAssets(): SharedAssets {
        starfield.prerender(450, 450, 225f, 225f, 220f)
        earth.init()
        return SharedAssets()
    }

    override fun onDestroy() {
        starfield.invalidate()
        earth.release()
    }

    override fun render(canvas: Canvas, bounds: Rect, calendar: Calendar, sharedAssets: SharedAssets) {
        val isAmbient = renderParameters.drawMode == androidx.wear.watchface.RenderParameters.DrawMode.AMBIENT

        centerX = bounds.exactCenterX()
        centerY = bounds.exactCenterY()
        watchRadius = min(bounds.width(), bounds.height()) / 2f - 4f

        if (!isAmbient && wasAmbient) {
            earth.triggerWakeUp()
        }
        wasAmbient = isAmbient

        canvas.drawColor(Color.argb(255, 2, 2, 16))

        starfield.draw(canvas)

        if (!isAmbient) {
            earth.draw(canvas, centerX, centerY, watchRadius)
        }

        drawProgressBars(canvas, isAmbient)
        drawBezel(canvas)
        drawTickMarks(canvas, isAmbient)
        drawHands(canvas, calendar, isAmbient)
    }

    private fun drawProgressBars(canvas: Canvas, isAmbient: Boolean) {
        if (isAmbient) {
            val p = Paint(Paint.ANTI_ALIAS_FLAG)
            p.style = Paint.Style.STROKE
            p.strokeWidth = 3f; p.color = Color.argb(50, 255, 255, 255)
            canvas.drawCircle(centerX, centerY, watchRadius - 6f, p)
            return
        }

        val arcs = listOf(
            ArcData(dataProvider.getWeatherIndicator(), -PI.toFloat() / 2f, 0.35f, Color.rgb(79, 195, 247)),
            ArcData(dataProvider.getBatteryIndicator(), 0f, 0.35f, Color.rgb(102, 187, 106)),
            ArcData(dataProvider.getHeartRateIndicator(), PI.toFloat() / 2f, 0.35f, Color.rgb(239, 83, 80)),
            ArcData(dataProvider.getStressIndicator(), PI.toFloat(), 0.35f, Color.rgb(171, 71, 188))
        )

        for (arc in arcs) {
            drawArcProgress(canvas, arc)
        }
    }

    data class ArcData(val data: DataProvider.IndicatorData, val centerAngle: Float, val span: Float, val color: Int)

    private fun drawArcProgress(canvas: Canvas, arc: ArcData) {
        val outerR = watchRadius - 4f
        val innerR = watchRadius - 10f
        val startAngle = arc.centerAngle - arc.span
        val sweepAngle = arc.span * 2f

        canvas.save()
        val clipPath = Path()
        clipPath.addArc(centerX - watchRadius, centerY - watchRadius,
            centerX + watchRadius, centerY + watchRadius,
            Math.toDegrees(startAngle.toDouble()).toFloat() - 0.5f,
            Math.toDegrees(sweepAngle.toDouble()).toFloat() + 1f)
        clipPath.addArc(centerX - innerR, centerY - innerR,
            centerX + innerR, centerY + innerR,
            Math.toDegrees(startAngle + sweepAngle + 0.01f).toFloat(),
            Math.toDegrees(-sweepAngle - 0.02f).toFloat())
        clipPath.close()
        canvas.clipPath(clipPath)

        progressPaint.style = Paint.Style.FILL
        progressPaint.color = Color.argb(15, 255, 255, 255)
        canvas.drawRect(centerX - watchRadius, centerY - watchRadius,
            centerX + watchRadius, centerY + watchRadius, progressPaint)

        if (arc.data.value > 0.001f) {
            val fillEnd = startAngle + sweepAngle * arc.data.value.coerceIn(0f, 1f)
            progressPaint.color = arc.color
            progressPaint.style = Paint.Style.FILL
            val arcPath = Path()
            arcPath.addArc(centerX - outerR, centerY - outerR, centerX + outerR, centerY + outerR,
                Math.toDegrees(startAngle.toDouble()).toFloat(),
                Math.toDegrees((fillEnd - startAngle).toDouble()).toFloat())
            arcPath.arcTo(centerX - innerR, centerY - innerR, centerX + innerR, centerY + innerR,
                Math.toDegrees(fillEnd.toDouble()).toFloat(),
                Math.toDegrees((startAngle - fillEnd).toDouble()).toFloat(), false)
            arcPath.close()
            canvas.drawPath(arcPath, progressPaint)
        }

        canvas.restore()
    }

    private fun drawBezel(canvas: Canvas) {
        tickPaint.style = Paint.Style.STROKE
        tickPaint.color = Color.argb(64, 120, 150, 220)
        tickPaint.strokeWidth = 2f
        canvas.drawCircle(centerX, centerY, watchRadius, tickPaint)
        tickPaint.color = Color.argb(31, 60, 80, 140)
        tickPaint.strokeWidth = 1f
        canvas.drawCircle(centerX, centerY, watchRadius - 12f, tickPaint)
    }

    private fun drawTickMarks(canvas: Canvas, isAmbient: Boolean) {
        val outerR = watchRadius * 0.88f
        for (i in 0 until 60) {
            val angle = Math.toRadians((i * 6 - 90).toDouble())
            val isHour = i % 5 == 0
            val innerR = if (isHour) watchRadius * 0.78f else watchRadius * 0.83f
            tickPaint.style = Paint.Style.STROKE
            tickPaint.strokeWidth = if (isHour) 2.5f else 1f
            tickPaint.color = if (isAmbient) Color.argb(100, 255, 255, 255)
            else if (isHour) Color.argb(179, 255, 255, 255)
            else Color.argb(115, 200, 210, 240)
            tickPaint.strokeCap = Paint.Cap.ROUND
            canvas.drawLine(
                centerX + cos(angle).toFloat() * innerR, centerY + sin(angle).toFloat() * innerR,
                centerX + cos(angle).toFloat() * outerR, centerY + sin(angle).toFloat() * outerR,
                tickPaint
            )
        }
    }

    private fun drawHands(canvas: Canvas, calendar: Calendar, isAmbient: Boolean) {
        val h = calendar.get(Calendar.HOUR)
        val m = calendar.get(Calendar.MINUTE)
        val s = calendar.get(Calendar.SECOND)
        val ms = calendar.get(Calendar.MILLISECOND)

        val sAngle = ((s + ms / 1000f) / 60f) * PI.toFloat() * 2f - PI.toFloat() / 2f
        val mAngle = ((m + s / 60f) / 60f) * PI.toFloat() * 2f - PI.toFloat() / 2f
        val hAngle = ((h + m / 60f) / 12f) * PI.toFloat() * 2f - PI.toFloat() / 2f

        if (isAmbient) {
            handPaint.style = Paint.Style.STROKE
            handPaint.strokeWidth = 4f; handPaint.color = Color.WHITE
            handPaint.strokeCap = Paint.Cap.ROUND
            drawHandLine(canvas, watchRadius * 0.4f, hAngle, handPaint)
            drawHandLine(canvas, watchRadius * 0.56f, mAngle, handPaint)

            handPaint.strokeWidth = 2f; handPaint.color = Color.argb(128, 255, 255, 255)
            drawHandLine(canvas, watchRadius * 0.75f, sAngle, handPaint)
        } else {
            drawHandFilled(canvas, watchRadius * 0.4f, hAngle, watchRadius * 0.038f,
                Color.rgb(232, 232, 240), Color.rgb(255, 255, 255))
            drawHandFilled(canvas, watchRadius * 0.56f, mAngle, watchRadius * 0.028f,
                Color.rgb(208, 208, 224), Color.rgb(255, 255, 255))
            drawSecondHand(canvas, sAngle)
        }
    }

    private fun drawHandLine(canvas: Canvas, length: Float, angle: Float, paint: Paint) {
        val ex = centerX + cos(angle) * length
        val ey = centerY + sin(angle) * length
        canvas.drawLine(centerX, centerY, ex, ey, paint)
    }

    private fun drawHandFilled(canvas: Canvas, length: Float, angle: Float, width: Float, color: Int, tipColor: Int) {
        canvas.save()
        canvas.rotate(Math.toDegrees(angle.toDouble()).toFloat(), centerX, centerY)

        handPaint.style = Paint.Style.FILL
        handPaint.shader = LinearGradient(centerX, centerY - length, centerX, centerY,
            color, tipColor, Shader.TileMode.CLAMP)

        val path = Path()
        path.moveTo(centerX, centerY + width * 1.5f)
        path.lineTo(centerX - width, centerY)
        path.lineTo(centerX, centerY - length)
        path.lineTo(centerX + width, centerY)
        path.close()
        canvas.drawPath(path, handPaint)

        canvas.restore()
    }

    private fun drawSecondHand(canvas: Canvas, angle: Float) {
        canvas.save()
        canvas.rotate(Math.toDegrees(angle.toDouble()).toFloat(), centerX, centerY)

        handPaint.style = Paint.Style.FILL
        handPaint.color = Color.rgb(255, 68, 68)
        val len = watchRadius * 0.75f
        val path = Path()
        path.moveTo(centerX, centerY + 3f)
        path.lineTo(centerX + 2f, centerY)
        path.lineTo(centerX, centerY - len)
        path.lineTo(centerX - 2f, centerY)
        path.close()
        canvas.drawPath(path, handPaint)

        canvas.drawCircle(centerX, centerY, watchRadius * 0.04f, handPaint)
        handPaint.color = Color.WHITE
        canvas.drawCircle(centerX, centerY, watchRadius * 0.02f, handPaint)

        canvas.restore()
    }
}