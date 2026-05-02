package com.mediaarchive.ui.components

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.mediaarchive.ui.theme.OnSurface

/** Segmented radio group for content rating selection. */
@Composable
fun RatingSelector(
    selected: String?,
    onSelected: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    val options = listOf("SFW", "Suggestive", "NSFW")
    Row(modifier = modifier, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        options.forEach { option ->
            FilterChip(
                selected = selected == option,
                onClick = { onSelected(option) },
                label = {
                    Text(
                        option,
                        color = if (selected == option) MaterialTheme.colorScheme.onPrimary else OnSurface,
                        style = MaterialTheme.typography.labelMedium,
                    )
                },
                colors = FilterChipDefaults.filterChipColors(
                    selectedContainerColor = ratingColor(option),
                    selectedLabelColor = MaterialTheme.colorScheme.onPrimary,
                ),
            )
        }
    }
}

/** Segmented radio group for art type selection. */
@Composable
fun ArtTypeSelector(
    selected: String?,
    onSelected: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    val options = listOf("Artwork", "Cosplay", "AI Generated")
    Row(modifier = modifier, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        options.forEach { option ->
            FilterChip(
                selected = selected == option,
                onClick = { onSelected(option) },
                label = {
                    Text(
                        option,
                        color = if (selected == option) MaterialTheme.colorScheme.onPrimary else OnSurface,
                        style = MaterialTheme.typography.labelMedium,
                    )
                },
                colors = FilterChipDefaults.filterChipColors(
                    selectedContainerColor = artTypeColor(option),
                    selectedLabelColor = MaterialTheme.colorScheme.onPrimary,
                ),
            )
        }
    }
}
