/**
 * Enhanced Control Panel JavaScript
 * 
 * INTEGRATION:
 * Add to index.html before </body>:
 *     <script src="/static/enhanced_control_panel.js"></script>
 * 
 * OR paste this entire file into your existing <script> section
 */

// ============================================================================
// TTS VOICE MANAGEMENT
// ============================================================================

async function loadAvailableVoices() {
    try {
        const data = await apiCall('/api/tts/voices');
        const select = document.getElementById('tts-voice-select');
        
        if (!select) return;
        
        if (data.voices && data.voices.length > 0) {
            select.innerHTML = data.voices.map(v => 
                `<option value="${v.file}">${v.name} (${(v.size / 1024).toFixed(0)}KB)</option>`
            ).join('');
            addLog('info', `✅ Loaded ${data.voices.length} voice files`);
        } else {
            select.innerHTML = '<option value="">No voices found - Add .wav/.pth files to tts/voices/</option>';
            if (data.message) {
                addLog('info', data.message);
            }
        }
    } catch (error) {
        console.error('Error loading voices:', error);
    }
}

async function loadTTSVoice() {
    const select = document.getElementById('tts-voice-select');
    if (!select) return;
    
    const voiceFile = select.value;
    if (!voiceFile) {
        addLog('warning', 'Please select a voice file');
        return;
    }
    
    addLog('info', `🔊 Loading TTS voice: ${voiceFile}...`);
    
    const result = await apiCall('/api/tts/voice/load', 'POST', {
        voice_name: voiceFile.split('.')[0],
        voice_file: voiceFile
    });
    
    if (result.success) {
        addLog('info', `✅ Voice loaded: ${result.voice}`);
    } else {
        addLog('error', `❌ Failed: ${result.error}`);
    }
}

async function clearTTSVoice() {
    addLog('info', '🔊 Clearing voice reference...');
    
    const result = await apiCall('/api/tts/voice/clear', 'POST');
    
    if (result.success) {
        addLog('info', '✅ Voice cleared (using default)');
    } else {
        addLog('error', `❌ Failed: ${result.error}`);
    }
}

async function loadCurrentTTS() {
    try {
        const data = await apiCall('/api/tts/current');
        
        if (!data.error) {
            const statusDiv = document.getElementById('tts-status');
            if (statusDiv) {
                statusDiv.innerHTML = `
                    <div class="stat"><span>Device</span><span class="stat-value">${data.device.toUpperCase()}</span></div>
                    <div class="stat"><span>CUDA</span><span class="stat-value">${data.cuda_enabled ? 'Yes' : 'No'}</span></div>
                    <div class="stat"><span>Voice Cloning</span><span class="stat-value">${data.voice_cloning_active ? 'Active' : 'Off'}</span></div>
                    <div class="stat"><span>Generations</span><span class="stat-value">${data.total_generations}</span></div>
                `;
            }
            
            const profileSelect = document.getElementById('tts-voice-profile');
            if (profileSelect && data.available_profiles) {
                profileSelect.innerHTML = data.available_profiles.map(p => 
                    `<option value="${p}" ${p === data.active_profile ? 'selected' : ''}>${p}</option>`
                ).join('');
            }
        }
    } catch (error) {
        console.error('Error loading TTS status:', error);
    }
}

async function updateTTSSettings() {
    const enabled = document.getElementById('tts-enabled')?.checked || false;
    const profile = document.getElementById('tts-voice-profile')?.value || 'default';
    
    const result = await apiCall('/api/tts/settings/update', 'POST', {
        enabled,
        profile,
        speed: 1.0,
        pitch: 1.0
    });
    
    if (result.success) {
        addLog('info', `✅ TTS profile: ${profile}`);
    } else {
        addLog('error', `❌ Failed: ${result.error}`);
    }
}

// ============================================================================
// AUDIO PROCESSING CONTROLS
// ============================================================================

async function loadAudioSettings() {
    try {
        const data = await apiCall('/api/audio/settings');
        
        if (!data.error) {
            const vadInput = document.getElementById('vad-threshold');
            const vadValue = document.getElementById('vad-threshold-value');
            if (vadInput && vadValue) {
                vadInput.value = data.vad_threshold;
                vadValue.textContent = data.vad_threshold;
            }
            
            const silenceInput = document.getElementById('silence-threshold');
            const silenceValue = document.getElementById('silence-threshold-value');
            if (silenceInput && silenceValue) {
                silenceInput.value = data.silence_threshold;
                silenceValue.textContent = data.silence_threshold;
            }
            
            const transcriptionCheckbox = document.getElementById('voice-transcription-enabled');
            if (transcriptionCheckbox) {
                transcriptionCheckbox.checked = data.transcription_enabled;
            }
        }
    } catch (error) {
        console.error('Error loading audio settings:', error);
    }
}

async function updateAudioSettings() {
    const vadThreshold = parseInt(document.getElementById('vad-threshold')?.value || 500);
    const silenceThreshold = parseFloat(document.getElementById('silence-threshold')?.value || 3.0);
    const transcriptionEnabled = document.getElementById('voice-transcription-enabled')?.checked || true;
    
    addLog('info', '🎙️ Updating audio settings...');
    
    const result = await apiCall('/api/audio/settings/update', 'POST', {
        vad_threshold: vadThreshold,
        silence_threshold: silenceThreshold,
        transcription_enabled: transcriptionEnabled
    });
    
    if (result.success) {
        addLog('info', '✅ Audio settings updated');
    } else {
        addLog('error', `❌ Failed: ${result.error}`);
    }
}

async function loadAudioStats() {
    try {
        const data = await apiCall('/api/audio/stats');
        
        if (!data.error) {
            const updateStat = (id, value) => {
                const el = document.getElementById(id);
                if (el) el.textContent = value;
            };
            
            updateStat('audio-chunks-received', data.chunks_received || 0);
            updateStat('audio-chunks-processed', data.chunks_processed || 0);
            updateStat('audio-queue-size', data.queue_size || 0);
            updateStat('audio-transcriptions', data.transcriptions_completed || 0);
            updateStat('audio-vad-detections', data.vad_detections || 0);
        }
    } catch (error) {
        console.error('Error loading audio stats:', error);
    }
}

async function loadActiveSpeakers() {
    try {
        const data = await apiCall('/api/audio/speakers');
        const container = document.getElementById('active-speakers-list');
        
        if (!container) return;
        
        if (data.speakers && data.speakers.length > 0) {
            container.innerHTML = data.speakers.map(s => `
                <div class="voice-channel-item">
                    <div class="voice-channel-info">
                        <div class="voice-channel-name">🎤 ${s.username}</div>
                        <div class="voice-channel-server">Buffer: ${(s.buffer_size / 1024).toFixed(1)}KB</div>
                    </div>
                    <div class="status-indicator">
                        <div class="status-dot online"></div>
                    </div>
                </div>
            `).join('');
        } else {
            container.innerHTML = '<p style="color: #888; padding: 10px;">No one speaking</p>';
        }
    } catch (error) {
        console.error('Error loading active speakers:', error);
    }
}

// ============================================================================
// VOICE PROFILE MANAGEMENT
// ============================================================================

async function loadVoiceProfiles() {
    try {
        const data = await apiCall('/api/voice-profiles/list');
        
        if (!data.error) {
            const container = document.getElementById('voice-profiles-list');
            const select = document.getElementById('tts-voice-profile');
            
            if (select) {
                select.innerHTML = data.profiles.map(p => 
                    `<option value="${p.name}" ${p.name === data.active ? 'selected' : ''}>${p.name}</option>`
                ).join('');
            }
            
            if (container) {
                container.innerHTML = data.profiles.map(p => `
                    <div class="voice-channel-item">
                        <div class="voice-channel-info">
                            <div class="voice-channel-name">🎙️ ${p.name} ${p.name === data.active ? '(Active)' : ''}</div>
                            <div class="voice-channel-server">Speed: ${p.speed}x, Temp: ${p.temperature}</div>
                        </div>
                        <div>
                            ${['default', 'casual', 'energetic', 'calm', 'sarcastic'].includes(p.name) ? 
                                `<button onclick="setActiveProfile('${p.name}')" class="success">Activate</button>` :
                                `<button onclick="setActiveProfile('${p.name}')" class="success">Activate</button>
                                 <button onclick="deleteProfile('${p.name}')" class="danger">Delete</button>`
                            }
                        </div>
                    </div>
                `).join('');
            }
        }
    } catch (error) {
        console.error('Error loading voice profiles:', error);
    }
}

async function createVoiceProfile() {
    const name = document.getElementById('new-profile-name')?.value;
    const speed = parseFloat(document.getElementById('new-profile-speed')?.value || 1.0);
    const temperature = parseFloat(document.getElementById('new-profile-temp')?.value || 0.7);
    const description = document.getElementById('new-profile-desc')?.value || '';
    
    if (!name) {
        addLog('error', 'Profile name required');
        return;
    }
    
    addLog('info', `📋 Creating profile: ${name}...`);
    
    const result = await apiCall('/api/voice-profiles/create', 'POST', {
        name,
        speed,
        temperature,
        description
    });
    
    if (result.success) {
        addLog('info', `✅ Profile created: ${name}`);
        document.getElementById('new-profile-name').value = '';
        document.getElementById('new-profile-desc').value = '';
        loadVoiceProfiles();
    } else {
        addLog('error', `❌ Failed: ${result.error}`);
    }
}

async function setActiveProfile(profileName) {
    addLog('info', `🎙️ Setting profile: ${profileName}...`);
    
    const result = await apiCall(`/api/voice-profiles/set-active?profile_name=${profileName}`, 'POST');
    
    if (result.success) {
        addLog('info', `✅ Active: ${profileName}`);
        loadVoiceProfiles();
    } else {
        addLog('error', `❌ Failed: ${result.error}`);
    }
}

async function deleteProfile(profileName) {
    if (!confirm(`Delete profile "${profileName}"?`)) return;
    
    const result = await apiCall(`/api/voice-profiles/${profileName}`, 'DELETE');
    
    if (result.success) {
        addLog('info', `🗑️ Deleted: ${profileName}`);
        loadVoiceProfiles();
    } else {
        addLog('error', `❌ Failed: ${result.error}`);
    }
}

// ============================================================================
// MODEL HOT-SWAPPING
// ============================================================================

// ADD proper error handling to apiCall():

// Enhanced API call with detailed error logging
async function apiCall(endpoint, method = 'GET', body = null) {
    console.log(`🔵 API Call: ${method} ${endpoint}`);
    
    try {
        const options = {
            method,
            headers: {'Content-Type': 'application/json'}
        };
        if (body) {
            options.body = JSON.stringify(body);
            console.log(`📦 Request body:`, body);
        }
        
        const response = await fetch(`${window.location.origin}${endpoint}`, options);
        console.log(`📡 Response status: ${response.status}`);
        
        if (!response.ok) {
            const errorText = await response.text();
            console.error(`❌ HTTP ${response.status}:`, errorText);
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        console.log(`✅ Response data:`, data);
        return data;
        
    } catch (error) {
        console.error(`❌ API call failed [${method} ${endpoint}]:`, error);
        addLog('error', `API Error: ${error.message}`);
        return { success: false, error: error.message };
    }
}

// (LM Studio model management removed during vLLM migration)

// ============================================================================
// BACKGROUND QUEUE
// ============================================================================

async function loadBackgroundQueue() {
    try {
        const data = await apiCall('/api/background/queue');
        
        if (!data.error) {
            const queueSize = document.getElementById('bg-queue-size');
            const queueStatus = document.getElementById('bg-queue-status');
            
            if (queueSize) queueSize.textContent = data.size || 0;
            if (queueStatus) queueStatus.textContent = data.is_running ? 'Running' : 'Stopped';
        }
    } catch (error) {
        console.error('Error loading background queue:', error);
    }
}

async function clearBackgroundQueue() {
    if (!confirm('Clear all pending background tasks?')) return;
    
    addLog('info', '🗑️ Clearing background queue...');
    
    const result = await apiCall('/api/background/clear-queue', 'POST');
    
    if (result.success) {
        addLog('info', `✅ Cleared ${result.cleared} tasks`);
        loadBackgroundQueue();
    } else {
        addLog('error', `❌ Failed: ${result.error}`);
    }
}

// ============================================================================
// AUTO-REFRESH FOR LIVE DATA
// ============================================================================

let liveUpdateInterval = null;

function startLiveUpdates() {
    if (liveUpdateInterval) return;
    
    liveUpdateInterval = setInterval(() => {
        const activeTab = document.querySelector('.tab-content:not(.hidden)');
        if (!activeTab) return;
        
        const tabId = activeTab.id;
        
        if (tabId === 'voice') {
            loadAudioStats();
            loadActiveSpeakers();
        } else if (tabId === 'dashboard') {
            loadBackgroundQueue();
        }
    }, 300000); // Every 5 minutes (reduced from 30 seconds to minimize API calls)
    
    console.log('Live updates started (5-minute interval to reduce API spam)');
}

function stopLiveUpdates() {
    if (liveUpdateInterval) {
        clearInterval(liveUpdateInterval);
        liveUpdateInterval = null;
        console.log('Live updates stopped');
    }
}

// ============================================================================
// SLIDER HELPERS
// ============================================================================

function updateSliderDisplay(sliderId, value) {
    const valueDisplay = document.getElementById(`${sliderId}-value`);
    if (valueDisplay) {
        valueDisplay.textContent = value;
    }
}

function initSliders() {
    const sliders = [
        'vad-threshold',
        'silence-threshold',
        'new-profile-speed',
        'new-profile-temp'
    ];
    
    sliders.forEach(sliderId => {
        const slider = document.getElementById(sliderId);
        if (slider) {
            slider.addEventListener('input', (e) => {
                updateSliderDisplay(sliderId, e.target.value);
            });
        }
    });
}

// ============================================================================
// INITIALIZATION
// ============================================================================

function initEnhancedControls() {
    console.log('Initializing enhanced controls...');
    
    initSliders();
    loadAvailableVoices();
    loadCurrentTTS();
    loadVoiceProfiles();
    loadAudioSettings();
    startLiveUpdates();
    
    console.log('Enhanced controls initialized');
}

// Auto-initialize
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initEnhancedControls);
} else {
    initEnhancedControls();
}

// ============================================================================
// ENHANCED TAB SWITCHING
// ============================================================================


// Removed LM Studio tab lifecycle hooks and auto-refresh

console.log('✅ Model management JavaScript loaded');