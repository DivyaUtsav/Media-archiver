package com.mediaarchive.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import coil3.compose.AsyncImage
import com.mediaarchive.data.api.ArtworkSummaryDto
import com.mediaarchive.ui.theme.*

import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.combinedClickable
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle

@OptIn(ExperimentalFoundationApi::class)
@Composable
fun ArtworkCard(
    artwork: ArtworkSummaryDto,
    mediaUrl: String,
    onClick: () -> Unit,
    onLongClick: (() -> Unit)? = null,
    isSelected: Boolean = false,
    modifier: Modifier = Modifier,
) {
    Box(
        modifier = modifier
            .clip(RoundedCornerShape(8.dp))
            .combinedClickable(
                onClick = onClick,
                onLongClick = onLongClick
            )
            .background(Surface700)
            .aspectRatio(1f),
    ) {
        AsyncImage(
            model = mediaUrl,
            contentDescription = "Artwork ${artwork.id}",
            contentScale = ContentScale.Crop,
            modifier = Modifier.fillMaxSize(),
        )

        // Content rating badge
        artwork.contentRating?.let { rating ->
            Box(
                modifier = Modifier
                    .align(Alignment.TopEnd)
                    .padding(6.dp)
                    .clip(RoundedCornerShape(4.dp))
                    .background(ratingColor(rating).copy(alpha = 0.85f))
                    .padding(horizontal = 6.dp, vertical = 2.dp),
            ) {
                Text(
                    text = rating,
                    style = MaterialTheme.typography.labelSmall,
                    color = Color.White,
                )
            }
        }

        // Series label (bottom)
        if (artwork.series.isNotEmpty()) {
            Box(
                modifier = Modifier
                    .align(Alignment.BottomStart)
                    .fillMaxWidth()
                    .background(Color.Black.copy(alpha = 0.6f))
                    .padding(horizontal = 8.dp, vertical = 4.dp),
            ) {
                Text(
                    text = artwork.series.joinToString(", ") { it.name },
                    style = MaterialTheme.typography.labelSmall,
                    color = OnSurface,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }

        // Selection overlay
        if (isSelected) {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .background(Color.Black.copy(alpha = 0.4f))
            ) {
                androidx.compose.material3.Icon(
                    Icons.Default.CheckCircle,
                    contentDescription = "Selected",
                    tint = AccentTeal,
                    modifier = Modifier
                        .align(Alignment.TopStart)
                        .padding(8.dp)
                        .size(28.dp)
                )
            }
        }
    }
}

fun ratingColor(rating: String): Color = when (rating) {
    "SFW" -> RatingSFW
    "Suggestive" -> RatingSuggestive
    "NSFW" -> RatingNSFW
    else -> Color.Gray
}

fun artTypeColor(artType: String): Color = when (artType) {
    "Artwork" -> ArtTypeArtwork
    "Cosplay" -> ArtTypeCosplay
    "AI Generated" -> ArtTypeAI
    else -> Color.Gray
}
