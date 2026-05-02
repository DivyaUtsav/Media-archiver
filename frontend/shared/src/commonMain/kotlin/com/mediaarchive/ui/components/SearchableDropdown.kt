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
) {
    Column(modifier = modifier) {
        OutlinedTextField(
            value = query,
            onValueChange = onQueryChange,
            label = { Text(label) },
            modifier = Modifier.fillMaxWidth(),
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
                    items(results) { item ->
                        Text(
                            text = itemLabel(item),
                            modifier = Modifier
                                .fillMaxWidth()
                                .clickable { onSelect(item) }
                                .padding(horizontal = 16.dp, vertical = 10.dp),
                            style = MaterialTheme.typography.bodyMedium,
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
