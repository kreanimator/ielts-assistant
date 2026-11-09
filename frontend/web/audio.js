// Browser audio for the app, used from lib/audio.dart.
//   startMic(onPcm)  calls onPcm(ArrayBuffer) with PCM16 mono 16 kHz, every 64 ms
//   play(buffer)     queues PCM16 mono 24 kHz speech
//   remainingMs()    how much queued speech has not been played yet
//   level()          loudness of the speech playing now, 0..1 (moves the avatar's mouth)
//   stop()           stops the mic and the speech
(() => {
  // Runs on the audio thread: collects 1024 samples, then posts them to the page.
  const WORKLET = `
    class Mic extends AudioWorkletProcessor {
      constructor() { super(); this.buffer = new Float32Array(1024); this.length = 0; }
      process(inputs) {
        const samples = inputs[0][0];
        if (!samples) return true;
        for (const s of samples) {
          this.buffer[this.length++] = s;
          if (this.length === this.buffer.length) {
            this.port.postMessage(this.buffer.slice(0));
            this.length = 0;
          }
        }
        return true;
      }
    }
    registerProcessor('mic', Mic);`;

  let stream, micCtx, playCtx, analyser, playEnd = 0;
  const levelData = new Float32Array(1024);

  function ensurePlayback() {
    if (playCtx) return;
    playCtx = new AudioContext({ sampleRate: 24000 });
    analyser = playCtx.createAnalyser();
    analyser.fftSize = 1024;
    analyser.connect(playCtx.destination);
  }

  window.ieltsAudio = {
    async startMic(onPcm) {
      ensurePlayback();  // created here, during the user's click, so the browser allows sound
      await playCtx.resume();
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      });
      micCtx = new AudioContext({ sampleRate: 16000 });
      const url = URL.createObjectURL(new Blob([WORKLET], { type: 'text/javascript' }));
      await micCtx.audioWorklet.addModule(url);
      const mic = new AudioWorkletNode(micCtx, 'mic');
      micCtx.createMediaStreamSource(stream).connect(mic);
      mic.connect(micCtx.destination);  // outputs silence; keeps the node running
      mic.port.onmessage = event => {
        const samples = event.data;
        const pcm = new Int16Array(samples.length);
        for (let i = 0; i < samples.length; i++) pcm[i] = Math.max(-1, Math.min(1, samples[i])) * 32767;
        onPcm(pcm.buffer);
      };
    },

    play(buffer) {
      ensurePlayback();
      const pcm = new Int16Array(buffer);
      const audio = playCtx.createBuffer(1, pcm.length, 24000);
      const channel = audio.getChannelData(0);
      for (let i = 0; i < pcm.length; i++) channel[i] = pcm[i] / 32768;
      const source = playCtx.createBufferSource();
      source.buffer = audio;
      source.connect(analyser);
      playEnd = Math.max(playEnd, playCtx.currentTime);
      source.start(playEnd);
      playEnd += audio.duration;
    },

    remainingMs() {
      return playCtx ? Math.max(0, playEnd - playCtx.currentTime) * 1000 : 0;
    },

    level() {
      if (!analyser || this.remainingMs() === 0) return 0;
      analyser.getFloatTimeDomainData(levelData);
      let sum = 0;
      for (const s of levelData) sum += s * s;
      return Math.min(1, Math.sqrt(sum / levelData.length) * 6);
    },

    stop() {
      stream?.getTracks().forEach(track => track.stop());
      micCtx?.close();
      playCtx?.close();
      stream = micCtx = playCtx = analyser = undefined;
      playEnd = 0;
    },
  };
})();
