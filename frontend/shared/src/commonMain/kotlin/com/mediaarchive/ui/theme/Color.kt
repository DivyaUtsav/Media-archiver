package com.mediaarchive.ui.theme

import androidx.compose.material3.darkColorScheme
import androidx.compose.ui.graphics.Color

val Black900 = Color(0xFF0D0D0D)
val Surface800 = Color(0xFF1A1A1A)
val Surface700 = Color(0xFF242424)
val Surface600 = Color(0xFF2E2E2E)
val OnSurface = Color(0xFFE8E8E8)
val OnSurfaceMuted = Color(0xFF9A9A9A)

val AccentTeal = Color(0xFF4DD9AC)
val AccentTealDim = Color(0xFF2A8A6A)

val RatingSFW = Color(0xFF4CAF84)
val RatingSuggestive = Color(0xFFF5A623)
val RatingNSFW = Color(0xFFE05252)
val RatingNSFWDim = Color(0xFF7A2020)

val ArtTypeArtwork = Color(0xFF6C8EBF)
val ArtTypeCosplay = Color(0xFFBF6C9A)
val ArtTypeAI = Color(0xFFBFAA6C)

val ArchiveColorScheme = darkColorScheme(
    background = Black900,
    surface = Surface800,
    surfaceVariant = Surface700,
    surfaceContainer = Surface600,
    onBackground = OnSurface,
    onSurface = OnSurface,
    onSurfaceVariant = OnSurfaceMuted,
    primary = AccentTeal,
    onPrimary = Black900,
    primaryContainer = AccentTealDim,
    onPrimaryContainer = OnSurface,
    secondary = Surface600,
    onSecondary = OnSurface,
    error = RatingNSFW,
    onError = OnSurface,
    outline = Surface600,
    outlineVariant = Surface700,
)
