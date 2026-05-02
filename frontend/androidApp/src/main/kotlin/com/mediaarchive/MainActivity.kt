package com.mediaarchive

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent

// Stub — full Android implementation deferred to the Android commit.
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { App() }
    }
}
