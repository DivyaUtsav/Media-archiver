package com.mediaarchive.ui.components

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.mediaarchive.data.api.ApiClient
import com.mediaarchive.data.api.SourcePlatformDto
import com.mediaarchive.ui.theme.OnSurfaceMuted

/**
 * Loads available publication platforms from the API and renders a
 * single-select dropdown (ExposedDropdownMenuBox).
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SourcePlatformSelector(
    selected: SourcePlatformDto?,
    api: ApiClient,
    onSelected: (SourcePlatformDto?) -> Unit,
    modifier: Modifier = Modifier,
) {
    var platforms by remember { mutableStateOf<List<SourcePlatformDto>>(emptyList()) }
    var expanded by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) {
        runCatching { api.getSourcePlatforms() }.onSuccess { platforms = it.items }
    }

    Column(modifier = modifier, verticalArrangement = Arrangement.spacedBy(4.dp)) {
        ExposedDropdownMenuBox(
            expanded = expanded,
            onExpandedChange = { expanded = !expanded },
        ) {
            OutlinedTextField(
                value = selected?.name ?: "None",
                onValueChange = {},
                readOnly = true,
                label = { Text("Publication Platform") },
                trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = expanded) },
                modifier = Modifier.menuAnchor(MenuAnchorType.PrimaryNotEditable).fillMaxWidth(),
            )
            ExposedDropdownMenu(
                expanded = expanded,
                onDismissRequest = { expanded = false },
            ) {
                DropdownMenuItem(
                    text = { Text("None", color = OnSurfaceMuted) },
                    onClick = { onSelected(null); expanded = false },
                )
                HorizontalDivider()
                platforms.forEach { platform ->
                    DropdownMenuItem(
                        text = { Text(platform.name) },
                        onClick = { onSelected(platform); expanded = false },
                    )
                }
            }
        }
    }
}
