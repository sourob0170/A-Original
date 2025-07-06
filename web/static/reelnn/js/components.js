/**
 * Reusable components for reelnn frontend
 */

/**
 * API Client for making requests to the backend
 */
class ApiClient {
    constructor() {
        this.baseUrl = '';
        this.defaultHeaders = {
            'Content-Type': 'application/json',
        };
    }

    async request(url, options = {}) {
        const config = {
            headers: { ...this.defaultHeaders, ...options.headers },
            ...options,
        };

        try {
            const response = await fetch(this.baseUrl + url, config);
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const contentType = response.headers.get('content-type');
            if (contentType && contentType.includes('application/json')) {
                return await response.json();
            }
            
            return await response.text();
        } catch (error) {
            console.error('API request failed:', error);
            throw error;
        }
    }

    async get(url, params = {}) {
        const urlParams = new URLSearchParams(params);
        const queryString = urlParams.toString();
        const fullUrl = queryString ? `${url}?${queryString}` : url;
        
        return this.request(fullUrl);
    }

    async post(url, data = {}) {
        return this.request(url, {
            method: 'POST',
            body: JSON.stringify(data),
        });
    }

    async put(url, data = {}) {
        return this.request(url, {
            method: 'PUT',
            body: JSON.stringify(data),
        });
    }

    async delete(url) {
        return this.request(url, {
            method: 'DELETE',
        });
    }
}

/**
 * Search Manager for handling search functionality
 */
class SearchManager {
    constructor() {
        this.searchInput = null;
        this.searchForm = null;
        this.searchResults = null;
        this.currentQuery = '';
        this.searchTimeout = null;
        this.apiClient = new ApiClient();
    }

    init() {
        this.searchInput = document.querySelector('.search-input');
        this.searchForm = document.querySelector('.search-form');
        this.searchResults = document.querySelector('.search-results');

        if (this.searchInput) {
            this.setupSearchInput();
        }

        if (this.searchForm) {
            this.setupSearchForm();
        }

        // Initialize filters
        this.setupFilters();
    }

    setupSearchInput() {
        // Real-time search suggestions (debounced)
        this.searchInput.addEventListener('input', (e) => {
            clearTimeout(this.searchTimeout);
            this.searchTimeout = setTimeout(() => {
                this.handleSearchInput(e.target.value);
            }, 300);
        });

        // Handle keyboard navigation
        this.searchInput.addEventListener('keydown', (e) => {
            this.handleSearchKeydown(e);
        });
    }

    setupSearchForm() {
        this.searchForm.addEventListener('submit', (e) => {
            e.preventDefault();
            this.performSearch();
        });
    }

    setupFilters() {
        const filterSelects = document.querySelectorAll('.filter-select');
        
        filterSelects.forEach(select => {
            select.addEventListener('change', () => {
                this.updateSearchFilters();
            });
        });
    }

    async handleSearchInput(query) {
        if (query.length < 2) {
            this.hideSuggestions();
            return;
        }

        try {
            const suggestions = await this.getSuggestions(query);
            this.showSuggestions(suggestions);
        } catch (error) {
            console.error('Error getting search suggestions:', error);
        }
    }

    async getSuggestions(query) {
        // Mock implementation - replace with actual API call
        return [
            { title: `${query} - Movie`, type: 'movie' },
            { title: `${query} - TV Show`, type: 'show' },
        ];
    }

    showSuggestions(suggestions) {
        // Create or update suggestions dropdown
        let dropdown = document.querySelector('.search-suggestions');
        
        if (!dropdown) {
            dropdown = document.createElement('div');
            dropdown.className = 'search-suggestions';
            dropdown.style.cssText = `
                position: absolute;
                top: 100%;
                left: 0;
                right: 0;
                background: var(--surface-color);
                border: 1px solid var(--border-color);
                border-radius: 0.5rem;
                margin-top: 0.25rem;
                max-height: 300px;
                overflow-y: auto;
                z-index: 1000;
                box-shadow: 0 10px 25px rgba(0, 0, 0, 0.3);
            `;
            
            this.searchInput.parentElement.appendChild(dropdown);
        }

        dropdown.innerHTML = suggestions.map(suggestion => `
            <div class="suggestion-item" style="
                padding: 0.75rem 1rem;
                cursor: pointer;
                border-bottom: 1px solid var(--border-color);
                transition: background 0.2s ease;
            " data-query="${suggestion.title}">
                <div style="font-weight: 500;">${suggestion.title}</div>
                <div style="font-size: 0.875rem; color: var(--text-secondary);">${suggestion.type}</div>
            </div>
        `).join('');

        // Add click handlers
        dropdown.querySelectorAll('.suggestion-item').forEach(item => {
            item.addEventListener('click', () => {
                this.searchInput.value = item.dataset.query;
                this.performSearch();
                this.hideSuggestions();
            });
        });
    }

    hideSuggestions() {
        const dropdown = document.querySelector('.search-suggestions');
        if (dropdown) {
            dropdown.remove();
        }
    }

    handleSearchKeydown(e) {
        const dropdown = document.querySelector('.search-suggestions');
        if (!dropdown) return;

        const items = dropdown.querySelectorAll('.suggestion-item');
        let activeIndex = Array.from(items).findIndex(item => item.classList.contains('active'));

        switch (e.key) {
            case 'ArrowDown':
                e.preventDefault();
                activeIndex = Math.min(activeIndex + 1, items.length - 1);
                this.updateActiveSuggestion(items, activeIndex);
                break;
            case 'ArrowUp':
                e.preventDefault();
                activeIndex = Math.max(activeIndex - 1, 0);
                this.updateActiveSuggestion(items, activeIndex);
                break;
            case 'Enter':
                e.preventDefault();
                if (activeIndex >= 0 && items[activeIndex]) {
                    items[activeIndex].click();
                } else {
                    this.performSearch();
                }
                break;
            case 'Escape':
                this.hideSuggestions();
                break;
        }
    }

    updateActiveSuggestion(items, activeIndex) {
        items.forEach((item, index) => {
            if (index === activeIndex) {
                item.classList.add('active');
                item.style.background = 'var(--primary-color)';
            } else {
                item.classList.remove('active');
                item.style.background = '';
            }
        });
    }

    performSearch() {
        const query = this.searchInput.value.trim();
        if (!query) return;

        const url = new URL('/search', window.location.origin);
        url.searchParams.set('q', query);

        // Add current filters
        const typeFilter = document.querySelector('select[name="type"]');
        const sortFilter = document.querySelector('select[name="sort"]');

        if (typeFilter && typeFilter.value) {
            url.searchParams.set('type', typeFilter.value);
        }

        if (sortFilter && sortFilter.value && sortFilter.value !== 'relevance') {
            url.searchParams.set('sort', sortFilter.value);
        }

        window.location.href = url.toString();
    }

    updateSearchFilters() {
        // Re-perform search with new filters
        this.performSearch();
    }
}

/**
 * Media Player Manager for enhanced video playback
 */
class MediaPlayerManager {
    constructor() {
        this.player = null;
        this.currentMedia = null;
        this.tracks = null;
    }

    async init(videoElement, mediaData) {
        this.currentMedia = mediaData;

        // Initialize ReelNN Player with advanced configuration
        this.player = new ReelNNPlayer(videoElement.parentElement, {
            autoplay: false,
            controls: true,
            quality: 'auto',
            speed: 1,
            volume: 0.8
        });

        this.setupPlayerEvents();
        await this.loadMediaSources();
        await this.loadTracks();
        this.restoreUserPreferences();
    }

    onQualityChange(quality) {
        // Save user preference
        localStorage.setItem('preferred_quality', quality);

        // Track quality changes for analytics
        if (typeof gtag !== 'undefined') {
            gtag('event', 'quality_change', {
                'custom_parameter': quality
            });
        }

        // Update current quality
        this.currentQuality = quality;
    }

    async loadMediaSources() {
        try {
            const response = await fetch(`/api/media/${this.currentMedia.hash_id}/qualities?hash=${this.currentMedia.hash_id.substring(0, 6)}`);
            const qualities = await response.json();

            if (qualities && qualities.length > 0) {
                // Clear existing sources
                const videoElement = this.player.media;
                const existingSources = videoElement.querySelectorAll('source');
                existingSources.forEach(source => source.remove());

                // Add quality sources
                qualities.forEach(quality => {
                    const source = document.createElement('source');
                    source.src = `/api/media/${this.currentMedia.hash_id}/stream?quality=${quality.label}&hash=${this.currentMedia.hash_id.substring(0, 6)}`;
                    source.type = 'video/mp4';
                    source.size = quality.height;
                    source.label = quality.label;
                    videoElement.appendChild(source);
                });

                // Update player quality options
                if (this.player.quality) {
                    this.player.quality.options = qualities.map(q => q.label);
                }
            }
        } catch (error) {
            console.error('Error loading media sources:', error);
        }
    }

    restoreUserPreferences() {
        // Restore saved preferences
        const savedQuality = localStorage.getItem('preferred_quality');
        const savedCaptions = localStorage.getItem('captions_enabled');
        const savedSpeed = localStorage.getItem('playback_speed');
        const savedVolume = localStorage.getItem('volume_level');

        if (savedQuality && this.player.quality) {
            this.player.quality = savedQuality;
        }

        if (savedCaptions === 'true') {
            this.player.captions.enabled = true;
        }

        if (savedSpeed) {
            this.player.speed = parseFloat(savedSpeed);
        }

        if (savedVolume) {
            this.player.volume = parseFloat(savedVolume);
        }
    }

    setupPlayerEvents() {
        // ReelNN Player events are handled internally
        // The player automatically manages loading, progress, quality changes, etc.
        console.log('ReelNN Player events are managed internally');
        this.hideLoadingOverlay();

        // ReelNN Player handles all events internally
    }

    setupKeyboardShortcuts() {
        // ReelNN Player handles keyboard shortcuts internally
        console.log('Keyboard shortcuts are handled by ReelNN Player');
    }

    showLoadingOverlay() {
        const overlay = document.getElementById('loadingOverlay');
        if (overlay) {
            overlay.style.display = 'flex';
        }
    }

    handlePlayerError(error) {
        console.error('Player error details:', error);

        // Try to recover from common errors
        if (error.code === 4) { // MEDIA_ELEMENT_ERROR: Format error
            this.showError('Video format not supported. Trying alternative quality...');
            this.tryAlternativeQuality();
        } else if (error.code === 2) { // MEDIA_ELEMENT_ERROR: Network error
            this.showError('Network error. Please check your connection.');
        } else {
            this.showError('Video playback error. Please try refreshing the page.');
        }
    }

    async tryAlternativeQuality() {
        try {
            const response = await fetch(`/api/media/${this.currentMedia.hash_id}/qualities?hash=${this.currentMedia.hash_id.substring(0, 6)}`);
            const qualities = await response.json();

            if (qualities && qualities.length > 1) {
                // Try the next available quality
                const currentIndex = qualities.findIndex(q => q.label === this.currentQuality);
                const nextQuality = qualities[currentIndex + 1] || qualities[0];

                this.player.source = {
                    type: 'video',
                    sources: [{
                        src: `/api/media/${this.currentMedia.hash_id}/stream?quality=${nextQuality.label}&hash=${this.currentMedia.hash_id.substring(0, 6)}`,
                        type: 'video/mp4',
                        size: nextQuality.height
                    }]
                };
            }
        } catch (error) {
            console.error('Error trying alternative quality:', error);
        }
    }

    hideLoadingOverlay() {
        const overlay = document.getElementById('loadingOverlay');
        if (overlay) {
            overlay.style.display = 'none';
        }
    }

    resumeFromSavedProgress() {
        // ReelNN Player handles progress restoration internally
    }

    saveProgress() {
        // ReelNN Player handles progress saving internally
    }

    handleVideoEnd() {
        // ReelNN Player handles end events internally
    }

    async loadTracks() {
        // ReelNN Player handles track loading internally
        console.log('Track loading is handled by ReelNN Player');
    }

    updateTrackControls() {
        // ReelNN Player handles track controls internally
    }

    updateTrackSelector(containerId, tracks) {
        // ReelNN Player handles track selection internally
    }

    selectTrack(containerId, trackId) {
        // ReelNN Player handles track selection internally
    }

    applyTrackSelection(containerId, trackId) {
        // ReelNN Player handles track application internally
    }

    async loadSubtitleTrack(trackId) {
        // ReelNN Player handles subtitle loading internally
    }

    showError(message) {
        const errorDiv = document.createElement('div');
        errorDiv.style.cssText = `
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            background: rgba(220, 53, 69, 0.9);
            color: white;
            padding: 1rem 2rem;
            border-radius: 0.5rem;
            z-index: 1000;
        `;
        errorDiv.textContent = message;
        
        const container = document.querySelector('.video-container');
        if (container) {
            container.appendChild(errorDiv);
            
            setTimeout(() => {
                errorDiv.remove();
            }, 5000);
        }
    }
}

// Export classes for use in other files
window.ApiClient = ApiClient;
window.SearchManager = SearchManager;
window.MediaPlayerManager = MediaPlayerManager;
