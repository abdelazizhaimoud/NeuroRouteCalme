/**
 * NeuroRoute Calme — Frontend Application
 *
 * Handles map interaction (click to select start/end),
 * API calls to the Flask backend, and route visualization.
 */

// ============================================================
//  State
// ============================================================

const state = {
    step: 1,            // 1 = select start, 2 = select end, 3 = results
    startLatLng: null,
    endLatLng: null,
    startMarker: null,
    endMarker: null,
    routeLayers: {},     // { profileName: L.polyline }
    profileMeta: {},     // from /api/profiles
    routeData: null,     // full API response
};

// ============================================================
//  Map Initialization
// ============================================================

const map = L.map('map', {
    center: [33.5731, -7.6114],
    zoom: 13,
    zoomControl: true,
    attributionControl: true,
});

// Dark tile layer
L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/">CARTO</a>',
    subdomains: 'abcd',
    maxZoom: 19,
}).addTo(map);

// Set crosshair cursor
map.getContainer().classList.add('selecting-mode');

// ============================================================
//  DOM References
// ============================================================

const $instructions = document.getElementById('instructions');
const $instructionText = document.getElementById('instruction-text');
const $coordsDisplay = document.getElementById('coords-display');
const $startCoords = document.getElementById('start-coords');
const $endCoords = document.getElementById('end-coords');
const $loading = document.getElementById('loading');
const $results = document.getElementById('results');
const $routeCards = document.getElementById('route-cards');
const $btnReset = document.getElementById('btn-reset');

const $step1 = document.getElementById('step-1-indicator');
const $step2 = document.getElementById('step-2-indicator');
const $step3 = document.getElementById('step-3-indicator');

// ============================================================
//  Custom Markers
// ============================================================

function createMarkerIcon(type) {
    const label = type === 'start' ? 'A' : 'B';
    const cls = type === 'start' ? 'marker-start marker-pulse' : 'marker-end';
    return L.divIcon({
        className: '',
        html: `<div class="custom-marker ${cls}">${label}</div>`,
        iconSize: [28, 28],
        iconAnchor: [14, 14],
    });
}

// ============================================================
//  Step Management
// ============================================================

function updateStepUI() {
    // Step indicators
    $step1.className = 'step' + (state.step === 1 ? ' active' : ' done');
    $step2.className = 'step' + (state.step === 2 ? ' active' : (state.step > 2 ? ' done' : ''));
    $step3.className = 'step' + (state.step === 3 ? ' active' : '');

    // Instruction text
    if (state.step === 1) {
        $instructionText.innerHTML = 'Cliquez sur la carte pour placer le <strong>point de départ</strong>';
    } else if (state.step === 2) {
        $instructionText.innerHTML = 'Cliquez sur la carte pour placer le <strong>point d\'arrivée</strong>';
    } else {
        $instructionText.innerHTML = '<strong>Itinéraires affichés</strong> — cliquez sur une carte pour mettre en surbrillance';
    }

    // Cursor
    if (state.step <= 2) {
        map.getContainer().classList.add('selecting-mode');
    } else {
        map.getContainer().classList.remove('selecting-mode');
    }
}

function formatCoord(latlng) {
    return `${latlng.lat.toFixed(5)}, ${latlng.lng.toFixed(5)}`;
}

// ============================================================
//  Map Click Handler
// ============================================================

map.on('click', function (e) {
    if (state.step === 1) {
        // Place start marker
        state.startLatLng = e.latlng;
        if (state.startMarker) map.removeLayer(state.startMarker);
        state.startMarker = L.marker(e.latlng, { icon: createMarkerIcon('start') })
            .addTo(map)
            .bindTooltip('Départ', { className: 'dark-tooltip', direction: 'top', offset: [0, -16] });

        $coordsDisplay.style.display = 'block';
        $coordsDisplay.classList.add('fade-in');
        $startCoords.textContent = formatCoord(e.latlng);

        state.step = 2;
        updateStepUI();

    } else if (state.step === 2) {
        // Place end marker
        state.endLatLng = e.latlng;
        if (state.endMarker) map.removeLayer(state.endMarker);
        state.endMarker = L.marker(e.latlng, { icon: createMarkerIcon('end') })
            .addTo(map)
            .bindTooltip('Arrivée', { className: 'dark-tooltip', direction: 'top', offset: [0, -16] });

        $endCoords.textContent = formatCoord(e.latlng);

        state.step = 3;
        updateStepUI();

        // Launch route computation
        computeRoutes();
    }
});

// ============================================================
//  API Call
// ============================================================

async function computeRoutes() {
    $loading.style.display = 'block';
    $loading.classList.add('fade-in');
    $results.style.display = 'none';
    $btnReset.style.display = 'none';

    const body = {
        start_lat: state.startLatLng.lat,
        start_lon: state.startLatLng.lng,
        end_lat: state.endLatLng.lat,
        end_lon: state.endLatLng.lng,
    };

    try {
        const resp = await fetch(API_BASE + '/api/route', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });

        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            throw new Error(err.error || `HTTP ${resp.status}`);
        }

        const data = await resp.json();
        state.routeData = data;
        state.profileMeta = data.profiles || {};

        $loading.style.display = 'none';
        displayResults(data);

    } catch (err) {
        $loading.style.display = 'none';
        showError(err.message);
    }
}

// ============================================================
//  Display Results
// ============================================================

function displayResults(data) {
    // Clear previous routes
    clearRoutes();

    const routes = data.routes;
    const profiles = data.profiles;

    // Find best score
    let bestScore = -1;
    let bestProfile = null;
    for (const [name, route] of Object.entries(routes)) {
        if (!route.error && route.avg_score_calme > bestScore) {
            bestScore = route.avg_score_calme;
            bestProfile = name;
        }
    }

    // Build route cards HTML
    let cardsHtml = '';
    const profileOrder = ['normal', 'equilibre', 'autiste', 'fauteuil_roulant'];

    for (const name of profileOrder) {
        const route = routes[name];
        const meta = profiles[name] || {};
        if (!route || route.error) continue;

        const isBest = name === bestProfile;
        const scoreClass = route.avg_score_calme >= 0.6 ? 'score-high'
                         : route.avg_score_calme >= 0.4 ? 'score-mid'
                         : 'score-low';

        cardsHtml += `
            <div class="route-card fade-in ${isBest ? 'best-score' : ''}"
                 data-profile="${name}"
                 onclick="highlightRoute('${name}')"
                 style="animation-delay: ${profileOrder.indexOf(name) * 0.08}s">
                <div class="route-toggle" onclick="event.stopPropagation(); toggleRoute('${name}')" title="Afficher/Masquer">
                    👁
                </div>
                <div class="route-card-header">
                    <div class="route-profile-name">
                        <span class="route-icon">${meta.icon || '🚶'}</span>
                        <span class="route-label">${meta.label || name}</span>
                    </div>
                    ${isBest ? '<span class="route-badge">★ Plus calme</span>' : ''}
                </div>
                <p class="route-description">${meta.description || ''}</p>
                <div class="route-stats">
                    <div class="stat">
                        <span class="stat-label">Distance</span>
                        <span class="stat-value">${formatDistance(route.total_length_m)}</span>
                    </div>
                    <div class="stat">
                        <span class="stat-label">Temps</span>
                        <span class="stat-value">${route.total_time_min} min</span>
                    </div>
                    <div class="stat">
                        <span class="stat-label">Score calme</span>
                        <span class="stat-value score ${scoreClass}">${route.avg_score_calme.toFixed(3)}</span>
                    </div>
                    <div class="stat">
                        <span class="stat-label">Segments</span>
                        <span class="stat-value">${route.n_edges}</span>
                    </div>
                </div>
            </div>
        `;
    }

    $routeCards.innerHTML = cardsHtml;
    $results.style.display = 'block';
    $results.classList.add('fade-in');
    $btnReset.style.display = 'flex';
    $btnReset.classList.add('fade-in');

    // Draw routes on map
    const profileColors = {
        normal:    '#3498db',
        equilibre: '#f39c12',
        autiste:   '#9b59b6',
        fauteuil_roulant: '#2ecc71',
    };

    const profileWeights = {
        normal:    4,
        equilibre: 4,
        autiste:   5,
        fauteuil_roulant: 5,
    };

    const profileDash = {
        normal:    '10 8',
        equilibre: null,
        autiste:   null,
        fauteuil_roulant: '6 8',
    };

    for (const name of profileOrder) {
        const route = routes[name];
        if (!route || route.error || !route.coords || route.coords.length < 2) continue;

        const polyline = L.polyline(route.coords, {
            color: profileColors[name] || '#ffffff',
            weight: profileWeights[name] || 4,
            opacity: 0.85,
            dashArray: profileDash[name],
            lineCap: 'round',
            lineJoin: 'round',
        }).addTo(map);

        // Tooltip on hover
        const meta = profiles[name] || {};
        polyline.bindTooltip(
            `<strong>${meta.label || name}</strong><br>` +
            `${formatDistance(route.total_length_m)} · ${route.total_time_min} min<br>` +
            `Score calme: ${route.avg_score_calme.toFixed(3)}`,
            { className: 'dark-tooltip', sticky: true }
        );

        state.routeLayers[name] = polyline;
    }

    // Fit map to show all routes
    const allCoords = Object.values(routes)
        .filter(r => r.coords && r.coords.length > 0)
        .flatMap(r => r.coords);

    if (allCoords.length > 0) {
        const bounds = L.latLngBounds(allCoords);
        map.fitBounds(bounds, { padding: [60, 60] });
    }
}

// ============================================================
//  Route Interaction
// ============================================================

function highlightRoute(profileName) {
    // Highlight this route, dim others
    for (const [name, layer] of Object.entries(state.routeLayers)) {
        if (name === profileName) {
            layer.setStyle({ opacity: 1, weight: 7 });
            layer.bringToFront();
        } else {
            layer.setStyle({ opacity: 0.3, weight: 3 });
        }
    }

    // Highlight the card
    document.querySelectorAll('.route-card').forEach(card => {
        card.classList.toggle('active', card.dataset.profile === profileName);
    });

    // Reset after 3 seconds
    clearTimeout(state._highlightTimeout);
    state._highlightTimeout = setTimeout(() => resetHighlight(), 3000);
}

function resetHighlight() {
    const profileWeights = { normal: 4, equilibre: 4, autiste: 5, fauteuil_roulant: 5 };
    for (const [name, layer] of Object.entries(state.routeLayers)) {
        layer.setStyle({ opacity: 0.85, weight: profileWeights[name] || 4 });
    }
    document.querySelectorAll('.route-card').forEach(card => card.classList.remove('active'));
}

function toggleRoute(profileName) {
    const layer = state.routeLayers[profileName];
    if (!layer) return;

    const toggle = document.querySelector(`.route-card[data-profile="${profileName}"] .route-toggle`);
    if (map.hasLayer(layer)) {
        map.removeLayer(layer);
        if (toggle) toggle.classList.add('hidden');
    } else {
        layer.addTo(map);
        if (toggle) toggle.classList.remove('hidden');
    }
}

// ============================================================
//  Helpers
// ============================================================

function formatDistance(meters) {
    if (meters >= 1000) {
        return (meters / 1000).toFixed(1) + ' km';
    }
    return Math.round(meters) + ' m';
}

function clearRoutes() {
    for (const layer of Object.values(state.routeLayers)) {
        map.removeLayer(layer);
    }
    state.routeLayers = {};
}

function showError(message) {
    $routeCards.innerHTML = `
        <div class="card error-card fade-in">
            <p>❌ Erreur : ${message}</p>
        </div>
    `;
    $results.style.display = 'block';
    $btnReset.style.display = 'flex';
    $btnReset.classList.add('fade-in');
}

// ============================================================
//  Reset
// ============================================================

$btnReset.addEventListener('click', function () {
    // Clear markers
    if (state.startMarker) { map.removeLayer(state.startMarker); state.startMarker = null; }
    if (state.endMarker) { map.removeLayer(state.endMarker); state.endMarker = null; }

    // Clear routes
    clearRoutes();

    // Reset state
    state.startLatLng = null;
    state.endLatLng = null;
    state.routeData = null;
    state.step = 1;

    // Reset UI
    $coordsDisplay.style.display = 'none';
    $results.style.display = 'none';
    $loading.style.display = 'none';
    $btnReset.style.display = 'none';
    $routeCards.innerHTML = '';

    updateStepUI();

    // Recenter map
    map.setView([33.5731, -7.6114], 13);
});

// ============================================================
//  Init
// ============================================================

updateStepUI();
