package com.earth.watchface

import android.app.PendingIntent
import android.content.ComponentName
import android.content.Intent
import android.graphics.drawable.Icon
import androidx.wear.watchface.*
import androidx.wear.watchface.complications.*
import androidx.wear.watchface.complications.data.*
import androidx.wear.watchface.complications.rendering.*
import androidx.wear.watchface.style.*

class EarthWatchFaceService : WatchFaceService() {

    companion object {
        var dataProvider: DataProvider? = null
    }

    override fun createUserStyleSchema(): UserStyleSchema = UserStyleSchema(emptyList())

    override suspend fun createWatchFace(
        surfaceHolder: android.view.SurfaceHolder,
        watchState: WatchState,
        complicationSlotsManager: ComplicationSlotsManager,
        currentUserStyleRepository: CurrentUserStyleRepository
    ): WatchFace {
        val dp = DataProvider(this)
        dp.start()
        dataProvider = dp

        val renderer = EarthWatchFaceRenderer(
            surfaceHolder, currentUserStyleRepository, watchState, dp
        )

        return WatchFace(
            WatchFaceType.ANALOG,
            renderer
        ).setTapListener { tapType, tapPt, complicationId ->
            renderer.earth.triggerWakeUp()
        }
    }

    override fun onDestroy() {
        dataProvider?.stop()
        dataProvider = null
        super.onDestroy()
    }
}