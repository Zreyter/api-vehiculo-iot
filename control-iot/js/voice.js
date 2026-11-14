const wakeWord = /^kiwi(?=$|[\s\p{P}])/iu;
const punctuation = /^[\s\p{P}]+|[\s\p{P}]+$/gu;
const stopCommand = /^(?:para|parar|detente|alto|stop)(?:\s+por favor)?$/iu;
const commandWindowMs = 7000;
const restartDelayMs = 300;

export class KiwiListener {
  constructor({ Speech, onStatus, onCommand, onStop, onError }) {
    Object.assign(this, { Speech, onStatus, onCommand, onStop, onError });
  }

  start() {
    if (this.enabled) return;
    this.enabled = true;
    this.open();
  }

  open() {
    const recognition = this.recognition = new this.Speech();
    recognition.lang = 'es-MX';
    recognition.continuous = true;
    recognition.interimResults = false;
    recognition.onstart = () => {
      if (this.recognition === recognition) this.updateStatus();
    };
    recognition.onresult = event => {
      for (let i = event.resultIndex; i < event.results.length && this.recognition === recognition; i++) {
        if (event.results[i].isFinal) this.receive(event.results[i][0].transcript);
      }
    };
    recognition.onerror = ({ error }) => {
      if (this.recognition !== recognition || error === 'no-speech') return;
      this.fail(error === 'not-allowed' || error === 'service-not-allowed'
        ? 'El navegador bloqueó el micrófono. Revisa el permiso y vuelve a activarlo.'
        : 'Se interrumpió el reconocimiento de voz. Vuelve a activar Kiwi.');
    };
    recognition.onend = () => {
      if (this.recognition !== recognition) return;
      this.recognition = null;
      this.retry = setTimeout(() => {
        if (this.enabled) this.open();
      }, restartDelayMs);
    };
    try {
      recognition.start();
    } catch {
      this.fail('No se pudo iniciar el micrófono.');
    }
  }

  receive(transcript) {
    const phrase = transcript.replace(punctuation, '');
    const woke = wakeWord.test(phrase);
    if (!woke && !this.waiting) return;
    const command = woke ? phrase.replace(wakeWord, '').replace(punctuation, '') : phrase;
    if (!command) {
      if (!woke) return;
      this.resetWake();
      this.waiting = setTimeout(() => {
        this.waiting = null;
        this.updateStatus();
      }, commandWindowMs);
      this.updateStatus();
      return;
    }
    this.resetWake();
    this.updateStatus();
    if (stopCommand.test(command)) this.onStop();
    else this.onCommand(command);
  }

  updateStatus() {
    this.onStatus(this.waiting ? 'Te escucho…' : 'Escuchando «Kiwi»…');
  }

  resetWake() {
    clearTimeout(this.waiting);
    this.waiting = null;
  }

  fail(message) {
    this.stop();
    this.onError(message);
  }

  stop() {
    this.enabled = false;
    this.resetWake();
    clearTimeout(this.retry);
    const recognition = this.recognition;
    this.recognition = null;
    recognition?.abort();
  }
}
