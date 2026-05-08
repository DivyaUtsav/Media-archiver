package com.mediaarchive.ui

import androidx.compose.ui.Modifier
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.input.key.KeyEventType
import androidx.compose.ui.input.key.key
import androidx.compose.ui.input.key.onKeyEvent
import androidx.compose.ui.input.key.type

fun Modifier.onEnterKey(action: () -> Unit): Modifier = this.onKeyEvent { event ->
    if (event.type == KeyEventType.KeyUp && event.key == Key.Enter) {
        action()
        true
    } else false
}

fun Modifier.onEscapeKey(action: () -> Unit): Modifier = this.onKeyEvent { event ->
    if (event.type == KeyEventType.KeyUp && event.key == Key.Escape) {
        action()
        true
    } else false
}

fun Modifier.onEnterOrEscape(onEnter: () -> Unit, onEscape: () -> Unit): Modifier = this.onKeyEvent { event ->
    if (event.type == KeyEventType.KeyUp) {
        when (event.key) {
            Key.Enter -> { onEnter(); true }
            Key.Escape -> { onEscape(); true }
            else -> false
        }
    } else false
}