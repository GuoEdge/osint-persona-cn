package com.earth.watchface

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.BatteryManager
import androidx.health.services.client.HealthServicesClient
import androidx.health.services.client.data.DataType
import androidx.health.services.client.data.ProtoDuration
import androidx.health.services.client.data.SampleDataPoint
import androidx.health.services.client.request.DataTypeCondition
import androidx.health.services.client.request.PassiveListenerRequest
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.flow.onEach
import kotlinx.coroutines.tasks.await
import com.google.android.gms.wearable.Wearable
import kotlin.math.roundToInt

class DataProvider(private val context: Context) {
    private var _heartRate: Float = 72f
    private var _stress: Float = 25f
    private var _batteryLevel: Float = 0.85f
    private var _batteryCharging: Boolean = false
    private var _weatherTemp: Float = 26f
    private var _weatherCondition: String = "晴"
    private var _weatherIcon: String = "☀"
    private var _steps: Long = 0L

    val heartRate: Float get() = _heartRate
    val stress: Float get() = _stress
    val batteryLevel: Float get() = _batteryLevel
    val batteryCharging: Boolean get() = _batteryCharging
    val weatherTemp: Float get() = _weatherTemp
    val weatherCondition: String get() = _weatherCondition
    val weatherIcon: String get() = _weatherIcon
    val steps: Long get() = _steps

    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private var healthClient: HealthServicesClient? = null

    private val batteryReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            val level = intent?.getIntExtra(BatteryManager.EXTRA_LEVEL, -1) ?: -1
            val scale = intent?.getIntExtra(BatteryManager.EXTRA_SCALE, 100) ?: 100
            val status = intent?.getIntExtra(BatteryManager.EXTRA_STATUS, -1) ?: -1
            if (level >= 0 && scale > 0) {
                _batteryLevel = level.toFloat() / scale.toFloat()
                _batteryCharging = status == BatteryManager.BATTERY_STATUS_CHARGING ||
                    status == BatteryManager.BATTERY_STATUS_FULL
            }
        }
    }

    fun start() {
        context.registerReceiver(batteryReceiver, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
        initHealthServices()
    }

    fun stop() {
        try { context.unregisterReceiver(batteryReceiver) } catch (_: Exception) {}
        scope.cancel()
    }

    private fun initHealthServices() {
        try {
            healthClient = HealthServicesClient.getOrCreate(context)
            scope.launch {
                try {
                    val capabilities = healthClient?.passiveMonitoringClient?.getCapabilitiesAsync()?.await()
                    val supportedTypes = capabilities?.supportedDataTypesPassive ?: emptySet()

                    if (DataType.HEART_RATE_BPM in supportedTypes) {
                        healthClient?.passiveMonitoringClient?.setPassiveListenerService(
                            HeartRateListenerService::class.java
                        )?.await()
                    }

                    if (DataType.STEPS_DAILY in supportedTypes) {
                        healthClient?.passiveMonitoringClient?.setPassiveListenerService(
                            StepsListenerService::class.java
                        )?.await()
                    }
                } catch (e: Exception) {
                    e.printStackTrace()
                }
            }
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }

    fun updateHeartRate(bpm: Float) {
        _heartRate = bpm
    }

    fun updateStress(level: Float) {
        _stress = level
    }

    fun updateSteps(count: Long) {
        _steps = count
    }

    fun updateWeather(temp: Float, condition: String, icon: String) {
        _weatherTemp = temp
        _weatherCondition = condition
        _weatherIcon = icon
    }

    data class IndicatorData(
        val value: Float,
        val text: String
    )

    fun getHeartRateIndicator(): IndicatorData {
        val normalized = ((_heartRate - 40f) / 160f).coerceIn(0f, 1f)
        return IndicatorData(normalized, _heartRate.roundToInt().toString())
    }

    fun getStressIndicator(): IndicatorData {
        val normalized = (_stress / 100f).coerceIn(0f, 1f)
        val text = when {
            _stress < 33f -> "低"
            _stress < 66f -> "中"
            else -> "高"
        }
        return IndicatorData(normalized, text)
    }

    fun getBatteryIndicator(): IndicatorData {
        return IndicatorData(_batteryLevel, "${(_batteryLevel * 100).roundToInt()}%")
    }

    fun getWeatherIndicator(): IndicatorData {
        val normalized = ((_weatherTemp + 10f) / 50f).coerceIn(0f, 1f)
        return IndicatorData(normalized, "${_weatherTemp.roundToInt()}°")
    }
}