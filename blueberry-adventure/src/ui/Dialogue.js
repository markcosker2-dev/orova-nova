export default class DialogueUI {
    constructor() {
        this.overlay = document.getElementById('dialogue-overlay');
        this.textElement = document.getElementById('dialogue-text');
        this.closeBtn = document.getElementById('close-dialogue');
        
        this.closeBtn.onclick = () => this.hide();
    }

    show(text) {
        this.overlay.classList.remove('hidden');
        this.typewriter(text, 0);
    }

    typewriter(text, index) {
        if (index < text.length) {
            this.textElement.innerText = text.substring(0, index + 1);
            this.typeTimeout = setTimeout(() => this.typewriter(text, index + 1), 30);
        }
    }

    hide() {
        clearTimeout(this.typeTimeout);
        this.overlay.classList.add('hidden');
    }
}
