package com.mediaarchive.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.unit.dp
import com.mediaarchive.ui.theme.Surface600
import com.mediaarchive.ui.theme.Surface700
import com.mediaarchive.ui.onEscapeKey
import com.mediaarchive.ui.theme.AccentTeal
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester

/**
 * Text field with a live-updated dropdown of results.
 * Used for character/artist search in tag editors.
 */
@Composable
fun <T> SearchableDropdown(
    label: String,
    query: String,
    onQueryChange: (String) -> Unit,
    results: List<T>,
    onSelect: (T) -> Unit,
    itemLabel: (T) -> String,
    modifier: Modifier = Modifier,
    onCreateNew: ((String) -> Unit)? = null,
    highlightedIndex: Int = -1,
    focusRequester: FocusRequester? = null,
) {
    Column(modifier = modifier) {
        OutlinedTextField(
            value = query,
            onValueChange = onQueryChange,
            label = { Text(label) },
            modifier = Modifier.fillMaxWidth()
                .then(if (focusRequester != null) Modifier.focusRequester(focusRequester) else Modifier)
                .onEscapeKey { onQueryChange("") },
            singleLine = true,
        )

        if (results.isNotEmpty() || (onCreateNew != null && query.isNotBlank())) {
            Surface(
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(bottomStart = 8.dp, bottomEnd = 8.dp))
                    .background(Surface700),
                tonalElevation = 4.dp,
            ) {
                LazyColumn(modifier = Modifier.heightIn(max = 200.dp)) {
                    items(results.size) { index ->
                        val item = results[index]
                        val isHighlighted = index == highlightedIndex
                        Text(
                            text = itemLabel(item),
                            modifier = Modifier
                                .fillMaxWidth()
                                .background(if (isHighlighted) AccentTeal.copy(alpha = 0.2f) else Color.Transparent)
                                .clickable { onSelect(item) }
                                .padding(horizontal = 16.dp, vertical = 10.dp),
                            style = MaterialTheme.typography.bodyMedium,
                            color = if (isHighlighted) AccentTeal else MaterialTheme.colorScheme.onSurface,
                        )
                        HorizontalDivider(color = Surface600, thickness = 0.5.dp)
                    }

                    if (onCreateNew != null && query.isNotBlank()) {
                        item {
                            Text(
                                text = "＋ Create \"$query\"",
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .clickable { onCreateNew(query) }
                                    .padding(horizontal = 16.dp, vertical = 10.dp),
                                style = MaterialTheme.typography.bodyMedium,
                                color = MaterialTheme.colorScheme.primary,
                            )
                        }
                    }
                }
            }
        }
    }
}
