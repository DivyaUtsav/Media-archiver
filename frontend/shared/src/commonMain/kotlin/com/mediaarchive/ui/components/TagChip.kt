package com.mediaarchive.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import com.mediaarchive.ui.theme.*

@Composable
fun TagChip(
    label: String,
    onClick: (() -> Unit)? = null,
    onRemove: (() -> Unit)? = null,
    color: Color = Surface600,
    textColor: Color = OnSurface,
) {
    Row(
        modifier = Modifier
            .clip(RoundedCornerShape(20.dp))
            .background(color)
            .then(if (onClick != null) Modifier.clickable { onClick() } else Modifier)
            .padding(start = 12.dp, end = if (onRemove != null) 4.dp else 12.dp, top = 6.dp, bottom = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        Text(label, style = MaterialTheme.typography.labelMedium, color = textColor)
        if (onRemove != null) {
            IconButton(
                onClick = onRemove,
                modifier = Modifier.size(18.dp),
            ) {
                Icon(Icons.Default.Close, contentDescription = "Remove $label", tint = textColor, modifier = Modifier.size(12.dp))
            }
        }
    }
}

@Composable
fun RatingBadge(rating: String) {
    Box(
        modifier = Modifier
            .clip(RoundedCornerShape(4.dp))
            .background(ratingColor(rating))
            .padding(horizontal = 10.dp, vertical = 4.dp),
    ) {
        Text(rating, style = MaterialTheme.typography.labelMedium, color = Color.White)
    }
}

@Composable
fun ArtTypeBadge(artType: String) {
    Box(
        modifier = Modifier
            .clip(RoundedCornerShape(4.dp))
            .background(artTypeColor(artType))
            .padding(horizontal = 10.dp, vertical = 4.dp),
    ) {
        Text(artType, style = MaterialTheme.typography.labelMedium, color = Color.White)
    }
}

@Composable
fun ConfidenceChip(label: String, confidence: Double?, onClick: (() -> Unit)? = null) {
    val pct = confidence?.let { " ${(it * 100).toInt()}%" } ?: ""
    TagChip(
        label = "$label$pct",
        onClick = onClick,
        color = Surface600.copy(alpha = 0.7f),
        textColor = OnSurfaceMuted,
    )
}
