package com.mediaarchive.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable

@Composable
fun ArchiveTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = ArchiveColorScheme,
        typography = ArchiveTypography,
        content = content,
    )
}
