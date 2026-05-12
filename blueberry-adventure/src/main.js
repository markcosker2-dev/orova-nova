import Phaser from 'phaser';
import Level1 from './scenes/Level1';
import Level2 from './scenes/Level2';
import Level3 from './scenes/Level3';

import DialogueUI from './ui/Dialogue';

const config = {
    type: Phaser.AUTO,
    width: 800,
    height: 600,
    parent: 'game-container',
    physics: {
        default: 'arcade',
        arcade: {
            gravity: { y: 0 },
            debug: false
        }
    },
    scene: [Level1, Level2, Level3]
};

const dialogue = new DialogueUI();
const game = new Phaser.Game(config);

game.events.on('ready', () => {
    game.scene.scenes.forEach(scene => {
        scene.events.on('show-dialogue', (text) => {
            dialogue.show(text);
        });
    });
});
