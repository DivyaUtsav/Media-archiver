package com.mediaarchive

import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Window
import androidx.compose.ui.window.application
import androidx.compose.ui.window.rememberWindowState

fun main() {
    // SOFTWARE rendering bypasses GPU/DirectX init — fixes UnsatisfiedLinkError
    // in RenderNodeContext_nMake on machines with mismatched Skiko native libraries
    // or when running headless/without proper GPU context via Gradle.
    System.setProperty("skiko.renderApi", "SOFTWARE")
    
    application {
        Window(
            onCloseRequest = ::exitApplication,
            title = "Media Archive",
            state = rememberWindowState(width = 1280.dp, height = 800.dp),
        ) {
            App()
        }
    }
}
