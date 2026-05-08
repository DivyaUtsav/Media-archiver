package com.mediaarchive.ui.components

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.mediaarchive.data.api.ApiClient
import com.mediaarchive.data.api.SeriesDto
import kotlinx.coroutines.delay
import com.mediaarchive.ui.onEnterOrEscape

@Composable
fun CreateCharacterDialog(
    initialName: String,
    api: ApiClient,
    onCreate: (String, Int) -> Unit,
    onDismiss: () -> Unit,
) {
    var name by remember { mutableStateOf(initialName) }
    var seriesQuery by remember { mutableStateOf("") }
    var seriesResults by remember { mutableStateOf<List<SeriesDto>>(emptyList()) }
    var selectedSeries by remember { mutableStateOf<SeriesDto?>(null) }
    var showCreateSeriesDialog by remember { mutableStateOf(false) }
    var isCreatingSeries by remember { mutableStateOf(false) }

    LaunchedEffect(seriesQuery) {
        if (seriesQuery.length >= 1) {
            delay(300)
            runCatching { api.getSeries() }.onSuccess {
                seriesResults = it.items.filter { s -> s.name.contains(seriesQuery, ignoreCase = true) }
            }
        } else seriesResults = emptyList()
    }

    if (showCreateSeriesDialog) {
        AlertDialog(
            onDismissRequest = { showCreateSeriesDialog = false },
            title = { Text("Create Series") },
            text = { Text("Create series \"$seriesQuery\"?") },
            confirmButton = {
                Button(
                    onClick = {
                        isCreatingSeries = true
                        showCreateSeriesDialog = false
                    },
                    enabled = !isCreatingSeries,
                ) { Text("Create") }
            },
            dismissButton = {
                OutlinedButton(onClick = { showCreateSeriesDialog = false }) { Text("Cancel") }
            },
        )
    }

    // Series creation side effect
    LaunchedEffect(isCreatingSeries) {
        if (isCreatingSeries) {
            runCatching { api.createSeries(seriesQuery) }.onSuccess { newSeries ->
                selectedSeries = newSeries
                seriesQuery = newSeries.name ?: ""
                seriesResults = emptyList()
            }
            isCreatingSeries = false
        }
    }

    AlertDialog(
        onDismissRequest = onDismiss,
        modifier = Modifier.onEnterOrEscape(
            onEnter = { if (name.isNotBlank() && selectedSeries != null && !isCreatingSeries) onCreate(name, selectedSeries!!.id) },
            onEscape = onDismiss,
        ),
        title = { Text("Create Character") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                OutlinedTextField(
                    value = name,
                    onValueChange = { name = it },
                    label = { Text("Character name") },
                    singleLine = true,
                )
                selectedSeries?.let {
                    Text(
                        "Series: ${it.name}",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.primary,
                    )
                }
                SearchableDropdown(
                    label = "Search series…",
                    query = seriesQuery,
                    onQueryChange = {
                        seriesQuery = it
                        if (selectedSeries != null && it != selectedSeries!!.name) selectedSeries = null
                    },
                    results = seriesResults,
                    onSelect = { s -> selectedSeries = s; seriesQuery = s.name ?: ""; seriesResults = emptyList() },
                    itemLabel = { it.name },
                    onCreateNew = { showCreateSeriesDialog = true },
                )
            }
        },
        confirmButton = {
            Button(
                onClick = { selectedSeries?.let { onCreate(name, it.id) } },
                enabled = name.isNotBlank() && selectedSeries != null && !isCreatingSeries,
            ) { Text("Create") }
        },
        dismissButton = {
            OutlinedButton(onClick = onDismiss) { Text("Cancel") }
        },
    )
}
