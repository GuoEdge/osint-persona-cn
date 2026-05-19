package com.earth.watchface

import android.content.Context
import androidx.health.services.client.PassiveListenerService
import androidx.health.services.client.data.DataPointContainer
import androidx.health.services.client.data.DataType

class HeartRateListenerService : PassiveListenerService() {
    override fun onNewDataPointsReceived(dataPoints: DataPointContainer) {
        val heartRateData = dataPoints.getData(DataType.HEART_RATE_BPM)
        for (point in heartRateData) {
            EarthWatchFaceService.dataProvider?.updateHeartRate(point.value)
        }
    }

    override fun onRegistrationSuccess(dataType: DataType) {}
    override fun onRegistrationFailed(dataType: DataType) {}
}