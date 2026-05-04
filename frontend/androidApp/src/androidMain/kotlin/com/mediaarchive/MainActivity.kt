package com.mediaarchive

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.core.view.WindowCompat
import com.mediaarchive.data.SettingsStore

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Initialise SharedPreferences-backed settings store.
        SettingsStore.init(this)

        // Draw edge-to-edge so the Compose UI can consume insets properly.
        WindowCompat.setDecorFitsSystemWindows(window, false)

        setContent { App() }
    }
}
