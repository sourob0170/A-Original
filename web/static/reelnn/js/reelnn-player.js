/**
 * ReelNN Custom Video Player
 * A lightweight, feature-rich video player with quality selection, tracks, and captions
 */

class ReelNNPlayer {
    constructor(container, options = {}) {
        this.container = container;
        this.video = container.querySelector('video');
        this.options = {
            autoplay: false,
            controls: true,
            quality: 'auto',
            speed: 1,
            volume: 0.8,
            ...options
        };

        this.state = {
            isPlaying: false,
            currentTime: 0,
            duration: 0,
            volume: this.options.volume,
            isMuted: false,
            isFullscreen: false,
            showControls: true,
            isLoading: false,
            playbackRate: this.options.speed,
            quality: this.options.quality,
            availableQualities: [],
            audioTracks: [],
            subtitleTracks: [],
            currentAudioTrack: 0,
            currentSubtitleTrack: -1
        };

        this.controlsTimeout = null;
        this.progressUpdateInterval = null;

        this.init();
    }

    init() {
        this.createControls();
        this.setupEventListeners();
        this.loadMediaInfo();
        this.restoreUserPreferences();
    }

    createControls() {
        const controlsHTML = `
            <div class="reelnn-player-overlay" id="playerOverlay">
                <!-- Loading Indicator -->
                <div class="reelnn-loading" id="loadingIndicator">
                    <div class="reelnn-spinner"></div>
                </div>

                <!-- Center Play Button -->
                <div class="reelnn-center-controls" id="centerControls">
                    <button class="reelnn-play-btn" id="centerPlayBtn">
                        <svg width="80" height="80" viewBox="0 0 24 24" fill="currentColor">
                            <path d="M8 5v14l11-7z"/>
                        </svg>
                    </button>
                </div>

                <!-- Bottom Controls -->
                <div class="reelnn-controls" id="bottomControls">
                    <div class="reelnn-controls-row">
                        <!-- Progress Bar -->
                        <div class="reelnn-progress-container" id="progressContainer">
                            <div class="reelnn-progress-bar" id="progressBar">
                                <div class="reelnn-progress-buffer" id="progressBuffer"></div>
                                <div class="reelnn-progress-played" id="progressPlayed"></div>
                                <div class="reelnn-progress-handle" id="progressHandle"></div>
                            </div>
                        </div>
                    </div>

                    <div class="reelnn-controls-row">
                        <!-- Left Controls -->
                        <div class="reelnn-controls-left">
                            <button class="reelnn-control-btn" id="playPauseBtn">
                                <svg class="reelnn-play-icon" width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
                                    <path d="M8 5v14l11-7z"/>
                                </svg>
                                <svg class="reelnn-pause-icon" width="24" height="24" viewBox="0 0 24 24" fill="currentColor" style="display: none;">
                                    <path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/>
                                </svg>
                            </button>

                            <button class="reelnn-control-btn" id="rewindBtn">
                                <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
                                    <path d="M11.99 5V1l-5 5 5 5V7c3.31 0 6 2.69 6 6s-2.69 6-6 6-6-2.69-6-6h-2c0 4.42 3.58 8 8 8s8-3.58 8-8-3.58-8-8-8z"/>
                                </svg>
                            </button>

                            <button class="reelnn-control-btn" id="forwardBtn">
                                <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
                                    <path d="M12 5V1l5 5-5 5V7c-3.31 0-6 2.69-6 6s2.69 6 6 6 6-2.69 6-6h2c0 4.42-3.58 8-8 8s-8-3.58-8-8 3.58-8 8-8z"/>
                                </svg>
                            </button>

                            <div class="reelnn-volume-container">
                                <button class="reelnn-control-btn" id="volumeBtn">
                                    <svg class="reelnn-volume-icon" width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
                                        <path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"/>
                                    </svg>
                                </button>
                                <div class="reelnn-volume-slider" id="volumeSlider">
                                    <input type="range" min="0" max="1" step="0.1" value="0.8" id="volumeRange">
                                </div>
                            </div>

                            <div class="reelnn-time-display" id="timeDisplay">
                                <span id="currentTime">0:00</span> / <span id="duration">0:00</span>
                            </div>
                        </div>

                        <!-- Right Controls -->
                        <div class="reelnn-controls-right">
                            <button class="reelnn-control-btn" id="captionsBtn">
                                <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
                                    <path d="M19 4H5c-1.11 0-2 .9-2 2v12c0 1.1.89 2 2 2h14c1.11 0 2-.9 2-2V6c0-1.1-.89-2-2-2zm-8 7H9.5v-.5h-2v3h2V13H11v1c0 .55-.45 1-1 1H7c-.55 0-1-.45-1-1v-4c0-.55.45-1 1-1h3c.55 0 1 .45 1 1v1zm7 0h-1.5v-.5h-2v3h2V13H18v1c0 .55-.45 1-1 1h-3c-.55 0-1-.45-1-1v-4c0-.55.45-1 1-1h3c.55 0 1 .45 1 1v1z"/>
                                </svg>
                            </button>

                            <button class="reelnn-control-btn" id="settingsBtn">
                                <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
                                    <path d="M19.14,12.94c0.04-0.3,0.06-0.61,0.06-0.94c0-0.32-0.02-0.64-0.07-0.94l2.03-1.58c0.18-0.14,0.23-0.41,0.12-0.61 l-1.92-3.32c-0.12-0.22-0.37-0.29-0.59-0.22l-2.39,0.96c-0.5-0.38-1.03-0.7-1.62-0.94L14.4,2.81c-0.04-0.24-0.24-0.41-0.48-0.41 h-3.84c-0.24,0-0.43,0.17-0.47,0.41L9.25,5.35C8.66,5.59,8.12,5.92,7.63,6.29L5.24,5.33c-0.22-0.08-0.47,0-0.59,0.22L2.74,8.87 C2.62,9.08,2.66,9.34,2.86,9.48l2.03,1.58C4.84,11.36,4.82,11.69,4.82,12s0.02,0.64,0.07,0.94l-2.03,1.58 c-0.18,0.14-0.23,0.41-0.12,0.61l1.92,3.32c0.12,0.22,0.37,0.29,0.59,0.22l2.39-0.96c0.5,0.38,1.03,0.7,1.62,0.94l0.36,2.54 c0.05,0.24,0.24,0.41,0.48,0.41h3.84c0.24,0,0.44-0.17,0.47-0.41l0.36-2.54c0.59-0.24,1.13-0.56,1.62-0.94l2.39,0.96 c0.22,0.08,0.47,0,0.59-0.22l1.92-3.32c0.12-0.22,0.07-0.47-0.12-0.61L19.14,12.94z M12,15.6c-1.98,0-3.6-1.62-3.6-3.6 s1.62-3.6,3.6-3.6s3.6,1.62,3.6,3.6S13.98,15.6,12,15.6z"/>
                                </svg>
                            </button>

                            <button class="reelnn-control-btn" id="pipBtn">
                                <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
                                    <path d="M19 7h-8v6h8V7zm2-4H3c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h18c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 16H3V5h18v14z"/>
                                </svg>
                            </button>

                            <button class="reelnn-control-btn" id="fullscreenBtn">
                                <svg class="reelnn-fullscreen-enter" width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
                                    <path d="M7 14H5v5h5v-2H7v-3zm-2-4h2V7h3V5H5v5zm12 7h-3v2h5v-5h-2v3zM14 5v2h3v3h2V5h-5z"/>
                                </svg>
                                <svg class="reelnn-fullscreen-exit" width="24" height="24" viewBox="0 0 24 24" fill="currentColor" style="display: none;">
                                    <path d="M5 16h3v3h2v-5H5v2zm3-8H5v2h5V5H8v3zm6 11h2v-3h3v-2h-5v5zm2-11V5h-2v5h5V8h-3z"/>
                                </svg>
                            </button>
                        </div>
                    </div>
                </div>

                <!-- Settings Menu -->
                <div class="reelnn-settings-menu" id="settingsMenu" style="display: none;">
                    <div class="reelnn-settings-content">
                        <div class="reelnn-settings-section">
                            <h4>Quality</h4>
                            <div class="reelnn-quality-options" id="qualityOptions">
                                <!-- Quality options will be populated dynamically -->
                            </div>
                        </div>

                        <div class="reelnn-settings-section">
                            <h4>Speed</h4>
                            <div class="reelnn-speed-options" id="speedOptions">
                                <button class="reelnn-option-btn" data-speed="0.5">0.5x</button>
                                <button class="reelnn-option-btn" data-speed="0.75">0.75x</button>
                                <button class="reelnn-option-btn active" data-speed="1">Normal</button>
                                <button class="reelnn-option-btn" data-speed="1.25">1.25x</button>
                                <button class="reelnn-option-btn" data-speed="1.5">1.5x</button>
                                <button class="reelnn-option-btn" data-speed="2">2x</button>
                            </div>
                        </div>

                        <div class="reelnn-settings-section">
                            <h4>Audio Track</h4>
                            <div class="reelnn-audio-options" id="audioOptions">
                                <!-- Audio track options will be populated dynamically -->
                            </div>
                        </div>

                        <div class="reelnn-settings-section">
                            <h4>Subtitles</h4>
                            <div class="reelnn-subtitle-options" id="subtitleOptions">
                                <!-- Subtitle options will be populated dynamically -->
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;

        this.container.insertAdjacentHTML('beforeend', controlsHTML);
        this.bindControlElements();
    }

    bindControlElements() {
        // Get control elements
        this.elements = {
            overlay: this.container.querySelector('#playerOverlay'),
            loading: this.container.querySelector('#loadingIndicator'),
            centerControls: this.container.querySelector('#centerControls'),
            centerPlayBtn: this.container.querySelector('#centerPlayBtn'),
            bottomControls: this.container.querySelector('#bottomControls'),
            playPauseBtn: this.container.querySelector('#playPauseBtn'),
            rewindBtn: this.container.querySelector('#rewindBtn'),
            forwardBtn: this.container.querySelector('#forwardBtn'),
            volumeBtn: this.container.querySelector('#volumeBtn'),
            volumeSlider: this.container.querySelector('#volumeSlider'),
            volumeRange: this.container.querySelector('#volumeRange'),
            timeDisplay: this.container.querySelector('#timeDisplay'),
            currentTime: this.container.querySelector('#currentTime'),
            duration: this.container.querySelector('#duration'),
            progressContainer: this.container.querySelector('#progressContainer'),
            progressBar: this.container.querySelector('#progressBar'),
            progressBuffer: this.container.querySelector('#progressBuffer'),
            progressPlayed: this.container.querySelector('#progressPlayed'),
            progressHandle: this.container.querySelector('#progressHandle'),
            captionsBtn: this.container.querySelector('#captionsBtn'),
            settingsBtn: this.container.querySelector('#settingsBtn'),
            pipBtn: this.container.querySelector('#pipBtn'),
            fullscreenBtn: this.container.querySelector('#fullscreenBtn'),
            settingsMenu: this.container.querySelector('#settingsMenu'),
            qualityOptions: this.container.querySelector('#qualityOptions'),
            speedOptions: this.container.querySelector('#speedOptions'),
            audioOptions: this.container.querySelector('#audioOptions'),
            subtitleOptions: this.container.querySelector('#subtitleOptions')
        };
    }

    setupEventListeners() {
        // Video events
        this.video.addEventListener('loadstart', () => this.showLoading());
        this.video.addEventListener('loadeddata', () => this.hideLoading());
        this.video.addEventListener('canplay', () => this.hideLoading());
        this.video.addEventListener('waiting', () => this.showLoading());
        this.video.addEventListener('playing', () => this.hideLoading());

        this.video.addEventListener('loadedmetadata', () => {
            this.updateDuration();
            this.restoreProgress();
        });

        this.video.addEventListener('timeupdate', () => {
            this.updateProgress();
            this.saveProgress();
        });

        this.video.addEventListener('play', () => {
            this.state.isPlaying = true;
            this.updatePlayButton();
            this.container.classList.add('playing');
            this.container.classList.remove('paused');
        });

        this.video.addEventListener('pause', () => {
            this.state.isPlaying = false;
            this.updatePlayButton();
            this.container.classList.add('paused');
            this.container.classList.remove('playing');
        });

        this.video.addEventListener('ended', () => {
            this.state.isPlaying = false;
            this.updatePlayButton();
            this.showCenterControls();
        });

        this.video.addEventListener('volumechange', () => {
            this.state.volume = this.video.volume;
            this.state.isMuted = this.video.muted;
            this.updateVolumeDisplay();
        });

        // Control events
        this.elements.centerPlayBtn.addEventListener('click', () => this.togglePlay());
        this.elements.playPauseBtn.addEventListener('click', () => this.togglePlay());
        this.elements.rewindBtn.addEventListener('click', () => this.seek(-10));
        this.elements.forwardBtn.addEventListener('click', () => this.seek(10));
        this.elements.volumeBtn.addEventListener('click', () => this.toggleMute());
        this.elements.volumeRange.addEventListener('input', (e) => this.setVolume(e.target.value));
        this.elements.fullscreenBtn.addEventListener('click', () => this.toggleFullscreen());
        this.elements.settingsBtn.addEventListener('click', () => this.toggleSettings());
        this.elements.captionsBtn.addEventListener('click', () => this.toggleCaptions());
        this.elements.pipBtn.addEventListener('click', () => this.togglePictureInPicture());

        // Progress bar events
        this.elements.progressContainer.addEventListener('click', (e) => this.seekToPosition(e));
        this.elements.progressHandle.addEventListener('mousedown', (e) => this.startProgressDrag(e));

        // Settings menu events
        this.elements.speedOptions.addEventListener('click', (e) => {
            if (e.target.dataset.speed) {
                this.setPlaybackRate(parseFloat(e.target.dataset.speed));
            }
        });

        // Keyboard events
        document.addEventListener('keydown', (e) => this.handleKeyboard(e));

        // Mouse events for controls visibility
        this.container.addEventListener('mousemove', () => this.showControls());
        this.container.addEventListener('mouseleave', () => this.hideControlsDelayed());

        // Touch events for mobile
        this.setupTouchEvents();

        // Fullscreen events
        document.addEventListener('fullscreenchange', () => this.handleFullscreenChange());
        document.addEventListener('webkitfullscreenchange', () => this.handleFullscreenChange());
        document.addEventListener('mozfullscreenchange', () => this.handleFullscreenChange());
        document.addEventListener('MSFullscreenChange', () => this.handleFullscreenChange());
    }

    setupTouchEvents() {
        let touchStartX = 0;
        let touchStartY = 0;
        let touchStartTime = 0;

        this.container.addEventListener('touchstart', (e) => {
            touchStartX = e.touches[0].clientX;
            touchStartY = e.touches[0].clientY;
            touchStartTime = this.video.currentTime;
        });

        this.container.addEventListener('touchmove', (e) => {
            if (e.touches.length !== 1) return;

            const touchX = e.touches[0].clientX;
            const touchY = e.touches[0].clientY;
            const deltaX = touchX - touchStartX;
            const deltaY = touchY - touchStartY;

            // Horizontal swipe for seeking
            if (Math.abs(deltaX) > Math.abs(deltaY) && Math.abs(deltaX) > 50) {
                e.preventDefault();
                const seekAmount = (deltaX / this.container.offsetWidth) * 30; // 30 seconds max
                const newTime = Math.max(0, Math.min(this.video.duration, touchStartTime + seekAmount));
                this.video.currentTime = newTime;
            }

            // Vertical swipe for volume (right side) or brightness (left side)
            if (Math.abs(deltaY) > Math.abs(deltaX) && Math.abs(deltaY) > 50) {
                e.preventDefault();
                if (touchStartX > this.container.offsetWidth / 2) {
                    // Right side - volume control
                    const volumeChange = -(deltaY / this.container.offsetHeight);
                    const newVolume = Math.max(0, Math.min(1, this.state.volume + volumeChange));
                    this.setVolume(newVolume);
                }
            }
        });
    }

    // Core playback methods
    togglePlay() {
        if (this.video.paused) {
            this.video.play();
        } else {
            this.video.pause();
        }
    }

    seek(seconds) {
        const newTime = Math.max(0, Math.min(this.video.duration, this.video.currentTime + seconds));
        this.video.currentTime = newTime;
    }

    setVolume(volume) {
        this.video.volume = Math.max(0, Math.min(1, volume));
        this.elements.volumeRange.value = this.video.volume;
        localStorage.setItem('reelnn_volume', this.video.volume);
    }

    toggleMute() {
        this.video.muted = !this.video.muted;
        localStorage.setItem('reelnn_muted', this.video.muted);
    }

    setPlaybackRate(rate) {
        this.video.playbackRate = rate;
        this.state.playbackRate = rate;

        // Update active speed button
        this.elements.speedOptions.querySelectorAll('.reelnn-option-btn').forEach(btn => {
            btn.classList.remove('active');
            if (parseFloat(btn.dataset.speed) === rate) {
                btn.classList.add('active');
            }
        });

        localStorage.setItem('reelnn_speed', rate);
    }

    toggleFullscreen() {
        if (!document.fullscreenElement) {
            this.container.requestFullscreen().catch(err => {
                console.log('Error attempting to enable fullscreen:', err);
            });
        } else {
            document.exitFullscreen();
        }
    }

    toggleSettings() {
        const isVisible = this.elements.settingsMenu.style.display !== 'none';
        this.elements.settingsMenu.style.display = isVisible ? 'none' : 'block';
    }

    toggleCaptions() {
        const tracks = this.video.textTracks;
        if (tracks.length > 0) {
            const track = tracks[0];
            track.mode = track.mode === 'showing' ? 'hidden' : 'showing';
            this.elements.captionsBtn.classList.toggle('active', track.mode === 'showing');
        }
    }

    togglePictureInPicture() {
        if (document.pictureInPictureElement) {
            document.exitPictureInPicture();
        } else if (document.pictureInPictureEnabled) {
            this.video.requestPictureInPicture();
        }
    }

    // UI update methods
    updatePlayButton() {
        const playIcon = this.elements.playPauseBtn.querySelector('.reelnn-play-icon');
        const pauseIcon = this.elements.playPauseBtn.querySelector('.reelnn-pause-icon');

        if (this.state.isPlaying) {
            playIcon.style.display = 'none';
            pauseIcon.style.display = 'block';
            this.hideCenterControls();
        } else {
            playIcon.style.display = 'block';
            pauseIcon.style.display = 'none';
            this.showCenterControls();
        }
    }

    updateProgress() {
        if (this.video.duration) {
            const progress = (this.video.currentTime / this.video.duration) * 100;
            this.elements.progressPlayed.style.width = `${progress}%`;
            this.elements.progressHandle.style.left = `${progress}%`;

            // Update buffer progress
            if (this.video.buffered.length > 0) {
                const buffered = (this.video.buffered.end(this.video.buffered.length - 1) / this.video.duration) * 100;
                this.elements.progressBuffer.style.width = `${buffered}%`;
            }
        }

        this.updateTimeDisplay();
    }

    updateTimeDisplay() {
        this.elements.currentTime.textContent = this.formatTime(this.video.currentTime);
        this.elements.duration.textContent = this.formatTime(this.video.duration || 0);
    }

    updateDuration() {
        this.state.duration = this.video.duration;
        this.updateTimeDisplay();
    }

    updateVolumeDisplay() {
        const volumeIcon = this.elements.volumeBtn.querySelector('.reelnn-volume-icon');
        this.elements.volumeRange.value = this.video.volume;

        // Update volume icon based on level
        if (this.video.muted || this.video.volume === 0) {
            volumeIcon.innerHTML = '<path d="M16.5 12c0-1.77-1.02-3.29-2.5-4.03v2.21l2.45 2.45c.03-.2.05-.41.05-.63zm2.5 0c0 .94-.2 1.82-.54 2.64l1.51 1.51C20.63 14.91 21 13.5 21 12c0-4.28-2.99-7.86-7-8.77v2.06c2.89.86 5 3.54 5 6.71zM4.27 3L3 4.27 7.73 9H3v6h4l5 5v-6.73l4.25 4.25c-.67.52-1.42.93-2.25 1.18v2.06c1.38-.31 2.63-.95 3.69-1.81L19.73 21 21 19.73l-9-9L4.27 3zM12 4L9.91 6.09 12 8.18V4z"/>';
        } else if (this.video.volume < 0.5) {
            volumeIcon.innerHTML = '<path d="M18.5 12c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM5 9v6h4l5 5V4L9 9H5z"/>';
        } else {
            volumeIcon.innerHTML = '<path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"/>';
        }
    }

    // Controls visibility
    showControls() {
        this.state.showControls = true;
        this.elements.bottomControls.style.opacity = '1';
        this.container.style.cursor = 'default';

        clearTimeout(this.controlsTimeout);
        this.hideControlsDelayed();
    }

    hideControlsDelayed() {
        clearTimeout(this.controlsTimeout);
        this.controlsTimeout = setTimeout(() => {
            if (this.state.isPlaying && !this.elements.settingsMenu.style.display !== 'none') {
                this.hideControls();
            }
        }, 3000);
    }

    hideControls() {
        this.state.showControls = false;
        this.elements.bottomControls.style.opacity = '0';
        this.container.style.cursor = 'none';
    }

    showCenterControls() {
        this.elements.centerControls.style.opacity = '1';
    }

    hideCenterControls() {
        this.elements.centerControls.style.opacity = '0';
    }

    showLoading() {
        this.state.isLoading = true;
        this.elements.loading.style.display = 'flex';
    }

    hideLoading() {
        this.state.isLoading = false;
        this.elements.loading.style.display = 'none';
    }

    // Utility methods
    formatTime(seconds) {
        if (isNaN(seconds)) return '0:00';

        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = Math.floor(seconds % 60);

        if (hours > 0) {
            return `${hours}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
        } else {
            return `${minutes}:${secs.toString().padStart(2, '0')}`;
        }
    }

    // Media loading and quality management
    async loadMediaInfo() {
        try {
            const hashId = this.getHashIdFromUrl();
            if (!hashId) return;

            // Load available qualities
            const qualities = await this.loadQualities(hashId);
            this.populateQualityOptions(qualities);

            // Load audio and subtitle tracks
            const tracks = await this.loadTracks(hashId);
            this.populateTrackOptions(tracks);

        } catch (error) {
            console.error('Error loading media info:', error);
        }
    }

    async loadQualities(hashId) {
        try {
            const response = await fetch(`/api/media/${hashId}/qualities?hash=${hashId.substring(0, 6)}`);
            if (response.ok) {
                return await response.json();
            }
        } catch (error) {
            console.error('Error loading qualities:', error);
        }

        // Default qualities
        return [
            { label: 'Auto', value: 'auto' },
            { label: '1080p', value: '1080p' },
            { label: '720p', value: '720p' },
            { label: '480p', value: '480p' },
            { label: '360p', value: '360p' }
        ];
    }

    async loadTracks(hashId) {
        try {
            const response = await fetch(`/api/media/${hashId}/tracks?hash=${hashId.substring(0, 6)}`);
            if (response.ok) {
                return await response.json();
            }
        } catch (error) {
            console.error('Error loading tracks:', error);
        }

        return {
            audio: [],
            subtitles: []
        };
    }

    populateQualityOptions(qualities) {
        this.state.availableQualities = qualities;
        this.elements.qualityOptions.innerHTML = '';

        qualities.forEach((quality, index) => {
            const button = document.createElement('button');
            button.className = 'reelnn-option-btn';
            button.dataset.quality = quality.value;
            button.textContent = quality.label;

            if (quality.value === this.state.quality || (index === 0 && this.state.quality === 'auto')) {
                button.classList.add('active');
            }

            button.addEventListener('click', () => this.changeQuality(quality.value));
            this.elements.qualityOptions.appendChild(button);
        });
    }

    populateTrackOptions(tracks) {
        // Populate audio tracks
        this.state.audioTracks = tracks.audio || [];
        this.elements.audioOptions.innerHTML = '';

        if (this.state.audioTracks.length > 0) {
            this.state.audioTracks.forEach((track, index) => {
                const button = document.createElement('button');
                button.className = 'reelnn-option-btn';
                button.dataset.track = index;
                button.textContent = track.title || `Audio ${index + 1}`;

                if (index === this.state.currentAudioTrack) {
                    button.classList.add('active');
                }

                button.addEventListener('click', () => this.changeAudioTrack(index));
                this.elements.audioOptions.appendChild(button);
            });
        } else {
            this.elements.audioOptions.innerHTML = '<span class="reelnn-no-options">No audio tracks available</span>';
        }

        // Populate subtitle tracks
        this.state.subtitleTracks = tracks.subtitles || [];
        this.elements.subtitleOptions.innerHTML = '';

        // Add "Off" option
        const offButton = document.createElement('button');
        offButton.className = 'reelnn-option-btn';
        offButton.dataset.track = '-1';
        offButton.textContent = 'Off';
        if (this.state.currentSubtitleTrack === -1) {
            offButton.classList.add('active');
        }
        offButton.addEventListener('click', () => this.changeSubtitleTrack(-1));
        this.elements.subtitleOptions.appendChild(offButton);

        if (this.state.subtitleTracks.length > 0) {
            this.state.subtitleTracks.forEach((track, index) => {
                const button = document.createElement('button');
                button.className = 'reelnn-option-btn';
                button.dataset.track = index;
                button.textContent = track.title || `Subtitle ${index + 1}`;

                if (index === this.state.currentSubtitleTrack) {
                    button.classList.add('active');
                }

                button.addEventListener('click', () => this.changeSubtitleTrack(index));
                this.elements.subtitleOptions.appendChild(button);
            });
        }
    }

    changeQuality(quality) {
        const currentTime = this.video.currentTime;
        const wasPlaying = !this.video.paused;

        this.state.quality = quality;

        // Update video source
        const hashId = this.getHashIdFromUrl();
        const newSrc = `/api/media/${hashId}/stream?quality=${quality}&hash=${hashId.substring(0, 6)}`;
        this.video.src = newSrc;

        this.video.addEventListener('loadeddata', () => {
            this.video.currentTime = currentTime;
            if (wasPlaying) this.video.play();
        }, { once: true });

        // Update active quality button
        this.elements.qualityOptions.querySelectorAll('.reelnn-option-btn').forEach(btn => {
            btn.classList.remove('active');
            if (btn.dataset.quality === quality) {
                btn.classList.add('active');
            }
        });

        localStorage.setItem('reelnn_quality', quality);
    }

    changeAudioTrack(trackIndex) {
        this.state.currentAudioTrack = trackIndex;

        // Update active audio track button
        this.elements.audioOptions.querySelectorAll('.reelnn-option-btn').forEach(btn => {
            btn.classList.remove('active');
            if (parseInt(btn.dataset.track) === trackIndex) {
                btn.classList.add('active');
            }
        });

        // Note: Actual audio track switching would require server-side support
        console.log('Audio track changed to:', trackIndex);
    }

    changeSubtitleTrack(trackIndex) {
        this.state.currentSubtitleTrack = trackIndex;

        // Update active subtitle track button
        this.elements.subtitleOptions.querySelectorAll('.reelnn-option-btn').forEach(btn => {
            btn.classList.remove('active');
            if (parseInt(btn.dataset.track) === trackIndex) {
                btn.classList.add('active');
            }
        });

        // Handle subtitle display
        const tracks = this.video.textTracks;
        for (let i = 0; i < tracks.length; i++) {
            tracks[i].mode = i === trackIndex ? 'showing' : 'hidden';
        }

        this.elements.captionsBtn.classList.toggle('active', trackIndex !== -1);
    }

    // Event handlers
    handleKeyboard(e) {
        if (e.target.tagName === 'INPUT') return;

        switch (e.code) {
            case 'Space':
                e.preventDefault();
                this.togglePlay();
                break;
            case 'ArrowLeft':
                e.preventDefault();
                this.seek(-10);
                break;
            case 'ArrowRight':
                e.preventDefault();
                this.seek(10);
                break;
            case 'ArrowUp':
                e.preventDefault();
                this.setVolume(Math.min(1, this.video.volume + 0.1));
                break;
            case 'ArrowDown':
                e.preventDefault();
                this.setVolume(Math.max(0, this.video.volume - 0.1));
                break;
            case 'KeyM':
                e.preventDefault();
                this.toggleMute();
                break;
            case 'KeyF':
                e.preventDefault();
                this.toggleFullscreen();
                break;
            case 'Escape':
                if (this.elements.settingsMenu.style.display !== 'none') {
                    this.toggleSettings();
                }
                break;
        }
    }

    seekToPosition(e) {
        const rect = this.elements.progressContainer.getBoundingClientRect();
        const pos = (e.clientX - rect.left) / rect.width;
        const newTime = pos * this.video.duration;
        this.video.currentTime = Math.max(0, Math.min(this.video.duration, newTime));
    }

    startProgressDrag(e) {
        e.preventDefault();
        const rect = this.elements.progressContainer.getBoundingClientRect();

        const handleMouseMove = (e) => {
            const pos = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
            const newTime = pos * this.video.duration;
            this.video.currentTime = newTime;
        };

        const handleMouseUp = () => {
            document.removeEventListener('mousemove', handleMouseMove);
            document.removeEventListener('mouseup', handleMouseUp);
        };

        document.addEventListener('mousemove', handleMouseMove);
        document.addEventListener('mouseup', handleMouseUp);
    }

    handleFullscreenChange() {
        this.state.isFullscreen = !!document.fullscreenElement;

        const enterIcon = this.elements.fullscreenBtn.querySelector('.reelnn-fullscreen-enter');
        const exitIcon = this.elements.fullscreenBtn.querySelector('.reelnn-fullscreen-exit');

        if (this.state.isFullscreen) {
            enterIcon.style.display = 'none';
            exitIcon.style.display = 'block';
            this.container.classList.add('reelnn-fullscreen');
        } else {
            enterIcon.style.display = 'block';
            exitIcon.style.display = 'none';
            this.container.classList.remove('reelnn-fullscreen');
        }
    }

    // User preferences
    restoreUserPreferences() {
        // Restore volume
        const savedVolume = localStorage.getItem('reelnn_volume');
        if (savedVolume !== null) {
            this.setVolume(parseFloat(savedVolume));
        }

        // Restore mute state
        const savedMuted = localStorage.getItem('reelnn_muted');
        if (savedMuted !== null) {
            this.video.muted = savedMuted === 'true';
        }

        // Restore playback speed
        const savedSpeed = localStorage.getItem('reelnn_speed');
        if (savedSpeed !== null) {
            this.setPlaybackRate(parseFloat(savedSpeed));
        }

        // Restore quality preference
        const savedQuality = localStorage.getItem('reelnn_quality');
        if (savedQuality !== null) {
            this.state.quality = savedQuality;
        }
    }

    restoreProgress() {
        const hashId = this.getHashIdFromUrl();
        if (!hashId) return;

        const savedProgress = localStorage.getItem(`reelnn_progress_${hashId}`);
        if (savedProgress !== null) {
            const progress = parseFloat(savedProgress);
            // Only restore if more than 30 seconds and less than 90% watched
            if (progress > 30 && progress < this.video.duration * 0.9) {
                this.video.currentTime = progress;
            }
        }
    }

    saveProgress() {
        const hashId = this.getHashIdFromUrl();
        if (!hashId || !this.video.duration) return;

        // Save progress every 5 seconds
        if (Math.floor(this.video.currentTime) % 5 === 0) {
            localStorage.setItem(`reelnn_progress_${hashId}`, this.video.currentTime);
        }
    }

    getHashIdFromUrl() {
        const path = window.location.pathname;
        const match = path.match(/\/(movie|show)\/([^\/]+)/);
        return match ? match[2] : null;
    }

    // Public API
    play() {
        return this.video.play();
    }

    pause() {
        this.video.pause();
    }

    destroy() {
        // Clean up event listeners
        clearTimeout(this.controlsTimeout);
        clearInterval(this.progressUpdateInterval);

        // Remove keyboard listener
        document.removeEventListener('keydown', this.handleKeyboard);

        // Remove fullscreen listeners
        document.removeEventListener('fullscreenchange', this.handleFullscreenChange);
        document.removeEventListener('webkitfullscreenchange', this.handleFullscreenChange);
        document.removeEventListener('mozfullscreenchange', this.handleFullscreenChange);
        document.removeEventListener('MSFullscreenChange', this.handleFullscreenChange);

        // Remove player overlay
        const overlay = this.container.querySelector('#playerOverlay');
        if (overlay) {
            overlay.remove();
        }
    }
}

// Export for use
window.ReelNNPlayer = ReelNNPlayer;

    setupEventListeners() {
        // Video events
        this.video.addEventListener('loadstart', () => this.showLoading());
        this.video.addEventListener('loadeddata', () => this.hideLoading());
        this.video.addEventListener('canplay', () => this.hideLoading());
        this.video.addEventListener('waiting', () => this.showLoading());
        this.video.addEventListener('playing', () => this.hideLoading());

        this.video.addEventListener('loadedmetadata', () => {
            this.updateDuration();
            this.restoreProgress();
        });

        this.video.addEventListener('timeupdate', () => {
            this.updateProgress();
            this.saveProgress();
        });

        this.video.addEventListener('play', () => {
            this.state.isPlaying = true;
            this.updatePlayButton();
            this.container.classList.add('playing');
            this.container.classList.remove('paused');
        });

        this.video.addEventListener('pause', () => {
            this.state.isPlaying = false;
            this.updatePlayButton();
            this.container.classList.add('paused');
            this.container.classList.remove('playing');
        });

        this.video.addEventListener('ended', () => {
            this.state.isPlaying = false;
            this.updatePlayButton();
            this.showCenterControls();
        });

        this.video.addEventListener('volumechange', () => {
            this.state.volume = this.video.volume;
            this.state.isMuted = this.video.muted;
            this.updateVolumeDisplay();
        });

        // Control events
        this.elements.centerPlayBtn.addEventListener('click', () => this.togglePlay());
        this.elements.playPauseBtn.addEventListener('click', () => this.togglePlay());
        this.elements.rewindBtn.addEventListener('click', () => this.seek(-10));
        this.elements.forwardBtn.addEventListener('click', () => this.seek(10));
        this.elements.volumeBtn.addEventListener('click', () => this.toggleMute());
        this.elements.volumeRange.addEventListener('input', (e) => this.setVolume(e.target.value));
        this.elements.fullscreenBtn.addEventListener('click', () => this.toggleFullscreen());
        this.elements.settingsBtn.addEventListener('click', () => this.toggleSettings());
        this.elements.captionsBtn.addEventListener('click', () => this.toggleCaptions());
        this.elements.pipBtn.addEventListener('click', () => this.togglePictureInPicture());

        // Progress bar events
        this.elements.progressContainer.addEventListener('click', (e) => this.seekToPosition(e));
        this.elements.progressHandle.addEventListener('mousedown', (e) => this.startProgressDrag(e));

        // Settings menu events
        this.elements.speedOptions.addEventListener('click', (e) => {
            if (e.target.dataset.speed) {
                this.setPlaybackRate(parseFloat(e.target.dataset.speed));
            }
        });

        // Keyboard events
        document.addEventListener('keydown', (e) => this.handleKeyboard(e));

        // Mouse events for controls visibility
        this.container.addEventListener('mousemove', () => this.showControls());
        this.container.addEventListener('mouseleave', () => this.hideControlsDelayed());

        // Touch events for mobile
        this.setupTouchEvents();

        // Fullscreen events
        document.addEventListener('fullscreenchange', () => this.handleFullscreenChange());
        document.addEventListener('webkitfullscreenchange', () => this.handleFullscreenChange());
        document.addEventListener('mozfullscreenchange', () => this.handleFullscreenChange());
        document.addEventListener('MSFullscreenChange', () => this.handleFullscreenChange());
    }

    setupTouchEvents() {
        let touchStartX = 0;
        let touchStartY = 0;
        let touchStartTime = 0;

        this.container.addEventListener('touchstart', (e) => {
            touchStartX = e.touches[0].clientX;
            touchStartY = e.touches[0].clientY;
            touchStartTime = this.video.currentTime;
        });

        this.container.addEventListener('touchmove', (e) => {
            if (e.touches.length !== 1) return;

            const touchX = e.touches[0].clientX;
            const touchY = e.touches[0].clientY;
            const deltaX = touchX - touchStartX;
            const deltaY = touchY - touchStartY;

            // Horizontal swipe for seeking
            if (Math.abs(deltaX) > Math.abs(deltaY) && Math.abs(deltaX) > 50) {
                e.preventDefault();
                const seekAmount = (deltaX / this.container.offsetWidth) * 30; // 30 seconds max
                const newTime = Math.max(0, Math.min(this.video.duration, touchStartTime + seekAmount));
                this.video.currentTime = newTime;
            }

            // Vertical swipe for volume (right side) or brightness (left side)
            if (Math.abs(deltaY) > Math.abs(deltaX) && Math.abs(deltaY) > 50) {
                e.preventDefault();
                if (touchStartX > this.container.offsetWidth / 2) {
                    // Right side - volume control
                    const volumeChange = -(deltaY / this.container.offsetHeight);
                    const newVolume = Math.max(0, Math.min(1, this.state.volume + volumeChange));
                    this.setVolume(newVolume);
                }
            }
        });
    }

    // Core playback methods
    togglePlay() {
        if (this.video.paused) {
            this.video.play();
        } else {
            this.video.pause();
        }
    }

    seek(seconds) {
        const newTime = Math.max(0, Math.min(this.video.duration, this.video.currentTime + seconds));
        this.video.currentTime = newTime;
    }

    setVolume(volume) {
        this.video.volume = Math.max(0, Math.min(1, volume));
        this.elements.volumeRange.value = this.video.volume;
        localStorage.setItem('reelnn_volume', this.video.volume);
    }

    toggleMute() {
        this.video.muted = !this.video.muted;
        localStorage.setItem('reelnn_muted', this.video.muted);
    }

    setPlaybackRate(rate) {
        this.video.playbackRate = rate;
        this.state.playbackRate = rate;

        // Update active speed button
        this.elements.speedOptions.querySelectorAll('.reelnn-option-btn').forEach(btn => {
            btn.classList.remove('active');
            if (parseFloat(btn.dataset.speed) === rate) {
                btn.classList.add('active');
            }
        });

        localStorage.setItem('reelnn_speed', rate);
    }
