package com.earth.watchface

import androidx.health.services.client.PassiveListenerService
import androidx.health.services.client.data.DataPointContainer
import androidx.health.services.client.data.DataType

class StepsListenerService : PassiveListenerService() {
    override fun onNewDataPointsReceived(dataPoints: DataPointContainer) {
        val stepsData = dataPoints.getData(DataType.STEPS_DAILY)
        for (point in stepsData) {
            EarthWatchFaceService.dataProvider?.updateSteps(point.value.toLong())
        }
    }

    override fun onRegistrationSuccess(dataType: DataType) {}
    override fun onRegistrationFailed(dataType: DataType) {}
}