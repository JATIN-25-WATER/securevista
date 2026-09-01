/**
 * Dual-engine Siren audio manager:
 * 1. Web Audio API synthesized security siren (guaranteed to work locally, no network fetch needed)
 * 2. HTML5 Audio fallback using /siren.mp3 asset
 * 
 * Includes browser autoplay unlock handling.
 */

class SirenManager {
  constructor() {
    this.audioCtx = null;
    this.oscillator = null;
    this.gainNode = null;
    this.isPlaying = false;
    this.unlocked = false;
    this.sirenInterval = null;
    this.audioElement = null;
  }

  init() {
    if (this.unlocked) return;
    try {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (AudioCtx) {
        this.audioCtx = new AudioCtx();
        if (this.audioCtx.state === 'suspended') {
          this.audioCtx.resume();
        }
      }
      this.audioElement = new Audio('/siren.mp3');
      this.audioElement.loop = true;
      this.unlocked = true;
    } catch (e) {
      console.warn('AudioContext initialization warning:', e);
    }
  }

  unlock() {
    this.init();
    if (this.audioCtx && this.audioCtx.state === 'suspended') {
      this.audioCtx.resume();
    }
  }

  startSiren() {
    this.init();
    if (this.isPlaying) return;
    this.isPlaying = true;

    // Try HTML5 Audio element first if file exists, else use Web Audio synth
    if (this.audioElement) {
      const playPromise = this.audioElement.play();
      if (playPromise !== undefined) {
        playPromise.catch(() => {
          // Autoplay blocked or file missing -> fallback to Web Audio synth
          this._startSynthSiren();
        });
        return;
      }
    }
    this._startSynthSiren();
  }

  _startSynthSiren() {
    try {
      if (!this.audioCtx) return;
      if (this.audioCtx.state === 'suspended') {
        this.audioCtx.resume();
      }

      this.oscillator = this.audioCtx.createOscillator();
      this.gainNode = this.audioCtx.createGain();

      this.oscillator.type = 'sawtooth';
      this.oscillator.frequency.setValueAtTime(800, this.audioCtx.currentTime);

      this.gainNode.gain.setValueAtTime(0.3, this.audioCtx.currentTime);

      this.oscillator.connect(this.gainNode);
      this.gainNode.connect(this.audioCtx.destination);

      this.oscillator.start();

      // Sweep frequency between 700Hz and 1200Hz to create security siren
      let high = false;
      this.sirenInterval = setInterval(() => {
        if (!this.oscillator || !this.audioCtx) return;
        const targetFreq = high ? 700 : 1200;
        high = !high;
        this.oscillator.frequency.exponentialRampToValueAtTime(
          targetFreq,
          this.audioCtx.currentTime + 0.35
        );
      }, 400);
    } catch (e) {
      console.error('Error starting siren synth:', e);
    }
  }

  stopSiren() {
    this.isPlaying = false;

    if (this.sirenInterval) {
      clearInterval(this.sirenInterval);
      this.sirenInterval = null;
    }

    if (this.audioElement) {
      this.audioElement.pause();
      this.audioElement.currentTime = 0;
    }

    if (this.oscillator) {
      try {
        this.oscillator.stop();
        this.oscillator.disconnect();
      } catch (e) {
        // Ignore
      }
      this.oscillator = null;
    }
  }
}

export const sirenManager = new SirenManager();
