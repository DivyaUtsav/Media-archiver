package com.mediaarchive

import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.toRoute
import com.mediaarchive.data.AppContainer
import com.mediaarchive.ui.screens.*
import com.mediaarchive.ui.theme.ArchiveTheme
import com.mediaarchive.viewmodel.ArtworkDetailViewModel
import com.mediaarchive.viewmodel.GalleryViewModel
import com.mediaarchive.viewmodel.ReviewQueueViewModel
import com.mediaarchive.viewmodel.KnowledgeGraphViewModel
import kotlinx.serialization.Serializable

// ── Type-safe route destinations ────────────────────────────────────────────

@Serializable
object GalleryRoute

@Serializable
data class DetailRoute(val artworkId: Int)

@Serializable
object QueueRoute

@Serializable
object SettingsRoute

@Serializable
object KnowledgeGraphRoute

// ── App entry point ──────────────────────────────────────────────────────────

@Composable
fun App() {
    ArchiveTheme {
        val navController = rememberNavController()
        val api = AppContainer.apiClient
        val galleryViewModel = viewModel { GalleryViewModel(api) }

        NavHost(navController = navController, startDestination = GalleryRoute) {

            composable<GalleryRoute> {
                GalleryScreen(
                    viewModel = galleryViewModel,
                    onArtworkClick = { id -> navController.navigate(DetailRoute(id)) },
                    onQueueClick = { navController.navigate(QueueRoute) },
                    onSettingsClick = { navController.navigate(SettingsRoute) },
                    onKnowledgeGraphClick = { navController.navigate(KnowledgeGraphRoute) },
                )
            }

            composable<DetailRoute> { backStack ->
                val route: DetailRoute = backStack.toRoute()
                ArtworkDetailScreen(
                    initialArtworkId = route.artworkId,
                    galleryViewModel = galleryViewModel,
                    onBack = { navController.popBackStack() },
                    onArtistClick = { artistId ->
                        galleryViewModel.updateFilters(com.mediaarchive.viewmodel.GalleryFilters(artistIds = listOf(artistId)))
                        navController.popBackStack()
                    },
                    onSeriesClick = { seriesId ->
                        galleryViewModel.filterBySeries(seriesId)
                        navController.popBackStack()
                    }
                )
            }

            composable<QueueRoute> {
                val vm = viewModel { ReviewQueueViewModel(api) }
                ReviewQueueScreen(viewModel = vm, onBack = { navController.popBackStack() })
            }

            composable<SettingsRoute> {
                SettingsScreen(onBack = { navController.popBackStack() })
            }

            composable<KnowledgeGraphRoute> {
                val vm = viewModel<KnowledgeGraphViewModel> { KnowledgeGraphViewModel(api) }
                KnowledgeGraphScreen(viewModel = vm, onBack = { navController.popBackStack() })
            }
        }
    }
}
