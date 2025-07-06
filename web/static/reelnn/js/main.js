/**
 * Main JavaScript file for reelnn frontend - Exact Reelnn Implementation
 * Matches Next.js reelnn functionality exactly
 */

class ReelnnApp {
    constructor() {
        this.currentSlide = 0;
        this.slideInterval = null;
        this.slides = [];
        this.indicators = [];
        this.init();
    }

    init() {
        this.setupEventListeners();
        this.initializeComponents();
        this.setupHeroSlideshow();
        this.setupCardGrids();
        this.setupMobileMenu();
        this.setupVideoPlayer();
        this.setupCardInteractions();
        this.setupLazyLoading();
    }

    setupEventListeners() {
        // Global event listeners
        document.addEventListener('DOMContentLoaded', () => {
            this.onDOMContentLoaded();
        });

        // Navigation search
        const searchForm = document.querySelector('nav form');
        if (searchForm) {
            searchForm.addEventListener('submit', (e) => {
                this.handleSearch(e);
            });
        }

        // Lazy loading for images
        this.setupLazyLoading();

        // Keyboard shortcuts
        this.setupKeyboardShortcuts();
    }

    setupHeroSlideshow() {
        this.slides = document.querySelectorAll('[data-slide]');
        this.indicators = document.querySelectorAll('[data-slide-to]');

        if (this.slides.length <= 1) return;

        // Setup auto-advance
        this.startSlideshow();

        // Setup indicator clicks
        this.indicators.forEach((indicator, index) => {
            indicator.addEventListener('click', () => {
                this.goToSlide(index);
            });
        });

        // Pause on hover
        const heroSection = document.querySelector('.reelnn-hero');
        if (heroSection) {
            heroSection.addEventListener('mouseenter', () => {
                this.pauseSlideshow();
            });

            heroSection.addEventListener('mouseleave', () => {
                this.startSlideshow();
            });
        }
    }

    startSlideshow() {
        this.pauseSlideshow(); // Clear any existing interval
        this.slideInterval = setInterval(() => {
            this.nextSlide();
        }, 8000); // 8 seconds like reelnn
    }

    pauseSlideshow() {
        if (this.slideInterval) {
            clearInterval(this.slideInterval);
            this.slideInterval = null;
        }
    }

    nextSlide() {
        this.currentSlide = (this.currentSlide + 1) % this.slides.length;
        this.updateSlides();
    }

    goToSlide(index) {
        this.currentSlide = index;
        this.updateSlides();
        this.startSlideshow(); // Restart timer
    }

    updateSlides() {
        // Update slide visibility
        this.slides.forEach((slide, index) => {
            if (index === this.currentSlide) {
                slide.style.opacity = '1';
            } else {
                slide.style.opacity = '0';
            }
        });

        // Update indicators
        this.indicators.forEach((indicator, index) => {
            if (index === this.currentSlide) {
                indicator.classList.add('bg-white', 'w-5', 'sm:w-6');
                indicator.classList.remove('bg-white/50');
            } else {
                indicator.classList.add('bg-white/50');
                indicator.classList.remove('bg-white', 'w-5', 'sm:w-6');
            }
        });
    }

    setupCardGrids() {
        // Setup horizontal scrolling for card grids
        const cardGrids = document.querySelectorAll('.reelnn-card-scroll');

        cardGrids.forEach(grid => {
            // Add smooth scrolling
            grid.style.scrollBehavior = 'smooth';

            // Optional: Add scroll buttons for desktop
            this.addScrollButtons(grid);
        });
    }

    addScrollButtons(grid) {
        const container = grid.parentElement;
        if (!container) return;

        // Create scroll buttons
        const leftButton = document.createElement('button');
        leftButton.innerHTML = '‹';
        leftButton.className = 'absolute left-2 top-1/2 transform -translate-y-1/2 bg-black/50 text-white w-10 h-10 rounded-full opacity-0 hover:opacity-100 transition-opacity z-10 hidden md:flex items-center justify-center';

        const rightButton = document.createElement('button');
        rightButton.innerHTML = '›';
        rightButton.className = 'absolute right-2 top-1/2 transform -translate-y-1/2 bg-black/50 text-white w-10 h-10 rounded-full opacity-0 hover:opacity-100 transition-opacity z-10 hidden md:flex items-center justify-center';

        // Add event listeners
        leftButton.addEventListener('click', () => {
            grid.scrollBy({ left: -200, behavior: 'smooth' });
        });

        rightButton.addEventListener('click', () => {
            grid.scrollBy({ left: 200, behavior: 'smooth' });
        });

        // Show/hide buttons on hover
        container.addEventListener('mouseenter', () => {
            leftButton.style.opacity = '1';
            rightButton.style.opacity = '1';
        });

        container.addEventListener('mouseleave', () => {
            leftButton.style.opacity = '0';
            rightButton.style.opacity = '0';
        });

        container.appendChild(leftButton);
        container.appendChild(rightButton);
    }

    setupMobileMenu() {
        const mobileMenuBtn = document.getElementById('mobile-menu-btn');
        const mobileMenu = document.getElementById('mobile-menu');

        if (mobileMenuBtn && mobileMenu) {
            mobileMenuBtn.addEventListener('click', () => {
                mobileMenu.classList.toggle('hidden');

                // Update aria-expanded
                const isExpanded = !mobileMenu.classList.contains('hidden');
                mobileMenuBtn.setAttribute('aria-expanded', isExpanded);
            });

            // Close menu when clicking outside
            document.addEventListener('click', (e) => {
                if (!mobileMenuBtn.contains(e.target) && !mobileMenu.contains(e.target)) {
                    mobileMenu.classList.add('hidden');
                    mobileMenuBtn.setAttribute('aria-expanded', 'false');
                }
            });
        }
    }

    // Exact Reelnn VideoPlayer functionality
    setupVideoPlayer() {
        const videoContainer = document.getElementById('videoPlayerContainer');
        if (!videoContainer) return;

        this.videoPlayer = new ReelnnVideoPlayer(videoContainer);
    }
}

// Legacy VideoPlayer Class - DEPRECATED: Use ReelNNPlayer instead
class ReelnnVideoPlayer {
    constructor(container) {
        this.container = container;
        this.video = container.querySelector('#player');
        this.controlsOverlay = container.querySelector('#controlsOverlay');
        this.loadingIndicator = container.querySelector('#loadingIndicator');
        this.centerControls = container.querySelector('#centerControls');
        this.bottomControls = container.querySelector('#bottomControls');
        this.settingsMenu = container.querySelector('#settingsMenu');

        this.state = {
            isPlaying: false,
            currentTime: 0,
            duration: 0,
            volume: 1,
            isMuted: false,
            isFullscreen: false,
            showControls: true,
            isLoading: true,
            playbackRate: 1,
            quality: 'auto'
        };

        this.controlsTimeout = null;
        this.progressDragging = false;
        this.volumeDragging = false;

        this.init();
    }

    init() {
        this.setupEventListeners();
        this.setupProgressBar();
        this.setupVolumeControl();
        this.setupKeyboardShortcuts();
        this.setupTouchControls();
        this.restoreUserPreferences();
        this.hideControlsAfterDelay();
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

        this.video.addEventListener('volumechange', () => {
            this.state.volume = this.video.volume;
            this.state.isMuted = this.video.muted;
            this.updateVolumeButton();
            this.updateVolumeSlider();
        });

        this.video.addEventListener('ended', () => {
            this.handleVideoEnd();
        });

        // Control events
        this.setupControlEvents();

        // Mouse/touch events for showing/hiding controls
        this.container.addEventListener('mousemove', () => this.showControls());
        this.container.addEventListener('touchstart', () => this.showControls());
        this.container.addEventListener('mouseleave', () => this.hideControlsAfterDelay());

        // Click to play/pause
        this.video.addEventListener('click', (e) => {
            if (!this.settingsMenu.classList.contains('show')) {
                this.togglePlay();
            }
        });

        // Double click for fullscreen
        this.video.addEventListener('dblclick', () => this.toggleFullscreen());
    }

    setupControlEvents() {
        // Play/pause buttons
        const playButtons = this.container.querySelectorAll('#centerPlayButton, #playPauseButton');
        playButtons.forEach(btn => {
            btn.addEventListener('click', () => this.togglePlay());
        });

        // Seek buttons
        const rewindBtn = this.container.querySelector('#rewindButton');
        const forwardBtn = this.container.querySelector('#forwardButton');

        if (rewindBtn) rewindBtn.addEventListener('click', () => this.seek(-10));
        if (forwardBtn) forwardBtn.addEventListener('click', () => this.seek(10));

        // Volume button
        const volumeBtn = this.container.querySelector('#volumeButton');
        if (volumeBtn) volumeBtn.addEventListener('click', () => this.toggleMute());

        // Settings button
        const settingsBtn = this.container.querySelector('#settingsButton');
        const settingsClose = this.container.querySelector('#settingsClose');

        if (settingsBtn) {
            settingsBtn.addEventListener('click', () => this.toggleSettings());
        }

        if (settingsClose) {
            settingsClose.addEventListener('click', () => this.hideSettings());
        }

        // Fullscreen button
        const fullscreenBtn = this.container.querySelector('#fullscreenButton');
        if (fullscreenBtn) {
            fullscreenBtn.addEventListener('click', () => this.toggleFullscreen());
        }

        // Settings controls
        const qualitySelect = this.container.querySelector('#qualitySelect');
        const speedSelect = this.container.querySelector('#speedSelect');

        if (qualitySelect) {
            qualitySelect.addEventListener('change', (e) => this.changeQuality(e.target.value));
        }

        if (speedSelect) {
            speedSelect.addEventListener('change', (e) => this.changeSpeed(parseFloat(e.target.value)));
        }
    }

    setupProgressBar() {
        const progressBar = this.container.querySelector('#progressBar');
        const progressPlayed = this.container.querySelector('#progressPlayed');
        const progressThumb = this.container.querySelector('#progressThumb');

        if (!progressBar) return;

        progressBar.addEventListener('mousedown', (e) => this.startProgressDrag(e));
        progressBar.addEventListener('mousemove', (e) => this.updateProgressPreview(e));
        progressBar.addEventListener('mouseleave', () => this.hideProgressPreview());

        document.addEventListener('mousemove', (e) => {
            if (this.progressDragging) this.updateProgressDrag(e);
        });

        document.addEventListener('mouseup', () => {
            if (this.progressDragging) this.endProgressDrag();
        });
    }

    setupVolumeControl() {
        const volumeSlider = this.container.querySelector('#volumeSlider');
        const volumeTrack = volumeSlider?.querySelector('.reelnn-volume-track');

        if (!volumeTrack) return;

        volumeTrack.addEventListener('mousedown', (e) => this.startVolumeDrag(e));

        document.addEventListener('mousemove', (e) => {
            if (this.volumeDragging) this.updateVolumeDrag(e);
        });

        document.addEventListener('mouseup', () => {
            if (this.volumeDragging) this.endVolumeDrag();
        });
    }

    setupKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;

            switch(e.key) {
                case ' ':
                case 'k':
                    e.preventDefault();
                    this.togglePlay();
                    break;
                case 'ArrowLeft':
                case 'j':
                    e.preventDefault();
                    this.seek(-10);
                    this.showSkipIndicator('-10s');
                    break;
                case 'ArrowRight':
                case 'l':
                    e.preventDefault();
                    this.seek(10);
                    this.showSkipIndicator('+10s');
                    break;
                case 'ArrowUp':
                    e.preventDefault();
                    this.changeVolume(0.1);
                    break;
                case 'ArrowDown':
                    e.preventDefault();
                    this.changeVolume(-0.1);
                    break;
                case 'm':
                    e.preventDefault();
                    this.toggleMute();
                    break;
                case 'f':
                    e.preventDefault();
                    this.toggleFullscreen();
                    break;
                case ',':
                    e.preventDefault();
                    if (this.video.paused) this.seek(-1/30); // Frame by frame
                    break;
                case '.':
                    e.preventDefault();
                    if (this.video.paused) this.seek(1/30); // Frame by frame
                    break;
                case '0':
                case '1':
                case '2':
                case '3':
                case '4':
                case '5':
                case '6':
                case '7':
                case '8':
                case '9':
                    e.preventDefault();
                    const percentage = parseInt(e.key) * 10;
                    this.seekToPercentage(percentage);
                    this.showSkipIndicator(`${percentage}%`);
                    break;
            }
        });
    }

    setupTouchControls() {
        let touchStartX = 0;
        let touchStartY = 0;
        let touchStartTime = 0;

        this.video.addEventListener('touchstart', (e) => {
            touchStartX = e.touches[0].clientX;
            touchStartY = e.touches[0].clientY;
            touchStartTime = this.video.currentTime;
        });

        this.video.addEventListener('touchmove', (e) => {
            if (e.touches.length !== 1) return;

            const touchX = e.touches[0].clientX;
            const touchY = e.touches[0].clientY;
            const deltaX = touchX - touchStartX;
            const deltaY = touchY - touchStartY;

            // Horizontal swipe for seeking
            if (Math.abs(deltaX) > Math.abs(deltaY) && Math.abs(deltaX) > 50) {
                e.preventDefault();
                const seekAmount = (deltaX / this.container.offsetWidth) * this.video.duration;
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
                    this.video.volume = newVolume;
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

    seekToPercentage(percentage) {
        const newTime = (this.video.duration * percentage) / 100;
        this.video.currentTime = newTime;
    }

    changeVolume(delta) {
        const newVolume = Math.max(0, Math.min(1, this.video.volume + delta));
        this.video.volume = newVolume;
        this.showVolumeIndicator(Math.round(newVolume * 100) + '%');
    }

    toggleMute() {
        this.video.muted = !this.video.muted;
        this.container.classList.toggle('muted', this.video.muted);
    }

    toggleFullscreen() {
        if (!document.fullscreenElement) {
            this.container.requestFullscreen().then(() => {
                this.state.isFullscreen = true;
                this.container.classList.add('fullscreen');

                // Lock orientation on mobile
                if (screen.orientation && screen.orientation.lock) {
                    screen.orientation.lock('landscape').catch(() => {});
                }
            }).catch(() => {});
        } else {
            document.exitFullscreen().then(() => {
                this.state.isFullscreen = false;
                this.container.classList.remove('fullscreen');

                // Unlock orientation
                if (screen.orientation && screen.orientation.unlock) {
                    screen.orientation.unlock();
                }
            }).catch(() => {});
        }
    }

    changeQuality(quality) {
        const currentTime = this.video.currentTime;
        const wasPlaying = !this.video.paused;

        this.state.quality = quality;

        // Update video source
        const newSrc = this.video.src.replace(/quality=[^&]*/, `quality=${quality}`);
        this.video.src = newSrc;

        this.video.addEventListener('loadeddata', () => {
            this.video.currentTime = currentTime;
            if (wasPlaying) this.video.play();
        }, { once: true });

        localStorage.setItem('preferred_quality', quality);
    }

    changeSpeed(rate) {
        this.video.playbackRate = rate;
        this.state.playbackRate = rate;
        localStorage.setItem('preferred_speed', rate.toString());
    }

    // UI Update Methods
    updatePlayButton() {
        const playButtons = this.container.querySelectorAll('#centerPlayButton, #playPauseButton');
        playButtons.forEach(btn => {
            const playIcon = btn.querySelector('.reelnn-play-icon');
            const pauseIcon = btn.querySelector('.reelnn-pause-icon');

            if (this.state.isPlaying) {
                if (playIcon) playIcon.style.display = 'none';
                if (pauseIcon) pauseIcon.style.display = 'block';
            } else {
                if (playIcon) playIcon.style.display = 'block';
                if (pauseIcon) pauseIcon.style.display = 'none';
            }
        });
    }

    updateVolumeButton() {
        const volumeBtn = this.container.querySelector('#volumeButton');
        if (!volumeBtn) return;

        const highIcon = volumeBtn.querySelector('.reelnn-volume-high');
        const lowIcon = volumeBtn.querySelector('.reelnn-volume-low');
        const muteIcon = volumeBtn.querySelector('.reelnn-volume-mute');

        // Hide all icons first
        [highIcon, lowIcon, muteIcon].forEach(icon => {
            if (icon) icon.style.display = 'none';
        });

        // Show appropriate icon
        if (this.video.muted || this.video.volume === 0) {
            if (muteIcon) muteIcon.style.display = 'block';
        } else if (this.video.volume > 0.5) {
            if (highIcon) highIcon.style.display = 'block';
        } else {
            if (lowIcon) lowIcon.style.display = 'block';
        }
    }

    updateVolumeSlider() {
        const volumeFill = this.container.querySelector('#volumeFill');
        const volumeThumb = this.container.querySelector('#volumeThumb');

        if (volumeFill) {
            const volume = this.video.muted ? 0 : this.video.volume;
            volumeFill.style.width = `${volume * 100}%`;
        }

        if (volumeThumb) {
            const volume = this.video.muted ? 0 : this.video.volume;
            volumeThumb.style.left = `${volume * 100}%`;
        }
    }

    updateProgress() {
        if (this.progressDragging) return;

        const progressPlayed = this.container.querySelector('#progressPlayed');
        const progressThumb = this.container.querySelector('#progressThumb');

        if (this.video.duration > 0) {
            const percentage = (this.video.currentTime / this.video.duration) * 100;

            if (progressPlayed) {
                progressPlayed.style.width = `${percentage}%`;
            }

            if (progressThumb) {
                progressThumb.style.left = `${percentage}%`;
            }
        }

        this.updateTimeDisplay();
    }

    updateTimeDisplay() {
        const currentTimeEl = this.container.querySelector('#currentTime');
        const durationEl = this.container.querySelector('#duration');

        if (currentTimeEl) {
            currentTimeEl.textContent = this.formatTime(this.video.currentTime);
        }

        if (durationEl) {
            durationEl.textContent = this.formatTime(this.video.duration);
        }
    }

    updateDuration() {
        this.state.duration = this.video.duration;
        this.updateTimeDisplay();
    }

    // Control visibility methods
    showControls() {
        this.state.showControls = true;
        this.controlsOverlay.classList.add('show-controls');
        this.centerControls.style.opacity = '1';
        this.bottomControls.style.opacity = '1';

        this.hideControlsAfterDelay();
    }

    hideControls() {
        if (!this.video.paused && !this.settingsMenu.classList.contains('show')) {
            this.state.showControls = false;
            this.controlsOverlay.classList.remove('show-controls');
            this.centerControls.style.opacity = '0';
            this.bottomControls.style.opacity = '0';
        }
    }

    hideControlsAfterDelay() {
        clearTimeout(this.controlsTimeout);
        this.controlsTimeout = setTimeout(() => {
            this.hideControls();
        }, 3000);
    }

    showLoading() {
        this.state.isLoading = true;
        this.loadingIndicator.style.display = 'flex';
    }

    hideLoading() {
        this.state.isLoading = false;
        this.loadingIndicator.style.display = 'none';
    }

    toggleSettings() {
        const isVisible = this.settingsMenu.classList.contains('show');

        if (isVisible) {
            this.hideSettings();
        } else {
            this.showSettings();
        }
    }

    showSettings() {
        this.settingsMenu.classList.add('show');
        this.showControls();
    }

    hideSettings() {
        this.settingsMenu.classList.remove('show');
    }

    // Drag handlers
    startProgressDrag(e) {
        this.progressDragging = true;
        this.updateProgressDrag(e);
        e.preventDefault();
    }

    updateProgressDrag(e) {
        if (!this.progressDragging) return;

        const progressBar = this.container.querySelector('#progressBar');
        const rect = progressBar.getBoundingClientRect();
        const percentage = Math.max(0, Math.min(100, ((e.clientX - rect.left) / rect.width) * 100));
        const newTime = (this.video.duration * percentage) / 100;

        this.video.currentTime = newTime;
    }

    endProgressDrag() {
        this.progressDragging = false;
    }

    startVolumeDrag(e) {
        this.volumeDragging = true;
        this.updateVolumeDrag(e);
        e.preventDefault();
    }

    updateVolumeDrag(e) {
        if (!this.volumeDragging) return;

        const volumeTrack = this.container.querySelector('.reelnn-volume-track');
        const rect = volumeTrack.getBoundingClientRect();
        const percentage = Math.max(0, Math.min(100, ((e.clientX - rect.left) / rect.width) * 100));

        this.video.volume = percentage / 100;
        this.video.muted = false;
    }

    endVolumeDrag() {
        this.volumeDragging = false;
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

    showSkipIndicator(text) {
        // Create and show skip indicator
        const indicator = document.createElement('div');
        indicator.className = 'reelnn-skip-indicator';
        indicator.textContent = text;
        indicator.style.cssText = `
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            background: rgba(0, 0, 0, 0.8);
            color: white;
            padding: 0.5rem 1rem;
            border-radius: 0.25rem;
            font-size: 1rem;
            font-weight: 600;
            z-index: 50;
            pointer-events: none;
        `;

        this.container.appendChild(indicator);

        setTimeout(() => {
            indicator.remove();
        }, 1000);
    }

    showVolumeIndicator(text) {
        // Create and show volume indicator
        const indicator = document.createElement('div');
        indicator.className = 'reelnn-volume-indicator';
        indicator.textContent = text;
        indicator.style.cssText = `
            position: absolute;
            top: 50%;
            right: 2rem;
            transform: translateY(-50%);
            background: rgba(0, 0, 0, 0.8);
            color: white;
            padding: 0.5rem 1rem;
            border-radius: 0.25rem;
            font-size: 1rem;
            font-weight: 600;
            z-index: 50;
            pointer-events: none;
        `;

        this.container.appendChild(indicator);

        setTimeout(() => {
            indicator.remove();
        }, 1000);
    }

    // Progress and preferences
    saveProgress() {
        if (this.video.duration > 0) {
            const progress = {
                time: this.video.currentTime,
                duration: this.video.duration,
                percentage: (this.video.currentTime / this.video.duration) * 100,
                timestamp: Date.now()
            };

            localStorage.setItem(`video_progress_${window.mediaData?.hash_id}`, JSON.stringify(progress));
        }
    }

    restoreProgress() {
        const saved = localStorage.getItem(`video_progress_${window.mediaData?.hash_id}`);
        if (saved) {
            try {
                const progress = JSON.parse(saved);
                // Only restore if less than 90% watched and within 7 days
                if (progress.percentage < 90 && (Date.now() - progress.timestamp) < 7 * 24 * 60 * 60 * 1000) {
                    this.video.currentTime = progress.time;
                }
            } catch (e) {
                console.warn('Failed to restore progress:', e);
            }
        }
    }

    restoreUserPreferences() {
        // Restore quality preference
        const savedQuality = localStorage.getItem('preferred_quality');
        if (savedQuality) {
            const qualitySelect = this.container.querySelector('#qualitySelect');
            if (qualitySelect) {
                qualitySelect.value = savedQuality;
                this.state.quality = savedQuality;
            }
        }

        // Restore speed preference
        const savedSpeed = localStorage.getItem('preferred_speed');
        if (savedSpeed) {
            const speedSelect = this.container.querySelector('#speedSelect');
            if (speedSelect) {
                speedSelect.value = savedSpeed;
                this.video.playbackRate = parseFloat(savedSpeed);
            }
        }

        // Restore volume preference
        const savedVolume = localStorage.getItem('preferred_volume');
        if (savedVolume) {
            this.video.volume = parseFloat(savedVolume);
        }
    }

    handleVideoEnd() {
        // Mark as watched
        if (window.mediaData) {
            localStorage.setItem(`watched_${window.mediaData.hash_id}`, JSON.stringify({
                completed: true,
                timestamp: Date.now(),
                duration: this.video.duration
            }));
        }

        // Show replay button or next content
        this.showControls();
    }

    onDOMContentLoaded() {
        // Initialize page-specific functionality
        const currentPage = this.getCurrentPage();
        
        switch (currentPage) {
            case 'home':
                this.initHomePage();
                break;
            case 'movie':
                this.initMoviePage();
                break;
            case 'show':
                this.initShowPage();
                break;
            // watch page removed - using movie/show pages instead
            case 'search':
                this.initSearchPage();
                break;
        }
    }

    getCurrentPage() {
        const path = window.location.pathname;
        
        if (path === '/') return 'home';
        if (path.startsWith('/movie/')) return 'movie';
        if (path.startsWith('/show/')) return 'show';
        if (path.startsWith('/watch/')) return 'watch';
        if (path.startsWith('/search')) return 'search';
        
        return 'unknown';
    }

    initHomePage() {
        // Initialize hero slider
        this.initHeroSlider();
        
        // Load trending and recent media
        this.loadHomePageData();
    }

    initMoviePage() {
        // Initialize movie-specific functionality
        this.initQualitySelector();
        this.loadMovieDetails();
    }

    initShowPage() {
        // Initialize TV show functionality
        this.initSeasonTabs();
        this.initEpisodeGrid();
    }

    initWatchPage() {
        // Initialize video player
        this.initVideoPlayer();
        this.loadMediaTracks();
    }

    initSearchPage() {
        // Initialize search functionality
        this.searchManager.init();
    }

    initHeroSlider() {
        const slider = document.getElementById('heroSlider');
        if (!slider) return;

        const slides = slider.querySelectorAll('.hero-slide');
        if (slides.length <= 1) return;

        let currentSlide = 0;
        
        const nextSlide = () => {
            slides[currentSlide].classList.remove('active');
            currentSlide = (currentSlide + 1) % slides.length;
            slides[currentSlide].classList.add('active');
        };

        // Auto-advance slides every 5 seconds
        setInterval(nextSlide, 5000);

        // Add navigation dots
        this.addSliderNavigation(slider, slides);
    }

    addSliderNavigation(slider, slides) {
        const nav = document.createElement('div');
        nav.className = 'hero-nav';
        nav.style.cssText = `
            position: absolute;
            bottom: 2rem;
            left: 50%;
            transform: translateX(-50%);
            display: flex;
            gap: 0.5rem;
            z-index: 3;
        `;

        slides.forEach((_, index) => {
            const dot = document.createElement('button');
            dot.className = `nav-dot ${index === 0 ? 'active' : ''}`;
            dot.style.cssText = `
                width: 12px;
                height: 12px;
                border-radius: 50%;
                border: 2px solid white;
                background: ${index === 0 ? 'white' : 'transparent'};
                cursor: pointer;
                transition: all 0.3s ease;
            `;
            
            dot.addEventListener('click', () => {
                slides.forEach(slide => slide.classList.remove('active'));
                nav.querySelectorAll('.nav-dot').forEach(d => {
                    d.classList.remove('active');
                    d.style.background = 'transparent';
                });
                
                slides[index].classList.add('active');
                dot.classList.add('active');
                dot.style.background = 'white';
            });
            
            nav.appendChild(dot);
        });

        slider.appendChild(nav);
    }

    initQualitySelector() {
        const qualityOptions = document.querySelectorAll('.quality-option');
        
        qualityOptions.forEach(option => {
            option.addEventListener('click', () => {
                qualityOptions.forEach(opt => opt.classList.remove('active'));
                option.classList.add('active');
                
                // Update play/download links with selected quality
                this.updateMediaLinks(option.dataset.quality);
            });
        });
    }

    initSeasonTabs() {
        const seasonTabs = document.querySelectorAll('.season-tab');
        const seasonContents = document.querySelectorAll('.season-content');
        
        seasonTabs.forEach(tab => {
            tab.addEventListener('click', () => {
                const targetSeason = tab.dataset.season;
                
                // Update active tab
                seasonTabs.forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                
                // Show corresponding season content
                seasonContents.forEach(content => {
                    if (content.dataset.season === targetSeason) {
                        content.style.display = 'grid';
                    } else {
                        content.style.display = 'none';
                    }
                });
            });
        });
    }

    initVideoPlayer() {
        // Video player initialization is handled by ReelNN Player in movie/show templates
        console.log('ReelNN Player is used for video playback');
    }

    setupLazyLoading() {
        const images = document.querySelectorAll('img[loading="lazy"]');
        
        if ('IntersectionObserver' in window) {
            const imageObserver = new IntersectionObserver((entries, observer) => {
                entries.forEach(entry => {
                    if (entry.isIntersecting) {
                        const img = entry.target;
                        img.src = img.dataset.src || img.src;
                        img.classList.remove('lazy');
                        observer.unobserve(img);
                    }
                });
            });

            images.forEach(img => imageObserver.observe(img));
        }
    }

    setupKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            // Global shortcuts
            if (e.ctrlKey || e.metaKey) {
                switch (e.key) {
                    case 'k':
                        e.preventDefault();
                        this.focusSearch();
                        break;
                }
            }

            // Player shortcuts (only on watch page)
            if (this.getCurrentPage() === 'watch' && this.mediaPlayer) {
                switch (e.key) {
                    case ' ':
                        e.preventDefault();
                        this.mediaPlayer.togglePlay();
                        break;
                    case 'f':
                        e.preventDefault();
                        this.mediaPlayer.fullscreen.toggle();
                        break;
                    case 'm':
                        e.preventDefault();
                        this.mediaPlayer.muted = !this.mediaPlayer.muted;
                        break;
                }
            }
        });
    }

    focusSearch() {
        const searchInput = document.querySelector('.search-input');
        if (searchInput) {
            searchInput.focus();
            searchInput.select();
        }
    }

    handleSearch(e) {
        e.preventDefault();
        const formData = new FormData(e.target);
        const query = formData.get('q');
        
        if (query.trim()) {
            window.location.href = `/search?q=${encodeURIComponent(query)}`;
        }
    }

    async loadHomePageData() {
        try {
            // Load trending media
            const trending = await this.apiClient.get('/api/v1/trending');
            this.updateMediaSection('trending', trending);

            // Load hero slider data
            const heroData = await this.apiClient.get('/api/v1/heroslider');
            this.updateHeroSlider(heroData);
        } catch (error) {
            console.error('Error loading homepage data:', error);
        }
    }

    updateMediaSection(sectionId, mediaData) {
        const section = document.querySelector(`[data-section="${sectionId}"]`);
        if (!section || !mediaData) return;

        const grid = section.querySelector('.media-grid');
        if (!grid) return;

        // Update grid with new media data
        grid.innerHTML = mediaData.map(media => this.createMediaCard(media)).join('');
    }

    createMediaCard(media) {
        const posterUrl = media.poster_url || media.thumbnail || '/static/icons/default-video.svg';
        const mediaType = media.series_data ? 'show' : 'movie';
        const rating = media.tmdb_data?.vote_average ? `⭐ ${media.tmdb_data.vote_average.toFixed(1)}` : '';

        return `
            <a href="/${mediaType}/${media.hash_id}" class="media-card">
                <div class="media-poster">
                    <img src="${posterUrl}" alt="${media.title}" class="poster-image" loading="lazy">
                </div>
                <div class="media-info">
                    <h3 class="media-title">${media.title}</h3>
                    <div class="media-meta">
                        <span>${media.release_date?.substring(0, 4) || 'Unknown'}</span>
                        ${rating ? `<div class="media-rating">${rating}</div>` : ''}
                    </div>
                </div>
            </a>
        `;
    }

    updateMediaLinks(quality) {
        // Update play and download links based on selected quality
        const playButtons = document.querySelectorAll('[href*="/movie/"], [href*="/show/"]');
        const downloadButtons = document.querySelectorAll('[href*="download=1"]');
        
        // Implementation would depend on how quality variants are handled
        console.log('Updated media links for quality:', quality);
    }

    async loadMediaTracks() {
        if (this.getCurrentPage() !== 'watch') return;

        const hashId = this.getHashIdFromUrl();
        if (!hashId) return;

        try {
            const tracks = await this.apiClient.get(`/api/media/${hashId}/tracks?hash=${hashId.substring(0, 6)}`);
            this.updateTrackSelectors(tracks);
        } catch (error) {
            console.error('Error loading media tracks:', error);
        }
    }

    getHashIdFromUrl() {
        const path = window.location.pathname;
        const match = path.match(/\/watch\/([^\/]+)/);
        return match ? match[1] : null;
    }

    updateTrackSelectors(tracks) {
        // Update audio tracks
        if (tracks.audio) {
            this.updateTrackSelector('audioTracks', tracks.audio);
        }

        // Update subtitle tracks
        if (tracks.subtitles) {
            this.updateTrackSelector('subtitleTracks', tracks.subtitles);
        }
    }

    updateTrackSelector(containerId, tracks) {
        const container = document.getElementById(containerId);
        if (!container || !tracks.length) return;

        container.innerHTML = tracks.map((track, index) => `
            <div class="control-option ${index === 0 ? 'active' : ''}" data-track="${track.id}">
                <span>${track.language || `Track ${index + 1}`}</span>
                <span class="option-info">${track.codec || track.format || 'Unknown'}</span>
            </div>
        `).join('');
    }

    setupCardInteractions() {
        // Add smooth interactions to all cards
        const cards = document.querySelectorAll('.reelnn-card');

        cards.forEach(card => {
            // Add loading state on click
            card.addEventListener('click', (e) => {
                if (!e.ctrlKey && !e.metaKey) { // Don't add loading for new tab opens
                    card.classList.add('loading');

                    // Remove loading state after navigation or timeout
                    setTimeout(() => {
                        card.classList.remove('loading');
                    }, 3000);
                }
            });

            // Add keyboard navigation
            card.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    card.click();
                }
            });

            // Add focus management
            card.setAttribute('tabindex', '0');
            card.setAttribute('role', 'button');
        });
    }

    setupLazyLoading() {
        // Enhanced lazy loading for images
        const images = document.querySelectorAll('.reelnn-card-image[loading="lazy"]');

        if ('IntersectionObserver' in window) {
            const imageObserver = new IntersectionObserver((entries, observer) => {
                entries.forEach(entry => {
                    if (entry.isIntersecting) {
                        const img = entry.target;

                        // Add loading animation
                        const card = img.closest('.reelnn-card');
                        if (card) {
                            card.classList.add('loading');
                        }

                        // Load the image
                        img.addEventListener('load', () => {
                            if (card) {
                                card.classList.remove('loading');
                            }
                            img.style.opacity = '1';
                        });

                        img.addEventListener('error', () => {
                            if (card) {
                                card.classList.remove('loading');
                            }
                        });

                        observer.unobserve(img);
                    }
                });
            }, {
                rootMargin: '50px 0px',
                threshold: 0.1
            });

            images.forEach(img => {
                img.style.opacity = '0';
                img.style.transition = 'opacity 0.3s ease';
                imageObserver.observe(img);
            });
        }
    }
}

// Initialize app when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        window.reelnnApp = new ReelnnApp();
    });
} else {
    window.reelnnApp = new ReelnnApp();
}
